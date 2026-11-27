"""Shared PostgreSQL login-attempt reservation and failure accounting.

Only HMAC digests of normalized account names and trusted peer IP addresses are
persisted. The caller must provide ``request.client.host`` after explicit trusted
proxy configuration; forwarded headers are deliberately not consumed here.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Callable

from sqlalchemy import select, text, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from app.core.login_orchestration import (
    CredentialAttemptOutcome,
    LoginAttemptContext,
    LoginAttemptDecision,
)
from app.models import AuthLoginAttemptBucket


@dataclass(frozen=True, slots=True)
class LoginProtectionPolicy:
    maximum_failures: int = 5
    window: timedelta = timedelta(minutes=15)
    restriction: timedelta = timedelta(minutes=15)
    retention: timedelta = timedelta(days=1)
    cleanup_batch_size: int = 100

    def __post_init__(self) -> None:
        if type(self.maximum_failures) is not int or not 1 <= self.maximum_failures <= 100:
            raise ValueError("Login failure limit is invalid.")
        if any(not isinstance(value, timedelta) or value <= timedelta(0) for value in
               (self.window, self.restriction, self.retention)):
            raise ValueError("Login protection durations must be positive.")
        if self.retention < self.window + self.restriction:
            raise ValueError("Attempt retention must exceed the active protection period.")
        if type(self.cleanup_batch_size) is not int or not 1 <= self.cleanup_batch_size <= 1000:
            raise ValueError("Attempt cleanup batch size is invalid.")


class PostgresLoginAttemptProtection:
    """Multi-instance throttling with atomic dual-bucket reservation.

    A reservation is committed before password verification. Concurrent requests
    cannot reserve beyond the configured budget. ``finish_credential_check`` then
    releases success/infrastructure reservations or records a failure. All
    operations use short independent transactions so the counter survives the
    request transaction and backend process boundaries.
    """

    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        hmac_key: bytes,
        policy: LoginProtectionPolicy,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not isinstance(hmac_key, bytes) or len(hmac_key) < 32:
            raise ValueError("Login protection key must contain at least 32 bytes.")
        self._factory = session_factory
        self._key = bytes(hmac_key)
        self._policy = policy
        self._clock = clock

    def check(self, attempt: LoginAttemptContext) -> LoginAttemptDecision:
        account, source = self._digests(attempt)
        now = self._now()
        with self._factory() as session, session.begin():
            rows = self._lock_or_create(session, account, source, now)
            available = True
            for row in rows:
                self._refresh_window(row, now)
                if row.blocked_until is not None and now < row.blocked_until:
                    available = False
                if row.failures + row.in_flight >= self._policy.maximum_failures:
                    available = False
            if not available:
                for row in rows:
                    row.updated_at = now
                return LoginAttemptDecision.DENY
            for row in rows:
                row.in_flight += 1
                row.updated_at = now
        return LoginAttemptDecision.ALLOW

    def finish_credential_check(
        self, attempt: LoginAttemptContext, outcome: CredentialAttemptOutcome | None
    ) -> None:
        if outcome not in (None, CredentialAttemptOutcome.SUCCEEDED, CredentialAttemptOutcome.FAILED):
            raise ValueError("Credential attempt outcome is invalid.")
        account, source = self._digests(attempt)
        now = self._now()
        with self._factory() as session, session.begin():
            rows = self._locked_existing(session, account, source)
            if len(rows) != 2:
                raise RuntimeError("Login reservation is unavailable.")
            for row in rows:
                self._refresh_window(row, now)
                if row.in_flight <= 0:
                    raise RuntimeError("Login reservation is inconsistent.")
                row.in_flight -= 1
                if outcome is CredentialAttemptOutcome.FAILED:
                    row.failures += 1
                    if row.failures >= self._policy.maximum_failures:
                        row.blocked_until = now + self._policy.restriction
                row.updated_at = now
            self._cleanup_expired(session, now)

    def cleanup_expired(self, *, limit: int | None = None) -> int:
        """Bounded cleanup hook for an explicitly scheduled maintenance worker."""
        batch = self._policy.cleanup_batch_size if limit is None else limit
        if type(batch) is not int or not 1 <= batch <= self._policy.cleanup_batch_size:
            raise ValueError("Cleanup batch exceeds its configured bound.")
        now = self._now()
        return self._cleanup_in_transaction(now, batch)

    def _lock_or_create(self, session: Session, account, source, now):
        for scope, digest in (account, source):
            session.execute(pg_insert(AuthLoginAttemptBucket).values(
                scope=scope, key_digest=digest, window_started_at=now,
                failures=0, in_flight=0, updated_at=now,
            ).on_conflict_do_nothing(index_elements=[
                AuthLoginAttemptBucket.scope, AuthLoginAttemptBucket.key_digest,
            ]))
        return self._locked_existing(session, account, source)

    @staticmethod
    def _locked_existing(session: Session, account, source):
        pairs = (account, source)
        return list(session.scalars(select(AuthLoginAttemptBucket).where(
            tuple_(AuthLoginAttemptBucket.scope, AuthLoginAttemptBucket.key_digest).in_(pairs)
        ).order_by(AuthLoginAttemptBucket.scope, AuthLoginAttemptBucket.key_digest).with_for_update()).all())

    def _refresh_window(self, row: AuthLoginAttemptBucket, now: datetime) -> None:
        if row.blocked_until is not None and now >= row.blocked_until:
            row.window_started_at = now
            row.failures = 0
            row.in_flight = 0
            row.blocked_until = None
        elif now >= row.window_started_at + self._policy.window:
            row.window_started_at = now
            row.failures = 0
            row.in_flight = 0
            row.blocked_until = None

    def _cleanup_expired(self, session: Session, now: datetime) -> None:
        # Runtime deletion is restricted to a fixed-size SECURITY DEFINER function.
        session.execute(
            text("SELECT public.inventory_aios_cleanup_login_attempts(:batch, :retention)"),
            {
                "batch": self._policy.cleanup_batch_size,
                "retention": int(self._policy.retention.total_seconds()),
            },
        )

    def _cleanup_in_transaction(self, now: datetime, batch: int) -> int:
        with self._factory() as session, session.begin():
            return self._cleanup_statement(session, now, batch)

    def _cleanup_statement(self, session: Session, now: datetime, batch: int) -> int:
        # The owner-owned function clamps both values, so
        # runtime credentials cannot delete arbitrary attempt records.
        result = session.execute(
            text("SELECT public.inventory_aios_cleanup_login_attempts(:batch, :retention)"),
            {"batch": batch, "retention": int(self._policy.retention.total_seconds())},
        )
        return int(result.scalar_one())

    def _digests(self, attempt: LoginAttemptContext):
        if not isinstance(attempt, LoginAttemptContext):
            raise ValueError("Login attempt context is invalid.")
        username = attempt.username
        if (not isinstance(username, str) or not username or not username.isascii()
                or len(username) > 128 or any(not (char.isalnum() or char in "._-") for char in username)):
            raise ValueError("Login account key is invalid.")
        source = attempt.trusted_source_key
        if not isinstance(source, str) or len(source) > 64:
            raise ValueError("Trusted request source is unavailable.")
        try:
            canonical_ip = ipaddress.ip_address(source).compressed
        except ValueError:
            raise ValueError("Trusted request source is unavailable.") from None
        account_digest = hmac.new(self._key, b"account\0" + username.lower().encode("ascii"), hashlib.sha256).digest()
        source_digest = hmac.new(self._key, b"source\0" + canonical_ip.encode("ascii"), hashlib.sha256).digest()
        return ("account", account_digest), ("source", source_digest)

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise RuntimeError("Login protection clock must return timezone-aware datetimes.")
        return value.astimezone(UTC)
