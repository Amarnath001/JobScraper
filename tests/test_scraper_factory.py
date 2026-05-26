import pytest

from app.db.models import Company
from app.services.scrape_runner_service import build_scraper
from app.scrapers.ashby import AshbyScraper
from app.scrapers.gem import GemScraper
from app.scrapers.greenhouse import GreenhouseScraper
from app.scrapers.icims import ICIMSScraper
from app.scrapers.lever import LeverScraper
from app.scrapers.smartrecruiters import SmartRecruitersScraper
from app.scrapers.generic_playwright import GenericPlaywrightScraper
from app.scrapers.workday import WorkdayScraper


def _company(source_type: str, source_config: dict) -> Company:
    return Company(
        id=1,
        name="TestCo",
        careers_url="https://example.com/careers",
        source_type=source_type,
        source_config=source_config,
        enabled=True,
    )


@pytest.mark.parametrize(
    ("source_type", "config", "expected_cls"),
    [
        ("greenhouse", {"board_token": "acme"}, GreenhouseScraper),
        ("lever", {"company": "acme"}, LeverScraper),
        ("ashby", {"organization": "acme"}, AshbyScraper),
        (
            "workday",
            {"careers_url": "https://acme.wd5.myworkdayjobs.com/en-US/AcmeSite"},
            WorkdayScraper,
        ),
        ("icims", {"careers_url": "https://careers-acme.icims.com/jobs"}, ICIMSScraper),
        ("gem", {"careers_url": "https://jobs.gem.com/acme"}, GemScraper),
        (
            "smartrecruiters",
            {"company": "acme", "careers_url": "https://jobs.smartrecruiters.com/acme"},
            SmartRecruitersScraper,
        ),
        (
            "generic_playwright",
            {"careers_url": "https://acme.com/careers"},
            GenericPlaywrightScraper,
        ),
    ],
)
def test_build_scraper_routes_source_types(
    source_type: str,
    config: dict,
    expected_cls: type,
) -> None:
    company = _company(source_type, config)
    scraper = build_scraper(company)
    assert isinstance(scraper, expected_cls)


def test_build_scraper_unknown_raises() -> None:
    company = _company("unknown_ats", {})
    with pytest.raises(ValueError, match="Unknown source_type"):
        build_scraper(company)
