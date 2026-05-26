import pytest

from app.services.ats_discovery_service import discover_ats_from_html
from app.services.company_targets_service import (
    NEEDS_ATS_ERROR,
    UNCONFIGURED_SOURCE_TYPE,
    normalize_target_row,
    parse_company_targets_csv,
    _parse_source_config,
)
from app.services.company_targets_service import CompanyTargetRow


def test_parse_source_config_empty() -> None:
    assert _parse_source_config("", 1) == {}


def test_parse_source_config_invalid_json() -> None:
    with pytest.raises(ValueError, match="invalid source_config_json"):
        _parse_source_config("{not json}", 3)


def test_parse_source_config_object() -> None:
    assert _parse_source_config('{"board_token": "stripe"}', 1) == {"board_token": "stripe"}


def test_normalize_known_greenhouse() -> None:
    row = CompanyTargetRow(
        name="Stripe",
        category="best_company",
        source_list="test",
        careers_url="https://boards.greenhouse.io/stripe",
        source_type="greenhouse",
        source_config={"board_token": "stripe"},
        priority="10",
        enabled=True,
        line_number=2,
    )
    payload = normalize_target_row(row)
    assert payload["source_type"] == "greenhouse"
    assert payload["enabled"] is True
    assert payload["last_error"] is None


def test_normalize_unknown_source_type() -> None:
    row = CompanyTargetRow(
        name="Apple",
        category="fortune_500",
        source_list="fortune_100",
        careers_url="https://www.apple.com/careers/us/",
        source_type="",
        source_config={},
        priority="50",
        enabled=True,
        line_number=3,
    )
    payload = normalize_target_row(row)
    assert payload["source_type"] == UNCONFIGURED_SOURCE_TYPE
    assert payload["enabled"] is False
    assert payload["last_error"] == NEEDS_ATS_ERROR


def test_normalize_unsupported_source_type() -> None:
    row = CompanyTargetRow(
        name="Acme",
        category="top_startup",
        source_list="manual",
        careers_url="https://jobs.workable.com/acme",
        source_type="workable",
        source_config={},
        priority="10",
        enabled=True,
        line_number=4,
    )
    payload = normalize_target_row(row)
    assert payload["source_type"] == UNCONFIGURED_SOURCE_TYPE
    assert payload["enabled"] is False


def test_parse_company_targets_csv(tmp_path) -> None:
    path = tmp_path / "targets.csv"
    path.write_text(
        "name,category,source_list,careers_url,source_type,source_config_json,priority,enabled\n"
        'TestCo,devtools,list,https://boards.greenhouse.io/testco,greenhouse,"{""board_token"": ""testco""}",1,true\n',
        encoding="utf-8",
    )
    rows = parse_company_targets_csv(path)
    assert len(rows) == 1
    assert rows[0].name == "TestCo"
    assert rows[0].source_config == {"board_token": "testco"}


def test_discover_greenhouse_in_html() -> None:
    html = '<a href="https://boards.greenhouse.io/acme">Jobs</a>'
    result = discover_ats_from_html(html, "https://acme.com/careers")
    assert result.source_type == "greenhouse"
    assert result.source_config == {"board_token": "acme"}


def test_discover_lever_in_html() -> None:
    html = 'https://jobs.lever.co/netflix/apply'
    result = discover_ats_from_html(html, "https://netflix.com/jobs")
    assert result.source_type == "lever"
    assert result.source_config == {"company": "netflix"}
