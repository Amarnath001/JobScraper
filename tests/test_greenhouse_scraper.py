import pytest

from app.scrapers.greenhouse import GreenhouseScraper


@pytest.fixture
def sample_greenhouse_job() -> dict:
    return {
        "id": 12345,
        "title": "Software Engineer — New Grad",
        "location": {"name": "San Francisco, CA"},
        "absolute_url": "https://boards.greenhouse.io/acme/jobs/12345",
        "content": "<p>We are hiring new grads.</p>",
        "updated_at": "2026-03-27T12:00:00Z",
    }


def test_greenhouse_normalize_job(sample_greenhouse_job: dict) -> None:
    scraper = GreenhouseScraper(
        company_name="Acme",
        careers_url="https://boards.greenhouse.io/acme",
        source_config={"board_token": "acme"},
    )
    norm = scraper.normalize_job(sample_greenhouse_job)
    assert norm.company_name == "Acme"
    assert norm.source_type == "greenhouse"
    assert norm.external_job_id == "12345"
    assert "New Grad" in norm.title
    assert norm.location == "San Francisco, CA"
    assert norm.url.startswith("https://")
    assert norm.description_text is not None
    assert norm.posted_at is not None
