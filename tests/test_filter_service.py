from app.services.filter_service import score_entry_level


def test_entry_level_positive_new_grad() -> None:
    r = score_entry_level("Software Engineer — New Grad 2026", "We want a new grad.", None)
    assert r.is_entry_level
    assert "new grad" in r.matched_positive
    assert r.score > 0


def test_entry_level_negative_senior() -> None:
    r = score_entry_level("Senior Software Engineer", "Looking for senior talent.", None)
    assert not r.is_entry_level
    assert "senior" in r.matched_negative


def test_entry_level_associate_title() -> None:
    r = score_entry_level("Associate Software Engineer", None, None)
    assert r.is_entry_level
    assert "associate software engineer" in r.matched_positive


def test_years_experience_negative() -> None:
    r = score_entry_level("Engineer", "Minimum 7+ years of experience required.", None)
    assert "7+ years" in r.matched_negative
