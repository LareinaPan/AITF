from app.services.pt_error_log_sanitizer import sanitize_error_message


def test_sanitize_error_message_redacts_authorization_header() -> None:
    message = "Request failed Authorization: Bearer secret-token-123"
    assert sanitize_error_message(message) == "Request failed Authorization: ***"


def test_sanitize_error_message_redacts_authorization_equals_form() -> None:
    message = "upstream rejected authorization=Bearer abc.def.ghi"
    assert sanitize_error_message(message) == "upstream rejected authorization: ***"


def test_sanitize_error_message_redacts_cookie_header() -> None:
    message = "Cookie: session=abc123; token=xyz789"
    assert sanitize_error_message(message) == "Cookie: ***"


def test_sanitize_error_message_redacts_standalone_bearer_token() -> None:
    message = "invalid token Bearer super-secret"
    assert sanitize_error_message(message) == "invalid token Bearer ***"


def test_sanitize_error_message_redacts_jwt_like_value() -> None:
    message = "token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    assert sanitize_error_message(message) == "token ***"


def test_sanitize_error_message_handles_empty_message() -> None:
    assert sanitize_error_message(None) == ""
    assert sanitize_error_message("") == ""
