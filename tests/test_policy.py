"""Pure policy tests."""

from datetime import UTC, datetime, time

import pytest

from custom_components.task_reminder.policy import (
    channel_plan,
    keeps_going,
    next_time_of_day,
    parse_minutes,
    quiet_window_end,
    repeat_after,
    snooze_for,
)

SNOOZES = (10, 5, 3)


def test_parse_minutes() -> None:
    assert parse_minutes("10, 5, 3") == (10, 5, 3)
    assert parse_minutes("10;5") == (10, 5)
    assert parse_minutes("") == ()
    with pytest.raises(ValueError):
        parse_minutes("10, abc")
    with pytest.raises(ValueError):
        parse_minutes("0")


def test_snoozes_shrink_then_run_out() -> None:
    assert [snooze_for(i, SNOOZES) for i in range(4)] == [10, 5, 3, None]


def test_escalation_ladder() -> None:
    plans = [channel_plan(level, SNOOZES, "off") for level in range(5)]
    assert [(p.phone, p.alexa, p.extra, p.critical) for p in plans] == [
        (True, False, False, False),
        (True, True, False, False),
        (True, True, True, False),
        (True, True, True, True),
        (True, True, True, True),
    ]


def test_no_critical_mode_downgrades() -> None:
    assert channel_plan(5, SNOOZES, "no_critical").critical is False
    assert channel_plan(5, SNOOZES, "no_critical").extra is True


def test_keeps_going_repeat_interval() -> None:
    assert not keeps_going(2, SNOOZES)
    assert repeat_after(2, SNOOZES, 5, 2) == 5
    assert repeat_after(3, SNOOZES, 5, 2) == 2


def test_next_time_of_day() -> None:
    now = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
    assert next_time_of_day(now, time(18, 0)) == datetime(2026, 10, 9, 18, 0, tzinfo=UTC)
    assert next_time_of_day(now, time(8, 0)) == datetime(2026, 10, 10, 8, 0, tzinfo=UTC)
    assert next_time_of_day(now, time(12, 0)) == datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("hour", "expected_day", "expected_hour"),
    [
        (23, 10, 7),  # evening: ends tomorrow
        (2, 9, 7),  # small hours: ends today
        (12, None, None),  # day time: outside
    ],
)
def test_quiet_window_wrapping_midnight(hour, expected_day, expected_hour) -> None:
    now = datetime(2026, 10, 9, hour, 30, tzinfo=UTC)
    end = quiet_window_end(now, time(23), time(7))
    if expected_day is None:
        assert end is None
    else:
        assert end == datetime(2026, 10, expected_day, expected_hour, tzinfo=UTC)


def test_quiet_window_same_day_and_disabled() -> None:
    now = datetime(2026, 10, 9, 13, 0, tzinfo=UTC)
    assert quiet_window_end(now, time(12), time(14)) == datetime(2026, 10, 9, 14, tzinfo=UTC)
    assert quiet_window_end(now, time(14), time(15)) is None
    assert quiet_window_end(now, time(9), time(9)) is None
