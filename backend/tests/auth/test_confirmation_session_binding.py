import pytest


@pytest.mark.xfail(reason="M4 did not persist owner-session binding on M3 confirmation records.", strict=True)
def test_confirmation_session_binding_is_not_yet_available() -> None:
    raise AssertionError("Session-bound confirmations require a reviewed schema extension.")
