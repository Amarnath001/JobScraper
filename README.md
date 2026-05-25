# job-scraper

Production-style MVP that pulls public job listings from company career systems (Greenhouse, Lever, Ashby, Workday, or custom Playwright pages), normalizes them, scores them for entry-level / new-grad / SWE I signals, deduplicates with a stable fingerprint, stores them in PostgreSQL, and sends a **daily email digest at 6:00 AM America/Los_Angeles** with jobs **first seen that calendar day** (only entry-level jobs in the digest). Jobs are never repeated in later digests once their `first_seen_at` is in the past.

## Architecture

- **FastAPI** exposes health, job queries, company admin, and manual scrape triggers.
- **SQLAlchemy 2.x (async)** + **asyncpg** talk to PostgreSQL.
- **Scrapers** implement `BaseScraper`: `fetch_raw_jobs()` → `normalize_job()` → `NormalizedJob`.
- **Ingest** computes a SHA-256 fingerprint, upserts rows, preserves `first_seen_at`, updates `last_seen_at`, and marks jobs inactive when they disappear from a company’s latest scrape.
- **Filter / scoring** (`filter_service`) uses weighted keyword patterns (easy to tune in one module).
- **Digest** (`digest_service`) selects rows where `first_seen_at` falls in “today” in `TIMEZONE`, `is_entry_level` is true, groups by company, and builds HTML + plain text.
- **Email** uses **Resend** (`email_service`).
- **APScheduler** runs the full pipeline daily at 06:00 in `TIMEZONE` (default `America/Los_Angeles`).

```
┌─────────────┐     ┌──────────┐     ┌─────────────┐     ┌──────────────┐
│  Scrapers   │────▶│  Ingest  │────▶│ PostgreSQL  │────▶│ Digest+Email │
│ (httpx/PW)  │     │ + dedupe │     │   (jobs)    │     │   (Resend)   │
└─────────────┘     └──────────┘     └─────────────┘     └──────────────┘
```

## Folder layout

```
job-scraper/
  app/
    main.py
    api/           # routes_health, routes_jobs, routes_admin
    core/          # config, logging, database, scheduler
    db/            # models, session, base
    schemas/       # pydantic models
    scrapers/      # greenhouse, lever, ashby, workday, generic_playwright
    services/      # ingest, filter, dedupe, digest, email, scrape runner, company
    utils/         # hashing, text, dates
  alembic/         # migrations
  tests/
  docker/
  data/
    companies.json # canonical company list
  scripts/
    run_scrape_cycle.py
    send_daily_digest.py
    import_companies_from_json.py
    validate_companies.py
    seed_companies.py
  .github/workflows/
    init-db.yml
    scrape-every-3-hours.yml
    daily-digest.yml
  Dockerfile
  docker-compose.yml
  requirements.txt
  .env.example
```

## Quick start (Docker)

1. Copy `.env.example` to `.env` and set at least `RESEND_API_KEY`, `EMAIL_FROM`, `EMAIL_TO` for real emails.

2. From the `job-scraper` directory:

```bash
docker compose up --build
```

3. API: `http://localhost:8000/health`

4. Apply migrations run automatically on container start (`alembic upgrade head` in `docker/entrypoint.sh`).

### Import and validate companies

```bash
# Upsert from data/companies.json (name + source_type)
docker compose exec app python scripts/import_companies_from_json.py

# Probe ATS endpoints; disable companies that return HTTP 404
docker compose exec app python scripts/validate_companies.py
```

Or via API:

```bash
curl -X POST http://localhost:8000/admin/companies/validate
curl "http://localhost:8000/admin/companies?enabled=false"
```

### Run tests (inside container)

```bash
docker compose run --rm --entrypoint "" app pytest -q
```

## Configuration

