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
  scripts/         # seed_example_companies.py
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

### Example companies (disabled)

```bash
docker compose exec app python scripts/seed_example_companies.py
```

Then enable or edit companies via `POST /admin/companies` or SQL.

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
| `PLAYWRIGHT_HEADLESS` | Browser headless mode |
| `SCRAPE_TIMEOUT_SECONDS` | HTTP / navigation timeouts |

## Adding a company

`POST /admin/companies` with JSON:

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

- APScheduler runs `run_scrape_pipeline` at **06:00** in `TIMEZONE`.
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
| GET | `/admin/companies` | List companies |
| POST | `/admin/companies` | Create company |
| POST | `/admin/run-scrape` | Run pipeline |

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
