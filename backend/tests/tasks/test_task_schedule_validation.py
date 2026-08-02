from datetime import UTC, datetime

import pytest

from tara_api.domain.tasks import ScheduleDefinition


def test_one_time_and_hourly_recurrence_calculate_utc_next_runs() -> None:
    schedule = ScheduleDefinition("Asia/Kolkata", datetime(2026, 8, 5, 9, tzinfo=UTC), interval_minutes=60, occurrence_limit=2)
    assert schedule.next_after(datetime(2026, 8, 5, 9, 30, tzinfo=UTC)) == datetime(2026, 8, 5, 10, tzinfo=UTC)


@pytest.mark.parametrize(
    "kwargs",
    (
        {"timezone": "Invalid/Zone"},
        {"timezone": "UTC", "interval_minutes": 10},
        {"timezone": "UTC", "occurrence_limit": 1},
        {"timezone": "UTC", "interval_minutes": 60, "occurrence_limit": 366},
    ),
)
def test_invalid_schedules_are_rejected(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        ScheduleDefinition(run_at=datetime(2026, 8, 5, 9, tzinfo=UTC), **kwargs)  # type: ignore[arg-type]
