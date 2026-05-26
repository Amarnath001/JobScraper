from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db.models import Company
from app.scrapers.parsing import looks_like_job_board
from app.services.company_validation_service import probe_company_source
from app.utils.source_urls import careers_url_for, validation_expects_json, validation_url_for


def _company(source_type: str, source_config: dict) -> Company:
    return Company(
        id=1,
        name="TestCo",
        careers_url="https://example.com/careers",
        source_type=source_type,
        source_config=source_config,
        enabled=True,
    )


def _mock_http_response(*, status_code: int, json_body: dict | None = None, text: str = "") -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    if json_body is not None:
        response.json.return_value = json_body
    return response


def _patch_httpx_get(return_value: MagicMock) -> object:
    client = AsyncMock()
    client.get = AsyncMock(return_value=return_value)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return patch(
        "app.services.company_validation_service.httpx.AsyncClient",
        return_value=client,
    )


@pytest.mark.asyncio
async def test_greenhouse_200_valid_no_undefined_err() -> None:
    company = _company("greenhouse", {"board_token": "stripe"})
    response = _mock_http_response(status_code=200, json_body={"jobs": []})

    with _patch_httpx_get(response):
        result = await probe_company_source(company, retries=1)

    assert result.valid is True
    assert result.status_code == 200
    assert result.error == ""
    assert result.source_type == "greenhouse"


@pytest.mark.asyncio
async def test_greenhouse_404_invalid() -> None:
    company = _company("greenhouse", {"board_token": "missing"})
    response = _mock_http_response(status_code=404)

    with _patch_httpx_get(response):
        result = await probe_company_source(company, retries=1)

    assert result.valid is False
    assert result.status_code == 404
    assert result.error == "HTTP 404"


@pytest.mark.asyncio
async def test_lever_200_valid_no_undefined_err() -> None:
    company = _company("lever", {"company": "netflix"})
    response = _mock_http_response(status_code=200, json_body=[])

    with _patch_httpx_get(response):
        result = await probe_company_source(company, retries=1)

    assert result.valid is True
    assert result.status_code == 200
    assert result.error == ""
    assert result.source_type == "lever"


@pytest.mark.asyncio
async def test_lever_404_invalid() -> None:
    company = _company("lever", {"company": "missing"})
    response = _mock_http_response(status_code=404)

    with _patch_httpx_get(response):
        result = await probe_company_source(company, retries=1)

    assert result.valid is False
    assert result.status_code == 404
    assert result.error == "HTTP 404"


@pytest.mark.asyncio
async def test_ashby_200_valid_no_undefined_err() -> None:
    company = _company("ashby", {"organization": "acme"})
    response = _mock_http_response(status_code=200, json_body={"jobs": []})

    with _patch_httpx_get(response):
        result = await probe_company_source(company, retries=1)

    assert result.valid is True
    assert result.status_code == 200
    assert result.error == ""
    assert result.source_type == "ashby"


@pytest.mark.asyncio
async def test_ashby_404_invalid() -> None:
    company = _company("ashby", {"organization": "missing"})
    response = _mock_http_response(status_code=404)

    with _patch_httpx_get(response):
        result = await probe_company_source(company, retries=1)

    assert result.valid is False
    assert result.status_code == 404
    assert result.error == "HTTP 404"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source_type", "source_config", "html"),
    [
        (
            "workday",
            {"careers_url": "https://boeing.wd1.myworkdayjobs.com/en-US/EXTERNAL_CAREERS"},
            "<html>myworkdayjobs job posting</html>",
        ),
        (
            "icims",
            {"careers_url": "https://careers-amd.icims.com/jobs"},
            '<html>icims <a href="/jobs/1/job">job</a></html>',
        ),
        (
            "gem",
            {"careers_url": "https://jobs.gem.com/bilt"},
            '<html><a href="https://jobs.gem.com/bilt/123">job</a></html>',
        ),
    ],
)
async def test_html_providers_200_valid(
    source_type: str,
    source_config: dict,
    html: str,
) -> None:
    company = _company(source_type, source_config)
    response = _mock_http_response(status_code=200, text=html)

    with _patch_httpx_get(response):
        result = await probe_company_source(company, retries=1)

    assert result.valid is True
    assert result.status_code == 200
    assert result.error == ""
    assert result.source_type == source_type


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source_type",
    ["workday", "icims", "gem"],
)
async def test_html_providers_404_invalid(source_type: str) -> None:
    configs = {
        "workday": {"careers_url": "https://boeing.wd1.myworkdayjobs.com/en-US/EXTERNAL_CAREERS"},
        "icims": {"careers_url": "https://careers-amd.icims.com/jobs"},
        "gem": {"careers_url": "https://jobs.gem.com/bilt"},
    }
    company = _company(source_type, configs[source_type])
    response = _mock_http_response(status_code=404)

    with _patch_httpx_get(response):
        result = await probe_company_source(company, retries=1)

    assert result.valid is False
    assert result.status_code == 404
    assert result.error == "HTTP 404"


@pytest.mark.asyncio
async def test_smartrecruiters_200_valid() -> None:
    company = _company("smartrecruiters", {"company": "acme"})
    response = _mock_http_response(status_code=200, json_body={"content": []})

    with _patch_httpx_get(response):
        result = await probe_company_source(company, retries=1)

    assert result.valid is True
    assert result.status_code == 200
    assert result.error == ""


@pytest.mark.asyncio
async def test_smartrecruiters_404_invalid() -> None:
    company = _company("smartrecruiters", {"company": "missing"})
    response = _mock_http_response(status_code=404)

    with _patch_httpx_get(response):
        result = await probe_company_source(company, retries=1)

    assert result.valid is False
    assert result.status_code == 404
    assert result.error == "HTTP 404"


def test_validation_url_greenhouse() -> None:
    url = validation_url_for("greenhouse", {"board_token": "stripe"})
    assert url == "https://boards-api.greenhouse.io/v1/boards/stripe/jobs"


def test_validation_url_lever() -> None:
    url = validation_url_for("lever", {"company": "netflix"})
    assert url == "https://api.lever.co/v0/postings/netflix"


def test_careers_url_greenhouse() -> None:
    assert "boards.greenhouse.io" in careers_url_for("greenhouse", {"board_token": "airbnb"})


def test_validation_urls_new_providers() -> None:
    assert validation_url_for(
        "workday",
        {"careers_url": "https://boeing.wd1.myworkdayjobs.com/en-US/EXTERNAL_CAREERS"},
    )
    assert validation_url_for("icims", {"careers_url": "https://careers-amd.icims.com/jobs"})
    assert validation_url_for("gem", {"careers_url": "https://jobs.gem.com/bilt"})
    assert (
        validation_url_for("smartrecruiters", {"company": "acme"})
        == "https://api.smartrecruiters.com/v1/companies/acme/postings"
    )
    assert validation_expects_json("workday") is False
    assert validation_expects_json("smartrecruiters") is True


def test_looks_like_job_board_icims() -> None:
    html = '<a href="/jobs/1/job">Engineer</a> icims careers'
    assert looks_like_job_board(html, "icims")
