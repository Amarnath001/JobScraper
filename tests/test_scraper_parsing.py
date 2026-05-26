from app.scrapers.parsing import (
    looks_like_job_board,
    parse_gem_listing_html,
    parse_icims_listing_html,
    parse_smartrecruiters_api_payload,
    parse_workday_careers_url,
    parse_workday_cxs_response,
    smartrecruiters_company_from_url,
)
from app.scrapers.smartrecruiters import SmartRecruitersScraper
from app.scrapers.workday import WorkdayScraper
from app.utils.source_urls import validation_expects_json, validation_url_for


SAMPLE_SR_API = {
    "totalFound": 2,
    "content": [
        {
            "id": "abc-123",
            "name": "Software Engineer",
            "location": {"city": "Austin", "region": "TX", "country": "US"},
            "ref": "software-engineer-abc",
            "releasedDate": "2026-03-01T12:00:00.000Z",
        }
    ],
}

SAMPLE_GEM_HTML = """
<html><body>
  <a href="https://jobs.gem.com/bilt/4509720004">Engineer</a>
  <a href="https://jobs.gem.com/bilt/5007870004">PM</a>
</body></html>
"""

SAMPLE_ICIMS_HTML = """
<html><body>
  <a href="https://careers-amd.icims.com/jobs/12345/software-engineer/job">Software Engineer</a>
  <a href="https://careers-amd.icims.com/jobs/99999/data-analyst/job">Data Analyst</a>
</body></html>
"""

SAMPLE_WORKDAY_CXS = {
    "total": 1,
    "jobPostings": [
        {
            "title": "Intern Engineer",
            "externalPath": "/job/intern-engineer",
            "locationsText": "San Jose, CA",
            "postedOn": 1710000000000,
            "bulletFields": ["R123"],
        }
    ],
}


def test_validation_accepts_new_source_types() -> None:
    assert validation_url_for(
        "workday",
        {"careers_url": "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite"},
    ).endswith("NVIDIAExternalCareerSite")
    assert validation_url_for("icims", {"careers_url": "https://careers-amd.icims.com/jobs"}) is not None
    assert validation_url_for("gem", {"careers_url": "https://jobs.gem.com/bilt"}) == "https://jobs.gem.com/bilt"
    assert (
        validation_url_for(
            "smartrecruiters",
            {"company": "Netflix", "careers_url": "https://jobs.smartrecruiters.com/Netflix"},
        )
        == "https://api.smartrecruiters.com/v1/companies/Netflix/postings"
    )
    assert validation_expects_json("smartrecruiters") is True
    assert validation_expects_json("workday") is False


def test_smartrecruiters_api_parser() -> None:
    jobs = parse_smartrecruiters_api_payload(SAMPLE_SR_API)
    assert len(jobs) == 1
    assert jobs[0]["name"] == "Software Engineer"

    scraper = SmartRecruitersScraper(
        "Acme",
        "https://jobs.smartrecruiters.com/acme",
        {"company": "acme"},
    )
    norm = scraper.normalize_job(jobs[0])
    assert norm.source_type == "smartrecruiters"
    assert norm.external_job_id == "abc-123"
    assert "Engineer" in norm.title
    assert "Austin" in (norm.location or "")


def test_gem_html_parser() -> None:
    jobs = parse_gem_listing_html(SAMPLE_GEM_HTML, "https://jobs.gem.com/bilt")
    assert len(jobs) == 2
    assert all("jobs.gem.com/bilt" in j["url"] for j in jobs)


def test_icims_html_parser() -> None:
    jobs = parse_icims_listing_html(
        SAMPLE_ICIMS_HTML,
        "https://careers-amd.icims.com/jobs",
    )
    assert len(jobs) == 2
    assert jobs[0]["url"].endswith("/job")


def test_workday_careers_url_parser() -> None:
    parts = parse_workday_careers_url(
        "https://boeing.wd1.myworkdayjobs.com/en-US/EXTERNAL_CAREERS/login"
    )
    assert parts is not None
    origin, tenant, site = parts
    assert tenant == "boeing"
    assert site == "EXTERNAL_CAREERS"
    assert "myworkdayjobs.com" in origin


def test_workday_cxs_response_parser() -> None:
    jobs = parse_workday_cxs_response(
        SAMPLE_WORKDAY_CXS,
        origin="https://nvidia.wd5.myworkdayjobs.com",
    )
    assert len(jobs) == 1
    scraper = WorkdayScraper(
        "NVIDIA",
        "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite",
        {"careers_url": "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite"},
    )
    norm = scraper.normalize_job(jobs[0])
    assert norm.source_type == "workday"
    assert "Intern" in norm.title


def test_looks_like_job_board() -> None:
    assert looks_like_job_board(SAMPLE_ICIMS_HTML, "icims")
    assert looks_like_job_board(SAMPLE_GEM_HTML, "gem")
    assert not looks_like_job_board("<html><body>hello</body></html>", "icims")


def test_smartrecruiters_company_from_url() -> None:
    assert smartrecruiters_company_from_url("https://jobs.smartrecruiters.com/Netflix") == "Netflix"
