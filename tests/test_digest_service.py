from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.services.digest_service import DigestService


def test_digest_build_bodies_groups_and_links() -> None:
    jobs = [
        SimpleNamespace(
            title="Software Engineer I",
            url="https://jobs.example.com/1",
            location="Remote",
            posted_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
            company=SimpleNamespace(name="Beta Co"),
        ),
        SimpleNamespace(
            title="Campus SWE",
            url="https://jobs.example.com/2",
            location=None,
            posted_at=None,
            company=SimpleNamespace(name="Alpha Inc"),
        ),
    ]
    d = date(2026, 3, 27)
    subject, html, text = DigestService.build_digest_bodies(jobs, d)

    assert subject == "New Entry-Level SWE Jobs — 2026-03-27"
    assert "Alpha Inc" in html
    assert "Beta Co" in html
    assert "https://jobs.example.com/1" in html
    assert "Campus SWE" in text


def test_digest_empty() -> None:
    subject, html, text = DigestService.build_digest_bodies([], date(2026, 3, 27))
    assert "No new entry-level jobs today" in html
    assert "No new entry-level jobs today" in text
