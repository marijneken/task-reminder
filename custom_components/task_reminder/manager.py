"""The task engine: lifecycle, persistence, scheduling, holds and triggers."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timedelta
from typing import Any
from uuid import uuid4

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    callback,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_track_point_in_utc_time,
    async_track_state_change_event,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    ACTION_DISMISS,
    ACTION_DONE,
    ACTION_PREFIX,
    ACTION_SNOOZE,
    CONF_ALEXA_SERVICES,
    CONF_EXTRA_SERVICES,
    CONF_PERSON,
    CONF_PHONE_SERVICES,
    CONF_QUIET_END,
    CONF_QUIET_START,
    DEFAULT_QUIET_END,
    DEFAULT_QUIET_START,
    DELIVERY_RETRY,
    EVENT_FINISHED,
    EVENT_MOBILE_ACTION,
    HOLD_AWAY,
    HOLD_QUIET,
    HOLD_SILENT,
    SIGNAL_UPDATE,
    SILENCE_OFF,
    SILENCE_SILENT,
    STORAGE_KEY,
    STORAGE_VERSION,
    SUMMARY_GRACE,
)
from .models import Silence, Task, TaskStatus, TaskType
from .notifier import Notifier
from .policy import (
    channel_plan,
    next_time_of_day,
    quiet_window_end,
    repeat_after,
    snooze_for,
)

_LOGGER = logging.getLogger(__name__)

ACTIVE_STATES_AFTER_DUE = (TaskStatus.NOTIFYING, TaskStatus.SNOOZED, TaskStatus.HELD)


class TaskManager:
    """Owns all task state. Every mutation is saved before returning, and every
    time is absolute, so a restart loses nothing."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.tasks: dict[str, Task] = {}
        self.silence = Silence()
        self.pending_until: datetime | None = None
        self.types: dict[str, TaskType] = {}
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._lock = asyncio.Lock()
        self._unsub_timer: CALLBACK_TYPE | None = None
        self._unsubs: list[CALLBACK_TYPE] = []
        self._started = False
        self.notifier = self._build_notifier()
        self._reload_types()

    # -- settings ---------------------------------------------------------

    @property
    def settings(self) -> dict[str, Any]:
        """Entry data with options on top."""
        return {**self.entry.data, **self.entry.options}

    def _build_notifier(self) -> Notifier:
        s = self.settings
        return Notifier(
            self.hass,
            list(s.get(CONF_PHONE_SERVICES, [])),
            list(s.get(CONF_ALEXA_SERVICES, [])),
            list(s.get(CONF_EXTRA_SERVICES, [])),
        )

    def _reload_types(self) -> None:
        self.types = {}
        for subentry in self.entry.subentries.values():
            try:
                task_type = TaskType.from_subentry(subentry)
            except (KeyError, ValueError):
                _LOGGER.warning("Ignoring invalid task type %s", subentry.title)
                continue
            self.types[task_type.key] = task_type

    def _quiet_times(self) -> tuple[time, time]:
        s = self.settings
        return (
            time.fromisoformat(s.get(CONF_QUIET_START, DEFAULT_QUIET_START)),
            time.fromisoformat(s.get(CONF_QUIET_END, DEFAULT_QUIET_END)),
        )

    # -- lifecycle --------------------------------------------------------

    async def async_load(self) -> None:
        """Load saved state and subscribe to triggers. Does not notify yet."""
        data = await self._store.async_load() or {}
        for raw in data.get("tasks", []):
            try:
                task = Task.from_dict(raw)
            except (KeyError, ValueError):
                _LOGGER.warning("Dropping unreadable stored task: %s", raw)
                continue
            self.tasks[task.id] = task
        self.silence = Silence.from_dict(data.get("silence"))
        self._subscribe()

    async def async_start(self, _hass: HomeAssistant | None = None) -> None:
        """Run once Home Assistant has started: anything that became due while
        it was down fires now, when the notify services exist."""
        self._started = True
        await self.async_process()

    def async_unload(self) -> None:
        """Stop timers and listeners (state is already saved)."""
        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    def _subscribe(self) -> None:
        by_entity: dict[str, list[tuple[str, TaskType, str]]] = {}
        for task_type in self.types.values():
            for kind, entity, state in (
                ("start", task_type.start_entity, task_type.start_state),
                ("due", task_type.due_entity, task_type.due_state),
                ("done", task_type.done_entity, task_type.done_state),
            ):
                if entity:
                    by_entity.setdefault(entity, []).append((kind, task_type, state))

        if by_entity:

            @callback
            def _changed(event: Event[EventStateChangedData]) -> None:
                new, old = event.data["new_state"], event.data["old_state"]
                if new is None or new.state in ("unavailable", "unknown"):
                    return
                if old is not None and old.state == new.state:
                    return
                for kind, task_type, state in by_entity.get(event.data["entity_id"], []):
                    if new.state == state:
                        self.hass.async_create_task(self._async_trigger(kind, task_type))

            self._unsubs.append(
                async_track_state_change_event(self.hass, list(by_entity), _changed)
            )

        person = self.settings.get(CONF_PERSON)
        if person:

            @callback
            def _person_changed(event: Event[EventStateChangedData]) -> None:
                self.hass.async_create_task(self.async_process(arrival_check=True))

            self._unsubs.append(
                async_track_state_change_event(self.hass, [person], _person_changed)
            )

        self._unsubs.append(self.hass.bus.async_listen(EVENT_MOBILE_ACTION, self._on_action))

    # -- persistence & scheduling ----------------------------------------

    async def _async_save(self) -> None:
        await self._store.async_save(
            {
                "tasks": [t.to_dict() for t in self.tasks.values()],
                "silence": self.silence.to_dict(),
            }
        )

    async def _commit(self) -> None:
        """Save, reschedule and tell the entities."""
        await self._async_save()
        self._schedule()
        async_dispatcher_send(self.hass, SIGNAL_UPDATE)

    def _schedule(self) -> None:
        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None
        if not self._started:
            return
        times = [t.next_at for t in self.tasks.values() if t.next_at]
        if self.silence.mode != SILENCE_OFF and self.silence.until:
            times.append(self.silence.until)
        if not times:
            return
        self._unsub_timer = async_track_point_in_utc_time(self.hass, self._on_timer, min(times))

    async def _on_timer(self, _now: datetime) -> None:
        self._unsub_timer = None
        await self.async_process()

    # -- processing -------------------------------------------------------

    async def async_process(self, arrival_check: bool = False) -> None:
        """Fire everything that is due. Safe to call at any time."""
        if not self._started:
            return
        async with self._lock:
            now = dt_util.utcnow()
            if self.silence.mode != SILENCE_OFF and (
                self.silence.until is None or self.silence.until <= now
            ):
                self.silence = Silence()
                await self._release_silent(now)
            if arrival_check and not self._away():
                for task in self.tasks.values():
                    if task.status is TaskStatus.HELD and task.held_reason == HOLD_AWAY:
                        task.next_at = now
                        task.held_reason = None
            for task in sorted(self.tasks.values(), key=lambda t: t.next_at or now):
                if task.next_at and task.next_at <= now and task.id in self.tasks:
                    await self._fire(task, now)
                await self._commit()

    def _away(self) -> bool:
        person = self.settings.get(CONF_PERSON)
        state = self.hass.states.get(person) if person else None
        # Never act on a guess: unknown/unavailable counts as home.
        return state is not None and state.state not in ("home", "unknown", "unavailable")

    def _hold(
        self, task: Task, task_type: TaskType, now: datetime
    ) -> tuple[str, datetime | None] | None:
        if self.silence.mode == SILENCE_SILENT and self.silence.until:
            return HOLD_SILENT, self.silence.until
        if not task_type.time_critical:
            start, end = self._quiet_times()
            quiet_end = quiet_window_end(dt_util.as_local(now), start, end)
            if quiet_end:
                return HOLD_QUIET, dt_util.as_utc(quiet_end)
        if self._away():
            return HOLD_AWAY, None
        return None

    async def _fire(self, task: Task, now: datetime) -> None:
        """A task's next_at has passed: notify it, or hold it."""
        task_type = self.types.get(task.type_key)
        if task_type is None:
            _LOGGER.warning("Task %s has no type %s any more; dropping", task.id, task.type_key)
            await self._finish(task, "dismissed", chain=False)
            return

        hold = self._hold(task, task_type, now)
        if hold:
            reason, until = hold
            entering = task.status is not TaskStatus.HELD or task.held_reason != reason
            task.status = TaskStatus.HELD
            task.held_reason = reason
            task.next_at = until
            if entering and reason == HOLD_AWAY and not task.away_notified:
                task.away_notified = True
                await self.notifier.async_quiet(
                    task_id=task.id,
                    title=task.title,
                    message=task.message or f"{task.title} is due (you're away)",
                )
            return

        snoozes = task_type.snooze_minutes
        plan = channel_plan(task.level, snoozes, self.silence.mode)
        text = task.message or (
            f"{task.title} is due" if task.level == 0 else f"{task.title} is still waiting"
        )
        delivered = await self.notifier.async_remind(
            task_id=task.id,
            title=task.title,
            message=text,
            plan=plan,
            time_critical=task_type.time_critical,
            can_snooze=snooze_for(task.snooze_count, snoozes) is not None,
            dismissable=task_type.dismissable,
        )
        if self.notifier.configured and delivered == 0:
            _LOGGER.warning("No channel delivered %s; retrying shortly", task.title)
            task.next_at = now + DELIVERY_RETRY
            return

        task.held_reason = None
        task.status = TaskStatus.NOTIFYING
        task.last_notified_at = now
        task.level += 1
        task.next_at = now + timedelta(
            minutes=repeat_after(
                task.level, snoozes, task_type.repeat_minutes, task_type.keeps_going_minutes
            )
        )

    async def _release_silent(self, now: datetime) -> None:
        """A silent period ended (or was cancelled): deliver what piled up."""
        held = [
            t
            for t in self.tasks.values()
            if t.status is TaskStatus.HELD and t.held_reason == HOLD_SILENT
        ]
        if len(held) > 1:
            await self.notifier.async_summary(
                [f"{len(held)} reminders while you were away from notifications:"]
                + [f"• {t.title}" for t in held]
            )
        for task in held:
            task.next_at = now + (SUMMARY_GRACE if len(held) > 1 else timedelta(0))
            task.held_reason = None

    # -- starting, finishing ---------------------------------------------

    def _active(self, type_key: str) -> list[Task]:
        return [t for t in self.tasks.values() if t.type_key == type_key]

    async def async_start_task(
        self,
        type_key: str,
        *,
        title: str | None = None,
        message: str | None = None,
        due_in: timedelta | None = None,
        due_at: datetime | None = None,
    ) -> Task:
        """Start a task of a type. Single-instance types return the running one."""
        async with self._lock:
            task = self._start_locked(type_key, title, message, due_in, due_at)
            await self._commit()
        await self.async_process()
        return task

    def _start_locked(
        self,
        type_key: str,
        title: str | None = None,
        message: str | None = None,
        due_in: timedelta | None = None,
        due_at: datetime | None = None,
    ) -> Task:
        task_type = self.types.get(type_key)
        if task_type is None:
            raise ServiceValidationError(f"Unknown task type: {type_key}")
        if task_type.single_instance and (running := self._active(type_key)):
            return running[0]

        now = dt_util.utcnow()
        if due_at is None:
            if due_in is not None:
                due_at = now + due_in
            elif task_type.duration_minutes:
                due_at = now + timedelta(minutes=task_type.duration_minutes)
            elif task_type.due_time:
                due_at = dt_util.as_utc(next_time_of_day(dt_util.as_local(now), task_type.due_time))
            elif task_type.due_entity:
                due_at = None  # waits for the due trigger
            else:
                due_at = now
        task = Task(
            id=uuid4().hex[:8],
            type_key=type_key,
            title=title or task_type.name,
            created_at=now,
            message=message,
            due_at=due_at,
            next_at=due_at,
        )
        self.tasks[task.id] = task
        return task

    async def _finish(self, task: Task, outcome: str, *, chain: bool = True) -> None:
        self.tasks.pop(task.id, None)
        await self.notifier.async_clear(task.id)
        self.hass.bus.async_fire(
            EVENT_FINISHED,
            {"task_id": task.id, "type": task.type_key, "title": task.title, "outcome": outcome},
        )
        task_type = self.types.get(task.type_key)
        if chain and outcome == "done" and task_type and task_type.then_start:
            try:
                self._start_locked(task_type.then_start)
            except ServiceValidationError:
                _LOGGER.warning("then_start type %s does not exist", task_type.then_start)

    def resolve(self, task_id: str | None, type_key: str | None) -> list[Task]:
        """Tasks addressed by id or by type; raises when nothing matches."""
        if task_id:
            matches = [self.tasks[task_id]] if task_id in self.tasks else []
        elif type_key:
            matches = self._active(type_key)
        else:
            raise ServiceValidationError("Give a task_id or a type")
        if not matches:
            raise ServiceValidationError("No such active task")
        return matches

    async def async_done(self, task_id: str | None = None, type_key: str | None = None) -> None:
        """Complete tasks. The only thing that ends a non-dismissable task."""
        async with self._lock:
            for task in self.resolve(task_id, type_key):
                await self._finish(task, "done")
            await self._commit()
        await self.async_process()

    async def async_dismiss(self, task_id: str | None = None, type_key: str | None = None) -> None:
        """End a dismissable task without doing it."""
        async with self._lock:
            matches = self.resolve(task_id, type_key)
            for task in matches:
                task_type = self.types.get(task.type_key)
                if task_type is None or not task_type.dismissable:
                    raise ServiceValidationError(
                        f"{task.title} cannot be dismissed; only completing it ends it"
                    )
            for task in matches:
                await self._finish(task, "dismissed", chain=False)
            await self._commit()

    async def async_snooze(self, task_id: str | None = None, type_key: str | None = None) -> None:
        """Snooze notifying tasks by the next (shorter) snooze period."""
        async with self._lock:
            matches = self.resolve(task_id, type_key)
            now = dt_util.utcnow()
            for task in matches:
                task_type = self.types.get(task.type_key)
                minutes = (
                    snooze_for(task.snooze_count, task_type.snooze_minutes) if task_type else None
                )
                if minutes is None:
                    raise ServiceValidationError(f"{task.title} has no snoozes left")
                task.status = TaskStatus.SNOOZED
                task.snooze_count += 1
                task.next_at = now + timedelta(minutes=minutes)
                await self.notifier.async_clear(task.id)
            await self._commit()

    # -- silencing --------------------------------------------------------

    async def async_set_silence(self, mode: str, until: datetime | None) -> None:
        """Set or end silencing. A mode other than `off` needs a future end time."""
        async with self._lock:
            now = dt_util.utcnow()
            if mode == SILENCE_OFF:
                self.silence = Silence()
            else:
                until = until or self.pending_until
                if until is None or until <= now:
                    raise ServiceValidationError("Silencing needs an end time in the future")
                self.silence = Silence(mode=mode, until=dt_util.as_utc(until))
            self.pending_until = None
            if mode == SILENCE_SILENT:
                for task in self.tasks.values():
                    if task.status is TaskStatus.HELD and task.held_reason == HOLD_SILENT:
                        task.next_at = self.silence.until
            else:
                await self._release_silent(now)
            await self._commit()
        await self.async_process()

    async def async_set_pending_until(self, until: datetime | None) -> None:
        """The end time entity: moves a running silence, else prepares the next."""
        if self.silence.mode != SILENCE_OFF:
            await self.async_set_silence(self.silence.mode, until)
            return
        self.pending_until = until
        async_dispatcher_send(self.hass, SIGNAL_UPDATE)

    # -- triggers & actions ----------------------------------------------

    async def _async_trigger(self, kind: str, task_type: TaskType) -> None:
        if kind == "start":
            await self.async_start_task(task_type.key)
            return
        async with self._lock:
            now = dt_util.utcnow()
            for task in self._active(task_type.key):
                if kind == "due" and task.status is TaskStatus.ARMED:
                    task.due_at = task.next_at = now
                elif kind == "done" and task.status in ACTIVE_STATES_AFTER_DUE:
                    # A door opened before the task was due must not complete it.
                    await self._finish(task, "done")
            await self._commit()
        await self.async_process()

    async def _on_action(self, event: Event) -> None:
        action = str(event.data.get("action", ""))
        if not action.startswith(ACTION_PREFIX):
            return
        verb, _, task_id = action[len(ACTION_PREFIX) :].partition("_")
        try:
            if verb == ACTION_DONE:
                await self.async_done(task_id)
            elif verb == ACTION_SNOOZE:
                await self.async_snooze(task_id)
            elif verb == ACTION_DISMISS:
                await self.async_dismiss(task_id)
        except ServiceValidationError as err:
            _LOGGER.debug("Ignoring notification action %s: %s", action, err)