See `.env.example`. Important variables:

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | `postgresql+asyncpg://...` |
| `RESEND_API_KEY` | Resend API key |
| `EMAIL_FROM` | Verified sender in Resend |
| `EMAIL_TO` | Digest recipient |
| `SEND_EMPTY_DIGEST` | If `true`, send a short email when no new entry-level jobs today |
| `TIMEZONE` | Digest “today” boundaries and scheduler TZ (default `America/Los_Angeles`) |
| `ENABLE_SCHEDULER` | `false` to disable the 6 AM job (useful locally) |
| `DIGEST_LOOKBACK_HOURS` | Optional rolling window for `send_daily_digest.py` (e.g. `24`); unset = calendar day in `TIMEZONE` |
| `PLAYWRIGHT_HEADLESS` | Browser headless mode |
| `SCRAPE_TIMEOUT_SECONDS` | HTTP / navigation timeouts |
| `US_ONLY_MODE` | When `true` (default), ingest keeps only US and US-compatible remote jobs |

## US location filtering

When `US_ONLY_MODE=true`, the ingest pipeline (`ingest_service`) filters every scraped job **before** insert using `location_filter_service`. Only jobs that pass `is_us_or_remote(location)` are stored.

### How it works

1. **Normalize** the location string (lowercase, trim, collapse whitespace).
2. **Split** multi-location strings on `|`, `/`, `;`, ` or `, and ` and `.
3. **Classify** each segment into `US`, `REMOTE_US`, `INTERNATIONAL`, or `UNKNOWN`.
4. **Accept** only when every segment is `US` or `REMOTE_US` (no international segment, no unknown segment).

Helper API:

- `normalize_location(location)` — string cleanup
- `classify_location(location)` — returns a `LocationCategory`
- `is_us_or_remote(location)` — `True` for `US` and `REMOTE_US`

### Accepted examples

| Location | Category |
|----------|----------|
| `San Francisco, CA` | US |
| `New York, NY` | US |
| `United States` / `USA` / `US` | US |
| `Hybrid - San Francisco` | US |
| `Remote` | REMOTE_US |
| `Remote US`, `US Remote` | REMOTE_US |
| `Remote - United States`, `Anywhere in US` | REMOTE_US |
| `Remote/San Francisco` | US (US city + remote) |

### Rejected examples

| Location | Reason |
|----------|--------|
| `London`, `Paris, France`, `Berlin` | International city/country markers |
| `Toronto`, `Vancouver`, `Remote Canada` | Canada |
| `India`, `Singapore`, `Tokyo`, `Sydney` | Non-US regions |
| `Remote EMEA`, `Remote Europe`, `Remote India` | Remote tied to non-US region |
| `San Francisco, CA \| London, UK` | Mixed US + international |
| `EMEA`, `TBD` | Unknown (not persisted) |

Skipped jobs are logged at INFO:

`Skipping international job: Company=Datadog Location=Paris, France`

### Disable filtering

Set in `.env` or GitHub Actions env:

```bash
US_ONLY_MODE=false
```

All scraped locations are stored again (previous behavior).

To extend rules later, edit pattern groups in `app/services/location_filter_service.py` (US cities, international markers, remote-US phrases).

## Why companies get disabled

Companies are disabled automatically when their configured ATS endpoint is invalid:

- **Wrong `board_token` or Lever slug** — typos or outdated tokens in `data/companies.json`
- **Company changed ATS** — e.g. moved from Greenhouse to Workday; the old public API returns 404
- **Public job board not available** — some employers hide or retire the public JSON API
- **Company no longer exposes API** — board removed or merged (rebrand)

**Validation** (`scripts/validate_companies.py` or `POST /admin/companies/validate`) probes each URL and sets `enabled=false` on **HTTP 404**.

**Scraping** increments `consecutive_failures` on 404 during a run; after **2** consecutive 404s the company is disabled with a log like:

`Disabling Coinbase: Greenhouse board_token coinbase returned 404`

View disabled companies: `GET /admin/companies?enabled=false` (includes `last_error`, `last_validation_status`).

Re-enable after fixing `source_config` in the DB or JSON, then re-run validation.

## Adding a company

Prefer editing `data/companies.json` and running `scripts/import_companies_from_json.py`, or `POST /admin/companies` with JSON:

