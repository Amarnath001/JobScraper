from app.services.ats_discovery_service import (
    ATSDiscoveryCandidate,
    _pick_best,
    _result_from_candidates,
    _unknown_result,
    classify_discovery_bucket,
    collect_ats_candidates,
    discover_ats_from_html,
    extract_candidate_links,
)


def test_extract_candidate_links_prioritizes_ats_hosts() -> None:
    html = """
    <a href="/about">About</a>
    <a href="https://careers.intuit.com/us/en/search-jobs">Search jobs</a>
    <a href="https://careers-intuit.icims.com/jobs/search">iCIMS search</a>
  """
    links = extract_candidate_links(html, "https://www.intuit.com/careers/")
    assert "icims.com" in links[0]


def test_no_candidates_returns_unknown_result() -> None:
    result = _unknown_result(("https://example.com/careers",), "https://example.com/careers")
    assert result.confidence == "none"
    assert result.reason == "No supported ATS pattern detected"
    assert result.source_type == ""
    assert result.provider_detected is None
    assert classify_discovery_bucket(result) == "still_unknown"


def test_workday_provider_returns_configured_supported() -> None:
    candidates = [
        ATSDiscoveryCandidate(
            "workday",
            90,
            "workday",
            {"careers_url": "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite"},
            "Workday host detected",
        )
    ]
    result = _result_from_candidates(
        candidates,
        ["https://www.nvidia.com/careers/"],
        "https://www.nvidia.com/careers/",
    )
    assert result.supported
    assert result.source_type == "workday"
    assert classify_discovery_bucket(result) == "configured_supported"


def test_unsupported_provider_returns_detected_unsupported() -> None:
    candidates = [
        ATSDiscoveryCandidate(
            "oracle",
            86,
            None,
            {"careers_url": "https://egug.fa.us2.oraclecloud.com/hcmUI/CandidateExperience"},
            "Oracle HCM detected",
        )
    ]
    result = _result_from_candidates(
        candidates,
        ["https://www.example.com/careers/"],
        "https://www.example.com/careers/",
    )
    assert not result.supported
    assert result.provider_detected == "oracle"
    assert classify_discovery_bucket(result) == "detected_unsupported"


def test_supported_provider_returns_configured_supported() -> None:
    candidates = collect_ats_candidates(
        'iframe src="https://jobs.lever.co/netflix"',
        "https://jobs.netflix.com/",
    )
    result = _result_from_candidates(candidates, ["https://jobs.netflix.com/"], "https://jobs.netflix.com/")
    assert result.supported
    assert result.source_type == "lever"
    assert classify_discovery_bucket(result) == "configured_supported"


def test_pick_best_never_accepts_strings() -> None:
    candidates = collect_ats_candidates(
        "https://boards.greenhouse.io/acme",
        "https://acme.com/careers",
    )
    best = _pick_best(candidates)
    assert best is not None
    assert best.source_type == "greenhouse"


def test_discover_greenhouse_from_embedded_board() -> None:
    html = "Apply at https://boards.greenhouse.io/acme/jobs/123"
    result = discover_ats_from_html(html, "https://acme.com/careers")
    assert result.supported
    assert result.source_type == "greenhouse"
    assert result.source_config == {"board_token": "acme"}


def test_discover_gem_supported() -> None:
    html = '<a href="https://jobs.gem.com/bilt/4509720004">Jobs</a>'
    result = discover_ats_from_html(html, "https://www.bilt.com/careers")
    assert result.supported
    assert result.source_type == "gem"
    assert result.source_config["careers_url"] == "https://jobs.gem.com/bilt"
    assert classify_discovery_bucket(result) == "configured_supported"


def test_summary_bucket_for_fetch_failure() -> None:
    from app.services.ats_discovery_service import AtsDiscoveryResult

    result = AtsDiscoveryResult(fetch_failed=True, reason="Failed to fetch careers landing page: 403")
    assert classify_discovery_bucket(result) == "errors"


def test_discovery_script_summary_keys() -> None:
    from scripts.discover_unconfigured_companies import SUMMARY_KEYS, _empty_summary

    summary = _empty_summary()
    assert "errors" in summary
    assert "error" not in summary
    summary["errors"] += 1
    summary["configured_supported"] += 1
    assert summary["errors"] == 1
