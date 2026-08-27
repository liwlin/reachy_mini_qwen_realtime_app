"""Session authentication tests for the local mobile controller."""

import pytest

from reachy_mini_conversation_app.local_control.security import (
    SessionAuthorizer,
    AuthenticationError,
)


def test_session_authorizer_accepts_pin_and_revokes_token() -> None:
    """A valid device PIN creates an opaque revocable session."""
    authorizer = SessionAuthorizer("12345", session_ttl_s=60)

    token = authorizer.authenticate("12345")

    assert len(token) >= 32
    assert authorizer.is_valid(token) is True
    authorizer.revoke(token)
    assert authorizer.is_valid(token) is False


def test_session_authorizer_rejects_wrong_pin_without_disclosure() -> None:
    """Authentication errors reveal neither expected nor supplied PIN."""
    authorizer = SessionAuthorizer("12345", session_ttl_s=60)

    with pytest.raises(AuthenticationError) as captured:
        authorizer.authenticate("99999")

    assert str(captured.value) == "invalid_pin"
    assert "12345" not in repr(authorizer)
    assert "99999" not in repr(captured.value)


def test_session_authorizer_expires_tokens() -> None:
    """Expired sessions are rejected and removed."""
    now = [10.0]
    authorizer = SessionAuthorizer("12345", session_ttl_s=5, clock=lambda: now[0])
    token = authorizer.authenticate("12345")

    now[0] = 16.0

    assert authorizer.is_valid(token) is False


def test_session_authorizer_bounds_active_sessions() -> None:
    """Creating sessions evicts the oldest token at the configured limit."""
    now = [0.0]
    authorizer = SessionAuthorizer("12345", session_ttl_s=60, max_sessions=2, clock=lambda: now[0])
    first = authorizer.authenticate("12345")
    now[0] += 1
    second = authorizer.authenticate("12345")
    now[0] += 1
    third = authorizer.authenticate("12345")

    assert authorizer.is_valid(first) is False
    assert authorizer.is_valid(second) is True
    assert authorizer.is_valid(third) is True
