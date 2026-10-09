"""Pure decision logic, free of Home Assistant state so it is easy to test."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from .const import SILENCE_NO_CRITICAL


def parse_minutes(value: str | list[int] | tuple[int, ...]) -> tuple[int, ...]:
    """Parse "10, 5, 3" into (10, 5, 3). Raises ValueError on bad input."""
    if isinstance(value, (list, tuple)):
        parts = [str(v) for v in value]
    else:
        parts = [p for p in value.replace(";", ",").split(",") if p.strip()]
    minutes = tuple(int(p.strip()) for p in parts)
    if any(m < 1 for m in minutes):
        raise ValueError("snooze minutes must be positive")
    return minutes


def next_time_of_day(now: datetime, at: time) -> datetime:
    """Next occurrence of a local time of day strictly after `now`."""
    candidate = datetime.combine(now.date(), at, tzinfo=now.tzinfo)
    if candidate <= now:
        candidate += timedelta(days=1)
        candidate = datetime.combine(candidate.date(), at, tzinfo=now.tzinfo)
    return candidate


def quiet_window_end(now: datetime, start: time, end: time) -> datetime | None:
    """End of the quiet window when `now` (local, aware) is inside it, else None.

    The window may wrap midnight. start == end disables quiet hours.
    """
    if start == end:
        return None
    current = now.timetz().replace(tzinfo=None)
    if start < end:
        if not start <= current < end:
            return None
        return datetime.combine(now.date(), end, tzinfo=now.tzinfo)
    # Wraps midnight, e.g. 23:00-07:00.
    if current >= start:
        day = now.date() + timedelta(days=1)
    elif current < end:
        day = now.date()
    else:
        return None
    return datetime.combine(day, end, tzinfo=now.tzinfo)


@dataclass(frozen=True, slots=True)
class ChannelPlan:
    """Which channels a notification at some escalation level goes to."""

    phone: bool = True
    alexa: bool = False
    extra: bool = False
    critical: bool = False


def keeps_going(level: int, snoozes: tuple[int, ...]) -> bool:
    """True once the snooze ladder is used up: repeat, widen, critical."""
    return level >= len(snoozes)


def channel_plan(level: int, snoozes: tuple[int, ...], silence_mode: str) -> ChannelPlan:
    """Escalation ladder: phone, then Alexa, then every device, then critical."""
    going = keeps_going(level, snoozes)
    return ChannelPlan(
        phone=True,
        alexa=level >= 1,
        extra=level >= 2,
        critical=going and silence_mode != SILENCE_NO_CRITICAL,
    )


def snooze_for(snooze_count: int, snoozes: tuple[int, ...]) -> int | None:
    """Minutes for the next snooze, None when no snoozes are left."""
    if snooze_count < len(snoozes):
        return snoozes[snooze_count]
    return None


def repeat_after(level: int, snoozes: tuple[int, ...], repeat: int, going: int) -> int:
    """Minutes until an unanswered notification at `level` is sent again."""
    return going if keeps_going(level, snoozes) else repeat
