from app.services.ingest_service import IngestResult, merge_ingest_results
from app.services.scrape_runner_service import PipelineSummary


def test_merge_ingest_results_accumulates() -> None:
    total = IngestResult()
    a = IngestResult(
        jobs_seen_total=10,
        jobs_inserted_total=3,
        jobs_inserted_software_related=2,
        jobs_inserted_entry_level=2,
        jobs_inserted_digest_eligible=1,
        jobs_skipped_international=4,
        jobs_skipped_non_software=1,
        jobs_skipped_non_entry_level=1,
    )
    b = IngestResult(
        jobs_seen_total=5,
        jobs_inserted_total=2,
        jobs_inserted_digest_eligible=2,
        jobs_skipped_international=1,
    )
    merge_ingest_results(total, a)
    merge_ingest_results(total, b)
    assert total.jobs_seen_total == 15
    assert total.jobs_inserted_total == 5
    assert total.jobs_inserted_digest_eligible == 3
    assert total.jobs_skipped_international == 5
    assert total.new_jobs_created == 5
    assert total.jobs_seen == 15


def test_pipeline_summary_legacy_aliases() -> None:
    summary = PipelineSummary()
    summary.ingest.jobs_seen_total = 100
    summary.ingest.jobs_inserted_total = 12
    summary.ingest.jobs_inserted_digest_eligible = 4
    assert summary.jobs_seen == 100
    assert summary.new_jobs_created == 12
    assert summary.jobs_inserted_total == 12
