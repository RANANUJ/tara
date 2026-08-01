"""Local single-process login rate limiter; replace for distributed deployment."""

from collections import defaultdict, deque
from datetime import datetime, timedelta


class InMemoryLoginRateLimiter:
    def __init__(self, attempts: int = 5, window: timedelta = timedelta(minutes=15)) -> None:
        self._attempts, self._window = attempts, window
        self._failures: dict[str, deque[datetime]] = defaultdict(deque)

    def allowed(self, key: str, now: datetime) -> bool:
        failures = self._failures[key]
        while failures and failures[0] + self._window <= now:
            failures.popleft()
        return len(failures) < self._attempts

    def record_failure(self, key: str, now: datetime) -> None:
        self._failures[key].append(now)

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)
