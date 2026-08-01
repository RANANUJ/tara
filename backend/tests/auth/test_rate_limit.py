from datetime import UTC, datetime, timedelta

from tara_api.auth.rate_limit import InMemoryLoginRateLimiter


def test_rate_limiter_resets_after_success_and_window() -> None:
    limiter = InMemoryLoginRateLimiter(attempts=2, window=timedelta(minutes=1))
    now = datetime(2026, 8, 1, tzinfo=UTC)
    limiter.record_failure("hashed-key", now)
    limiter.record_failure("hashed-key", now)
    assert limiter.allowed("hashed-key", now) is False
    limiter.reset("hashed-key")
    assert limiter.allowed("hashed-key", now) is True
