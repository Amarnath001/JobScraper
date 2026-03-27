from app.utils.hashing import compute_job_fingerprint


def test_fingerprint_stable() -> None:
    a = compute_job_fingerprint(
        company_name="Acme",
        title="Software Engineer I",
        location="Remote",
        url="https://example.com/jobs/1",
        external_job_id="abc",
    )
    b = compute_job_fingerprint(
        company_name="acme",
        title="  software engineer i  ",
        location="remote",
        url="https://example.com/jobs/1",
        external_job_id="abc",
    )
    assert a == b


def test_fingerprint_changes_on_url() -> None:
    a = compute_job_fingerprint(
        company_name="Acme",
        title="SWE",
        location=None,
        url="https://a.com/1",
        external_job_id=None,
    )
    b = compute_job_fingerprint(
        company_name="Acme",
        title="SWE",
        location=None,
        url="https://a.com/2",
        external_job_id=None,
    )
    assert a != b
