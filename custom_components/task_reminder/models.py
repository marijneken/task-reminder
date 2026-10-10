"""Data models: task types (configuration) and tasks (running instances)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from enum import StrEnum
from typing import Any

from homeassistant.config_entries import ConfigSubentry
from homeassistant.util import dt as dt_util

from .const import (
    ADHOC_KEY,
    CONF_ALEXA_SERVICE,
    CONF_DISMISSABLE,
    CONF_DONE_ENTITY,
    CONF_DONE_STATE,
    CONF_DONE_TAG,
    CONF_DONE_THEN_ENTITY,
    CONF_DONE_THEN_STATE,
    CONF_DONE_WINDOW_MINUTES,
    CONF_DUE_ENTITY,
    CONF_DUE_STATE,
    CONF_DUE_TIME,
    CONF_DURATION_MINUTES,
    CONF_FLAG_ENTITY,
    CONF_GOOD_MOMENT_ENTITIES,
    CONF_KEEPS_GOING_MINUTES,
    CONF_KEY,
    CONF_NAME,
    CONF_PRESENCE_ENTITIES,
    CONF_QUIET_WITHOUT_FLAG,
    CONF_REPEAT_MINUTES,
    CONF_RING,
    CONF_RING_SECONDS,
    CONF_SCHEDULE_ENTITY,
    CONF_SINGLE_INSTANCE,
    CONF_SNOOZE_MINUTES,
    CONF_SOUND,
    CONF_START_DAYS_BEFORE,
    CONF_START_ENTITY,
    CONF_START_STATE,
    CONF_START_TAG,
    CONF_THEN_START,
    CONF_TIME_CRITICAL,
    DEFAULT_DONE_WINDOW_MINUTES,
    DEFAULT_KEEPS_GOING_MINUTES,
    DEFAULT_REPEAT_MINUTES,
    DEFAULT_SNOOZE_MINUTES,
    DEFAULT_START_DAYS_BEFORE,
    DEFAULT_TRIGGER_STATE,
    SILENCE_OFF,
)
from .policy import parse_minutes


@dataclass(frozen=True, slots=True)
class TaskType:
    """A task type, configured once (one config subentry per type)."""

    key: str
    name: str
    dismissable: bool = False
    time_critical: bool = False
    single_instance: bool = True
    duration_minutes: int | None = None
    due_time: time | None = None
    snooze_minutes: tuple[int, ...] = (10, 5, 3)
    repeat_minutes: int = DEFAULT_REPEAT_MINUTES
    keeps_going_minutes: int = DEFAULT_KEEPS_GOING_MINUTES
    start_entity: str | None = None
    start_state: str = DEFAULT_TRIGGER_STATE
    due_entity: str | None = None
    due_state: str = DEFAULT_TRIGGER_STATE
    done_entity: str | None = None
    done_state: str = DEFAULT_TRIGGER_STATE
    then_start: str | None = None
    flag_entity: str | None = None
    sound: str | None = None
    ring: bool = False
    ring_seconds: int | None = None
    start_tag: str | None = None
    done_tag: str | None = None
    good_moment_entities: tuple[str, ...] = ()
    schedule_entity: str | None = None
    start_days_before: int = DEFAULT_START_DAYS_BEFORE
    quiet_without_flag: bool = False
    done_then_entity: str | None = None
    done_then_state: str = DEFAULT_TRIGGER_STATE
    done_window_minutes: int = DEFAULT_DONE_WINDOW_MINUTES

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> TaskType:
        """Build from the stored subentry data."""
        due_time = data.get(CONF_DUE_TIME)
        duration = data.get(CONF_DURATION_MINUTES)
        return cls(
            key=data[CONF_KEY],
            name=data[CONF_NAME],
            dismissable=data.get(CONF_DISMISSABLE, False),
            time_critical=data.get(CONF_TIME_CRITICAL, False),
            single_instance=data.get(CONF_SINGLE_INSTANCE, True),
            duration_minutes=int(duration) if duration else None,
            due_time=time.fromisoformat(due_time) if due_time else None,
            snooze_minutes=parse_minutes(data.get(CONF_SNOOZE_MINUTES, DEFAULT_SNOOZE_MINUTES)),
            repeat_minutes=int(data.get(CONF_REPEAT_MINUTES, DEFAULT_REPEAT_MINUTES)),
            keeps_going_minutes=int(
                data.get(CONF_KEEPS_GOING_MINUTES, DEFAULT_KEEPS_GOING_MINUTES)
            ),
            start_entity=data.get(CONF_START_ENTITY) or None,
            start_state=data.get(CONF_START_STATE) or DEFAULT_TRIGGER_STATE,
            due_entity=data.get(CONF_DUE_ENTITY) or None,
            due_state=data.get(CONF_DUE_STATE) or DEFAULT_TRIGGER_STATE,
            done_entity=data.get(CONF_DONE_ENTITY) or None,
            done_state=data.get(CONF_DONE_STATE) or DEFAULT_TRIGGER_STATE,
            then_start=data.get(CONF_THEN_START) or None,
            flag_entity=data.get(CONF_FLAG_ENTITY) or None,
            sound=(data.get(CONF_SOUND) or "").strip() or None,
            ring=bool(data.get(CONF_RING, False)),
            ring_seconds=int(data[CONF_RING_SECONDS]) if data.get(CONF_RING_SECONDS) else None,
            start_tag=data.get(CONF_START_TAG) or None,
            done_tag=data.get(CONF_DONE_TAG) or None,
            good_moment_entities=tuple(data.get(CONF_GOOD_MOMENT_ENTITIES) or ()),
            schedule_entity=data.get(CONF_SCHEDULE_ENTITY) or None,
            start_days_before=int(data.get(CONF_START_DAYS_BEFORE, DEFAULT_START_DAYS_BEFORE)),
            quiet_without_flag=data.get(CONF_QUIET_WITHOUT_FLAG, False),
            done_then_entity=data.get(CONF_DONE_THEN_ENTITY) or None,
            done_then_state=data.get(CONF_DONE_THEN_STATE) or DEFAULT_TRIGGER_STATE,
            done_window_minutes=int(
                data.get(CONF_DONE_WINDOW_MINUTES) or DEFAULT_DONE_WINDOW_MINUTES
            ),
        )

    @classmethod
    def from_subentry(cls, subentry: ConfigSubentry) -> TaskType:
        """Build from a config subentry."""
        return cls.from_data(dict(subentry.data))


# Ad hoc reminders and timers: someone asked for this exact moment, so it may
# break quiet hours, end with Done (there is nothing to dismiss instead of do),
# and any number can run at once.
ADHOC_TYPE = TaskType(
    key=ADHOC_KEY,
    name="Reminder",
    dismissable=False,
    time_critical=True,
    single_instance=False,
    ring=True,  # a timer or alarm: keeps going off until you stop it
)


@dataclass(frozen=True, slots=True)
class Room:
    """A room with presence sensors and (optionally) an Alexa speaker."""

    key: str
    name: str
    presence_entities: tuple[str, ...] = ()
    alexa_service: str | None = None

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> Room:
        """Build from the stored subentry data."""
        return cls(
            key=data[CONF_KEY],
            name=data[CONF_NAME],
            presence_entities=tuple(data.get(CONF_PRESENCE_ENTITIES) or ()),
            alexa_service=data.get(CONF_ALEXA_SERVICE) or None,
        )


class TaskStatus(StrEnum):
    """Task lifecycle. `due` is not a stored state: a due task is notified at
    once (`notifying`) or held (`held`)."""

    ARMED = "armed"
    NOTIFYING = "notifying"
    SNOOZED = "snoozed"
    HELD = "held"


def _dump(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _load(value: str | None) -> datetime | None:
    return dt_util.parse_datetime(value) if value else None


@dataclass(slots=True)
class Task:
    """A running instance of a task type. All times are absolute (UTC)."""

    id: str
    type_key: str
    title: str
    created_at: datetime
    status: TaskStatus = TaskStatus.ARMED
    message: str | None = None
    due_at: datetime | None = None
    next_at: datetime | None = None
    snooze_count: int = 0
    level: int = 0
    held_reason: str | None = None
    away_notified: bool = False
    last_notified_at: datetime | None = None
    ring_at: datetime | None = None  # next re-trigger of the sound
    ring_until: datetime | None = None  # stop re-triggering after this
    ring_tag: str | None = None  # tag of the latest re-triggered notification (refresh style)
    ring_count: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialise for storage."""
        return {
            "id": self.id,
            "type_key": self.type_key,
            "title": self.title,
            "created_at": _dump(self.created_at),
            "status": self.status.value,
            "message": self.message,
            "due_at": _dump(self.due_at),
            "next_at": _dump(self.next_at),
            "snooze_count": self.snooze_count,
            "level": self.level,
            "held_reason": self.held_reason,
            "away_notified": self.away_notified,
            "last_notified_at": _dump(self.last_notified_at),
            "ring_at": _dump(self.ring_at),
            "ring_until": _dump(self.ring_until),
            "ring_tag": self.ring_tag,
            "ring_count": self.ring_count,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Task:
        """Restore from storage."""
        return cls(
            id=data["id"],
            type_key=data["type_key"],
            title=data["title"],
            created_at=_load(data["created_at"]) or dt_util.utcnow(),
            status=TaskStatus(data["status"]),
            message=data.get("message"),
            due_at=_load(data.get("due_at")),
            next_at=_load(data.get("next_at")),
            snooze_count=data.get("snooze_count", 0),
            level=data.get("level", 0),
            held_reason=data.get("held_reason"),
            away_notified=data.get("away_notified", False),
            last_notified_at=_load(data.get("last_notified_at")),
            ring_at=_load(data.get("ring_at")),
            ring_until=_load(data.get("ring_until")),
            ring_tag=data.get("ring_tag"),
            ring_count=data.get("ring_count", 0),
            extra=data.get("extra", {}),
        )

    def as_attributes(self) -> dict[str, Any]:
        """Compact form for entity attributes."""
        return {
            "id": self.id,
            "type": self.type_key,
            "title": self.title,
            "status": self.status.value,
            "due_at": _dump(self.due_at),
            "next_at": _dump(self.next_at),
            "snooze_count": self.snooze_count,
            "level": self.level,
            "held_reason": self.held_reason,
        }


@dataclass(slots=True)
class Silence:
    """Silencing state; a mode other than `off` always has an end time."""

    mode: str = SILENCE_OFF
    until: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialise for storage."""
        return {"mode": self.mode, "until": _dump(self.until)}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Silence:
        """Restore from storage."""
        if not data:
            return cls()
        return cls(mode=data.get("mode", SILENCE_OFF), until=_load(data.get("until")))
