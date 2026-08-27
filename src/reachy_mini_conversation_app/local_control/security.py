"""In-memory PIN sessions for the LAN control surface."""

import hmac
import time
import hashlib
import secrets
from typing import Callable


class AuthenticationError(ValueError):
    """Reject an invalid local-control login."""


class SessionAuthorizer:
    """Issue short-lived sessions after device-PIN verification."""

    def __init__(
        self,
        pin: str,
        session_ttl_s: int = 12 * 60 * 60,
        max_sessions: int = 8,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Store only a one-way PIN digest and in-memory session tokens."""
        if not pin or session_ttl_s <= 0 or max_sessions <= 0:
            raise ValueError("invalid_session_configuration")
        self._pin_digest = hashlib.sha256(pin.encode("utf-8")).digest()
        self._session_ttl_s = session_ttl_s
        self._max_sessions = max_sessions
        self._clock = clock
        self._sessions: dict[str, float] = {}

    def __repr__(self) -> str:
        """Return diagnostics without authentication material."""
        return f"SessionAuthorizer(active_sessions={len(self._sessions)})"

    def _purge_expired(self) -> None:
        now = self._clock()
        for token, expires_at in list(self._sessions.items()):
            if expires_at <= now:
                self._sessions.pop(token, None)

    def authenticate(self, pin: str) -> str:
        """Return an opaque session token for a matching device PIN."""
        candidate = hashlib.sha256(pin.encode("utf-8")).digest()
        if not hmac.compare_digest(candidate, self._pin_digest):
            raise AuthenticationError("invalid_pin")
        self._purge_expired()
        while len(self._sessions) >= self._max_sessions:
            self._sessions.pop(next(iter(self._sessions)))
        token = secrets.token_urlsafe(32)
        self._sessions[token] = self._clock() + self._session_ttl_s
        return token

    def is_valid(self, token: str) -> bool:
        """Return whether an opaque session token remains active."""
        self._purge_expired()
        return token in self._sessions

    def revoke(self, token: str) -> None:
        """Remove one active session token."""
        self._sessions.pop(token, None)