```json
{
  "name": "Acme",
  "careers_url": "https://job-boards.greenhouse.io/acme",
  "source_type": "greenhouse",
  "source_config": { "board_token": "acme" },
  "enabled": true
}
```

**Greenhouse:** `source_config.board_token` — public board token from the Greenhouse URL.

**Lever:** `source_config.company` — Lever site name (e.g. `figma` for `jobs.lever.co/figma`).

**Ashby:** `source_config.organization` — org slug, or `posting_api_url` for a full API URL override.

**Workday:** Prefer `json_url` (+ optional `json_method`, `json_body`, `json_headers`) for a JSON listing API; otherwise Playwright with `list_selector`, `item_link_selector`, optional `title_selector`, `location_selector`, `wait_selector`.

**Generic Playwright:** `list_selector`, `link_selector`, optional `title_selector`, `location_selector`, `load_more_selector`, `page_url`.

## Daily 6:00 AM digest

- **Docker / local API:** APScheduler runs the full pipeline at **06:00** in `TIMEZONE` when `ENABLE_SCHEDULER=true`.
- **GitHub Actions:** `scrape-every-3-hours.yml` scrapes every 3 hours **and sends a digest email** (entry-level jobs first seen in the last `DIGEST_LOOKBACK_HOURS`, default 4). `daily-digest.yml` is an optional morning catch-up (24h window); disable it if you only want post-scrape emails.
- After all enabled companies are scraped and ingested, the service loads jobs with `first_seen_at` in the **current local day** and `is_entry_level = true`, sorts by company and title, and sends one email.
- **Old jobs never appear again** in the digest: only rows whose `first_seen_at` is that day in `TIMEZONE` are included.

## Manual scrape

```bash
curl -X POST http://localhost:8000/admin/run-scrape
```

Same pipeline as the scheduled job (scrape → ingest → digest email).

## Deduplication

Fingerprint = SHA-256 of normalized `company_name | title | location | url | external_job_id` (see `utils/hashing.py`). If the hash exists, `first_seen_at` is unchanged, `last_seen_at` is updated, and the row is reactivated. If a job is missing from the latest scrape for that company, it is marked `is_active = false`.

## API summary

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness + DB check |
| GET | `/jobs` | Filter: `company`, `company_id`, `is_entry_level`, `is_active`, `first_seen_date`, `limit`, `offset` |
| GET | `/jobs/new-today` | Jobs first seen “today” in `TIMEZONE` |
| GET | `/admin/companies` | List companies (`?enabled=true|false`) |
| POST | `/admin/companies` | Create company |
| POST | `/admin/companies/validate` | Probe ATS URLs; disable 404s |
| POST | `/admin/run-scrape` | Run pipeline |
| POST | `/admin/send-test-email` | Send a test message to `EMAIL_TO` via Resend |

## Email troubleshooting

The app only sets `emails_sent: 1` when Resend returns a **message id** (provider accepted the send). `emails_attempted: 1` means a send was tried; check `email_failures` and container logs if `emails_sent` is 0.

### 1. Verify environment variables

In your project `.env` (used by Docker Compose for substitution):

```bash
RESEND_API_KEY=re_...
EMAIL_FROM="Your Name <onboarding@yourdomain.com>"
EMAIL_TO=you@example.com
```

