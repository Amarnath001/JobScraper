import pytest

from app.services.filter_service import classify_job, score_entry_level


@pytest.mark.parametrize(
    "title",
    [
        "Sales Development Representative - New Grad",
        "Product Manager, New Grad",
        "Sales Engineer, University Graduate",
        "Customer Success Associate, Entry Level",
        "Account Executive, Early Career",
        "Business Analyst Intern",
    ],
)
def test_non_swe_roles_rejected(title: str) -> None:
    r = classify_job(title, None, None)
    assert not r.is_software_engineering_related
    assert r.non_software_indicators_matched
    assert r.rejection_reason == "non_software_role_in_title"


@pytest.mark.parametrize(
    "title",
    [
        "Software Engineer, New Grad",
        "Backend Engineer I",
        "Frontend Software Engineer - University Grad",
        "Machine Learning Engineer, Early Career",
        "Site Reliability Engineer I",
        "Data Engineer I",
        "Infrastructure Engineer, University Graduate",
    ],
)
def test_swe_entry_level_accepted(title: str) -> None:
    r = classify_job(title, None, None)
    assert r.is_software_engineering_related
    assert r.is_entry_level_related
    assert r.is_digest_eligible
    assert r.rejection_reason is None


def test_senior_swe_rejected_entry_level() -> None:
    r = classify_job("Senior Software Engineer", "Looking for senior talent.", None)
    assert r.is_software_engineering_related
    assert not r.is_entry_level_related
    assert r.rejection_reason == "not_entry_level"


def test_entry_level_positive_new_grad() -> None:
    r = score_entry_level("Software Engineer — New Grad 2026", "We want a new grad.", None)
    assert r.is_entry_level
    assert "new grad" in r.matched_positive


def test_entry_level_associate_title() -> None:
    r = score_entry_level("Associate Software Engineer", None, None)
    assert r.is_entry_level
    assert "associate software engineer" in r.matched_positive


def test_filter_result_fields_populated() -> None:
    r = classify_job("Software Engineer I", "campus hire", None)
    assert r.software_indicators_matched
    assert isinstance(r.entry_level_indicators_matched, list)
