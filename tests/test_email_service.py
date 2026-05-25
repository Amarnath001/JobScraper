from app.services.email_service import EmailSendResult, _extract_error_message, _extract_provider_id


def test_extract_provider_id_from_dict() -> None:
    assert _extract_provider_id({"id": "msg_123"}) == "msg_123"


def test_extract_provider_id_from_object() -> None:
    class R:
        id = "msg_abc"

    assert _extract_provider_id(R()) == "msg_abc"


def test_extract_error_from_dict() -> None:
    assert _extract_error_message({"error": {"message": "Invalid from"}}) == "Invalid from"


def test_extract_error_when_no_id() -> None:
    msg = _extract_error_message({})
    assert msg is not None


def test_email_send_result() -> None:
    ok = EmailSendResult(ok=True, provider_id="x")
    assert ok.ok and ok.provider_id == "x"