`EMAIL_FROM` must use a **verified domain** in the [Resend dashboard](https://resend.com/domains) (or Resend’s test sender for quick tests).

After changing `.env`, recreate the app container (no image rebuild required):

```bash
docker compose up -d --force-recreate app
```

### 2. Send a test email

```bash
curl -X POST http://localhost:8000/admin/send-test-email
```

Success looks like:

```json
{"success": true, "message": "Test email accepted by provider", "provider_id": "..."}
```

If it fails, `error` explains the problem; the app also logs `EMAIL_TO`, `EMAIL_FROM`, subject, and a full stack trace on exceptions.

### 3. Inspect Docker env inside the running app

```bash
docker compose exec app printenv | grep -E 'RESEND|EMAIL'
```

Confirm `RESEND_API_KEY`, `EMAIL_FROM`, and `EMAIL_TO` are set as expected (Compose reads your host `.env` for `${RESEND_API_KEY}`, `${EMAIL_FROM}`, `${EMAIL_TO}`).

### 4. Check app logs

```bash
docker compose logs -f app
```

Look for:

- Startup: `Email config: ...` warnings if something is missing
- `Sending email: to=... from=... subject=... jobs_in_digest=...`
- `Email accepted by provider: ... provider_id=...` on success
- `Email provider raised:` or `Email rejected or incomplete response:` on failure

### 5. Run-scrape response fields

`POST /admin/run-scrape` returns:

- `success: true` if the pipeline finished (even when some companies 404)
- `scraper_failures`: per-company scrape errors
- `email_failures`: config or Resend issues
- `emails_attempted` / `emails_sent`: only count a sent email when the provider returns an id

## GitHub Actions (production scheduling)

Run scraping and the morning digest **without a 24/7 server**. Point workflows at your managed PostgreSQL (e.g. [Render](https://render.com), [Neon](https://neon.tech), or Supabase) using repository secrets.

### First-time setup (Render Postgres + GitHub)

1. **Create Render PostgreSQL** and copy the **External** connection string.
2. **Add GitHub repository secrets** (Settings → Secrets and variables → Actions):

   | Secret | Example format |
   |--------|----------------|
   | `DATABASE_URL` | `postgresql+asyncpg://USER:PASS@HOST:5432/DB?sslmode=require` |
   | `RESEND_API_KEY` | `re_...` |
   | `EMAIL_FROM` | `Job Scraper <jobs@yourdomain.com>` |
   | `EMAIL_TO` | `you@example.com` |

   Secret **names** must match exactly. Paste only the value (no `DATABASE_URL=` prefix).

3. **Run Init DB once** (manual workflow): Actions → **Init database (one-time)** → **Run workflow** on `main`.

   This runs `alembic upgrade head`, imports `data/companies.json`, and validates sources. The log ends with `=== INIT DB SUMMARY ===` (company counts).

4. **Run scrape** (manual or wait for cron): Actions → **Scrape every 3 hours** → **Run workflow**.

   Scheduled scrape and digest workflows run `alembic upgrade head` on every job (idempotent). They do **not** re-import companies each time.

### Workflows

| Workflow file | When | What it does |
|---------------|------|----------------|
| `init-db.yml` | Manual only | Migrations + import companies + validate (run **once** per database) |
| `scrape-every-3-hours.yml` | `0 */3 * * *` UTC | `alembic upgrade head` → scrape + digest email |
| `daily-digest.yml` | `0 14 * * *` UTC | `alembic upgrade head` → optional 24h digest email |

All workflows support **Run workflow** via `workflow_dispatch`.

**Post-scrape email (every 3 hours):** the scrape workflow sets `SEND_DIGEST_AFTER_SCRAPE=true` and `DIGEST_LOOKBACK_HOURS=4`. After each scrape it emails **entry-level** jobs whose `first_seen_at` is in that rolling window. No email is sent when there are zero qualifying jobs and `SEND_EMPTY_DIGEST=false`.

**Morning email (optional):** `daily-digest.yml` uses a 24h lookback. You can disable that workflow on GitHub if you only want the 3-hour emails.

The in-app APScheduler (`ENABLE_SCHEDULER=true`) runs the full pipeline at 6:00 AM with **calendar-day** digest unless you set `DIGEST_LOOKBACK_HOURS` in `.env`.

### How cron schedules work

- GitHub Actions `schedule` uses **UTC** only (unless you add a `timezone` field on the cron entry).
- `0 */3 * * *` — at minute 0, every 3rd hour (00:00, 03:00, 06:00, … UTC).
- `0 14 * * *` — 14:00 UTC daily, which is **6:00 AM Pacific Standard Time** (UTC−8). During daylight saving (PDT, UTC−7) the same cron fires at **7:00 AM** local. If you need 6:00 AM year-round regardless of DST, change the workflow to `cron: "0 6 * * *"` with `timezone: America/Los_Angeles` instead of the UTC line above.
- Scheduled runs only run on the **default branch** (usually `main`) and may be delayed a few minutes during high GitHub load.

### Required GitHub Secrets

Add under **Settings → Secrets and variables → Actions → Repository secrets**:

| Secret | Purpose |
|--------|---------|
| `DATABASE_URL` | Async SQLAlchemy URL, e.g. `postgresql+asyncpg://user:pass@host/db?ssl=require` (Render external URL) |
| `RESEND_API_KEY` | Resend API key with send permission |
| `EMAIL_FROM` | Verified sender, e.g. `Job Scraper <jobs@yourdomain.com>` |
| `EMAIL_TO` | Recipient inbox |

Workflows also set these **environment variables** (not secrets):

| Variable | Value |
|----------|--------|
| `TIMEZONE` | `America/Los_Angeles` |
| `PLAYWRIGHT_HEADLESS` | `true` |
| `LOG_LEVEL` | `INFO` |
| `ENABLE_SCHEDULER` | `false` (no APScheduler in CI) |
| `SEND_DIGEST_AFTER_SCRAPE` | `true` on 3-hour scrape workflow |
| `DIGEST_LOOKBACK_HOURS` | `4` on scrape workflow; `24` on daily-digest workflow |

### One-time database setup (local or CI)

Same steps as the **Init database** workflow, runnable on your machine:

```bash
export DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname
alembic upgrade head
python scripts/import_companies_from_json.py
python scripts/validate_companies.py
```

Alembic reads `DATABASE_URL` from the environment (`alembic/env.py`); it does not use the placeholder URL in `alembic.ini`.

### Manually trigger a workflow

1. Open the repo on GitHub → **Actions**.
2. First time: **Init database (one-time)** → **Run workflow**.
3. Then: **Scrape every 3 hours** or **Daily digest email** → **Run workflow** on `main`.

Use this to test secrets, migrations, Playwright, and email without waiting for cron.

### Inspect workflow logs

1. **Actions** → click a workflow run → click the job (`scrape` or `digest`).
2. Expand **Apply database migrations**, **Run scrape cycle**, or **Send daily digest**.
3. Look for structured blocks:
   - **Scrape:** `=== SCRAPE CYCLE SUMMARY ===` with `companies_scanned`, `jobs_seen`, `new_jobs_created`, `inactive_jobs_marked`, and `scraper_failures` (also printed as JSON).
   - **Digest:** `=== DAILY DIGEST SUMMARY ===` with `digest_jobs_count`, `digest_window`, `emails_sent`, and `email_sent_successfully`.
4. Per-company lines appear at `INFO` during scrape (`Scraped company=…`).
5. Failures print `SCRAPER_FAILURE:` or `EMAIL_FAILURE:` on stderr; unhandled exceptions fail the step with a non-zero exit code.

### Exit behavior

- **Scrape:** exits `0` even when individual companies fail (404s, timeouts), so one bad board does not block the whole run. Unhandled exceptions exit `1`.
- **Digest:** exits `1` if Resend/config fails or an email was attempted but not confirmed sent. Skips send when there are zero qualifying jobs and `SEND_EMPTY_DIGEST=false` (exit `0`).

### Cost notes

- GitHub Actions: generous free minutes on public repos; private repos have a monthly allowance.
- Render/Neon/Supabase free tiers are usually enough for this workload.
- Resend: free tier for low email volume.

### Optional: Docker locally

Use Docker for development and the HTTP API (`/admin/*`). Production scheduling can be entirely GitHub Actions with `ENABLE_SCHEDULER=false` locally.

## Local development (without Docker)

Requires Python **3.12**, PostgreSQL, and:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
export DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/jobscraper
alembic upgrade head
uvicorn app.main:app --reload
```

## Future improvements

- Per-source rate limits and exponential backoff; persistent scrape run history.
- Stronger Workday / Ashby adapters per tenant (GraphQL, CXS POST bodies).
- ML-based relevance instead of pure keyword scoring.
- OAuth or API keys for admin routes; structured metrics (Prometheus).
