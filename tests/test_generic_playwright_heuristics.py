from app.scrapers.generic_playwright import GenericPlaywrightScraper
from app.scrapers.generic_playwright_heuristics import (
    candidate_follow_urls,
    extract_title_from_link_text,
    is_job_link,
    is_rejected_url,
    links_from_anchor_dicts,
)
from app.services.scrape_runner_service import build_scraper
from app.db.models import Company


def test_accepts_job_urls() -> None:
    assert is_job_link("https://careers.example.com/jobs/123-engineer", "Software Engineer")
    assert is_job_link("https://example.com/careers/openings", "View openings")


def test_rejects_login_and_benefits() -> None:
    assert is_rejected_url("https://careers.example.com/login", "Sign in")
    assert is_rejected_url("https://careers.example.com/benefits", "Benefits")
    assert is_rejected_url("https://careers.example.com/blog/post", "Blog")
    assert not is_job_link("https://careers.example.com/login", "Login")


def test_extract_title_from_link_text() -> None:
    assert "Engineer" in extract_title_from_link_text("Software Engineer — New Grad")
    assert extract_title_from_link_text("Apply") == "Open position"


def test_links_from_anchor_dicts_dedupes() -> None:
    anchors = [
        {"href": "https://co.com/jobs/1", "text": "Software Engineer I"},
        {"href": "https://co.com/jobs/1", "text": "Software Engineer I"},
        {"href": "https://co.com/privacy", "text": "Privacy"},
    ]
    jobs = links_from_anchor_dicts(anchors, "https://co.com/careers", max_links=50)
    assert len(jobs) == 1
    assert jobs[0].title.startswith("Software")


def test_candidate_follow_urls() -> None:
    hrefs = [
        "https://acme.com/careers/jobs",
        "https://acme.com/about",
        "https://acme.com/careers/search",
    ]
    follow = candidate_follow_urls("https://acme.com/careers", "https://acme.com/careers", hrefs)
    assert any("/jobs" in u or "/search" in u for u in follow)


def test_normalize_job_shape() -> None:
    scraper = GenericPlaywrightScraper(
        "Acme",
        "https://acme.com/careers",
        {"careers_url": "https://acme.com/careers"},
    )
    norm = scraper.normalize_job(
        {
            "title": "Software Engineer",
            "url": "https://acme.com/jobs/1",
            "location": "Remote, US",
        }
    )
    assert norm.source_type == "generic_playwright"
    assert norm.company_name == "Acme"
    assert norm.title == "Software Engineer"
    assert norm.url.endswith("/jobs/1")
    assert norm.location == "Remote, US"


def test_build_scraper_routes_generic_playwright() -> None:
    company = Company(
        id=1,
        name="Acme",
        careers_url="https://acme.com/careers",
        source_type="generic_playwright",
        source_config={"careers_url": "https://acme.com/careers"},
        enabled=True,
    )
    scraper = build_scraper(company)
    assert isinstance(scraper, GenericPlaywrightScraper)
