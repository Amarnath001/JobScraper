import json
import logging

import pytest

from app.services.ingest_service import IngestResult
from app.services.scrape_runner_service import PipelineSummary
from scripts import ci_summary


def test_log_scrape_summary_json_fields(capsys, caplog: pytest.LogCaptureFixture) -> None:
    summary = PipelineSummary(companies_scanned=3)
    summary.ingest = IngestResult(
        jobs_seen_total=50,
        jobs_inserted_total=10,
        jobs_inserted_software_related=6,
        jobs_inserted_entry_level=5,
        jobs_inserted_digest_eligible=4,
        jobs_skipped_international=12,
        jobs_skipped_non_software=3,
        jobs_skipped_non_entry_level=2,
    )
    with caplog.at_level(logging.INFO):
        caplog.clear()
        ci_summary.log_scrape_summary(summary)
    payload = json.loads(capsys.readouterr().out)
    assert payload["jobs_seen_total"] == 50
    assert payload["new_swe_jobs_created"] == 6
    assert payload["new_entry_level_swe_jobs_created"] == 4
    assert payload["jobs_skipped_international"] == 12
    assert payload["new_jobs_created"] == 10


def test_log_digest_summary_json_fields(capsys, caplog: pytest.LogCaptureFixture) -> None:
    summary = PipelineSummary(
        digest_candidates_count=7,
        digest_swe_jobs_count=7,
        digest_entry_level_swe_jobs_count=7,
        digest_window="last 4 hours (UTC)",
        emails_sent=1,
        emails_attempted=1,
    )
    with caplog.at_level(logging.INFO):
        caplog.clear()
        ci_summary.log_digest_summary(summary)
    payload = json.loads(capsys.readouterr().out)
    assert payload["digest_candidates_count"] == 7
    assert payload["digest_entry_level_swe_jobs_count"] == 7
    assert payload["digest_jobs_count"] == 7
