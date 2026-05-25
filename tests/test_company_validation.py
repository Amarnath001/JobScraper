from app.utils.source_urls import careers_url_for, validation_url_for


def test_validation_url_greenhouse() -> None:
    url = validation_url_for("greenhouse", {"board_token": "stripe"})
    assert url == "https://boards-api.greenhouse.io/v1/boards/stripe/jobs"


def test_validation_url_lever() -> None:
    url = validation_url_for("lever", {"company": "netflix"})
    assert url == "https://api.lever.co/v0/postings/netflix"


def test_careers_url_greenhouse() -> None:
    assert "boards.greenhouse.io" in careers_url_for("greenhouse", {"board_token": "airbnb"})
