import html
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.config import get_settings
from app.db.models import Job
from app.utils.dates import end_of_day_local, start_of_day_local, today_in_timezone

_DIGEST_FILTERS = (
    Job.is_entry_level.is_(True),
    Job.is_software_engineering_related.is_(True),
)


def _format_posted(posted_at) -> str:
    if posted_at is None:
        return ""
    try:
        return posted_at.date().isoformat()
    except Exception:
        return str(posted_at)[:10]


class DigestService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_todays_new_entry_level_jobs(self) -> list[Job]:
        """Entry-level SWE jobs first seen today (local timezone)."""
        settings = get_settings()
        tz = settings.timezone
        today: date = today_in_timezone(tz)
        start = start_of_day_local(today, tz)
        end = end_of_day_local(today, tz)

        stmt = (
            select(Job)
            .options(joinedload(Job.company))
            .where(
                and_(
                    *_DIGEST_FILTERS,
                    Job.first_seen_at >= start,
                    Job.first_seen_at <= end,
                )
            )
            .order_by(Job.company_id, Job.title)
        )
        res = await self._session.execute(stmt)
        return list(res.unique().scalars().all())

    async def get_entry_level_jobs_first_seen_within_hours(self, hours: int) -> list[Job]:
        """Entry-level SWE jobs whose first_seen_at is within the last `hours` (UTC)."""
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        stmt = (
            select(Job)
            .options(joinedload(Job.company))
            .where(
                and_(
                    *_DIGEST_FILTERS,
                    Job.first_seen_at >= since,
                )
            )
            .order_by(Job.company_id, Job.title)
        )
        res = await self._session.execute(stmt)
        return list(res.unique().scalars().all())

    @staticmethod
    def build_digest_bodies(jobs: list[Job], digest_date: date) -> tuple[str, str, str]:
        """Returns (subject, html, plain_text)."""
        subject = f"New Entry-Level SWE Jobs — {digest_date.isoformat()}"
        if not jobs:
            return subject, "<p>No new entry-level SWE jobs today.</p>", "No new entry-level SWE jobs today."

        by_company: dict[str, list[Job]] = defaultdict(list)
        for j in jobs:
            cname = j.company.name if j.company else "Unknown"
            by_company[cname].append(j)

        lines_txt: list[str] = [f"New entry-level SWE jobs — {digest_date.isoformat()}", ""]
        html_parts: list[str] = [
            "<html><body style=\"font-family:system-ui,Segoe UI,Roboto,sans-serif;font-size:15px;line-height:1.5;\">",
            f"<h2 style=\"margin:0 0 12px;\">New entry-level SWE jobs — {html.escape(digest_date.isoformat())}</h2>",
        ]

        for company in sorted(by_company.keys()):
            lines_txt.append(f"## {company}")
            html_parts.append(f"<h3 style=\"margin:20px 0 8px;\">{html.escape(company)}</h3><ul style=\"margin:0;padding-left:20px;\">")
            for job in by_company[company]:
                loc = job.location or ""
                posted = _format_posted(job.posted_at)
                meta_bits = [x for x in [loc, posted] if x]
                meta = " — ".join(meta_bits)
                safe_url = html.escape(job.url, quote=True)
                title_esc = html.escape(job.title)
                html_parts.append(
                    f'<li style="margin-bottom:10px;"><a href="{safe_url}">{title_esc}</a>'
                    + (f"<br/><span style=\"color:#555;font-size:13px;\">{html.escape(meta)}</span>" if meta else "")
                    + "</li>"
                )
                line = f"- {job.title}\n  {job.url}"
                if meta:
                    line += f"\n  {meta}"
                lines_txt.append(line)
            html_parts.append("</ul>")
            lines_txt.append("")

        html_parts.append("</body></html>")
        return subject, "".join(html_parts), "\n".join(lines_txt).strip()
