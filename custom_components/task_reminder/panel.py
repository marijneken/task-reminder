"""Sidebar panel: registration and the websocket API it talks to."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.components import panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.util import dt as dt_util

from .const import (
    ADHOC_KEY,
    ATTR_SORT_DATE,
    DOMAIN,
    SIGNAL_UPDATE,
    SILENCE_MODES,
)
from .manager import TaskManager
from .models import Task
from .policy import keeps_going, snooze_for

_LOGGER = logging.getLogger(__name__)

URL_BASE = "/task_reminder_static"
PANEL_URL = "tasks"
PANEL_FILE = "task-reminder-panel.js"


async def async_setup_panel(hass: HomeAssistant) -> None:
    """Register the websocket API, serve the panel JS and add "Tasks" to the sidebar."""
    if hass.data.get(f"{DOMAIN}_panel"):
        return
    hass.data[f"{DOMAIN}_panel"] = True
    for command in (
        ws_subscribe,
        ws_done,
        ws_cancel,
        ws_snooze,
        ws_dismiss,
        ws_start,
        ws_remind,
        ws_silence,
    ):
        websocket_api.async_register_command(hass, command)
    if hass.http is None:  # e.g. tests without a web server
        return
    www = Path(__file__).parent / "www"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(URL_BASE, str(www), cache_headers=False)]
    )
    version = (www / PANEL_FILE).stat().st_mtime_ns
    try:
        await panel_custom.async_register_panel(
            hass,
            frontend_url_path=PANEL_URL,
            webcomponent_name="task-reminder-panel",
            sidebar_title="Tasks",
            sidebar_icon="mdi:bell-check-outline",
            module_url=f"{URL_BASE}/{PANEL_FILE}?v={version}",
            require_admin=False,
        )
    except Exception:
        _LOGGER.warning("Could not add the Tasks panel to the sidebar", exc_info=True)


def _manager(hass: HomeAssistant) -> TaskManager | None:
    # Not only "loaded": while the entry reloads the manager is already attached.
    for entry in hass.config_entries.async_entries(DOMAIN):
        if (mgr := getattr(entry, "runtime_data", None)) is not None:
            return mgr
    return None


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _task_dict(mgr: TaskManager, task: Task) -> dict[str, Any]:
    task_type = mgr._type_of(task)
    snoozes = task_type.snooze_minutes if task_type else ()
    return {
        "id": task.id,
        "type": task.type_key,
        "type_name": task_type.name if task_type else task.type_key,
        "title": task.title,
        "message": task.message,
        "status": task.status.value,
        "created_at": _iso(task.created_at),
        "due_at": _iso(task.due_at),
        "next_at": _iso(task.next_at),
        "last_notified_at": _iso(task.last_notified_at),
        "level": task.level,
        "keeps_going": keeps_going(task.level, snoozes),
        "snooze_count": task.snooze_count,
        "snooze_total": len(snoozes),
        "snooze_next": snooze_for(task.snooze_count, snoozes),
        "dismissable": bool(task_type and mgr.is_dismissable(task_type)),
        "held_reason": task.held_reason,
        "ringing": bool(task.ring_at and task.status.value == "notifying"),
        "waits_for": task_type.due_entity if task_type and task.due_at is None else None,
    }


def _parse_day(value: Any) -> date | None:
    try:
        text = str(value)
        return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    except (ValueError, TypeError):
        return None


def _upcoming(mgr: TaskManager) -> list[dict[str, Any]]:
    """Collections coming up for task types that follow a schedule sensor and have no
    task running for them (yet)."""
    today = dt_util.now().date()
    items = []
    for task_type in mgr.types.values():
        if not task_type.schedule_entity or mgr._active(task_type.key):
            continue
        state = mgr.hass.states.get(task_type.schedule_entity)
        if state is None or state.state in ("unavailable", "unknown"):
            continue
        collection = _parse_day(state.attributes.get(ATTR_SORT_DATE))
        if collection is None or collection < today:
            continue
        if mgr.marks.get(task_type.key) == str(state.attributes.get(ATTR_SORT_DATE)):
            continue  # already started (and finished) for this collection
        items.append(
            {
                "type": task_type.key,
                "name": task_type.name,
                "collection": collection.isoformat(),
                "starts_on": max(
                    today, collection - timedelta(days=task_type.start_days_before)
                ).isoformat(),
                "due_time": task_type.due_time.strftime("%H:%M") if task_type.due_time else None,
            }
        )
    return sorted(items, key=lambda i: i["collection"])


def _snapshot(hass: HomeAssistant) -> dict[str, Any]:
    mgr = _manager(hass)
    if mgr is None:
        return {"ready": False, "tasks": []}
    return {
        "ready": True,
        "now": dt_util.utcnow().isoformat(),
        "entry_id": mgr.entry.entry_id,
        "silence": {"mode": mgr.silence.mode, "until": _iso(mgr.silence.until)},
        "room": mgr.current_place(),
        "tasks": [_task_dict(mgr, t) for t in mgr.tasks.values()],
        "types": [{"key": t.key, "name": t.name} for t in mgr.types.values() if t.key != ADHOC_KEY],
        "upcoming": _upcoming(mgr),
        "history": mgr.history,
    }


@websocket_api.websocket_command({vol.Required("type"): "task_reminder/subscribe"})
@callback
def ws_subscribe(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Send the state now and whenever it changes."""
    msg_id = msg["id"]

    @callback
    def send() -> None:
        connection.send_message(websocket_api.event_message(msg_id, _snapshot(hass)))

    connection.subscriptions[msg_id] = async_dispatcher_connect(hass, SIGNAL_UPDATE, send)
    connection.send_result(msg_id)
    send()


def _require(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> TaskManager | None:
    mgr = _manager(hass)
    if mgr is None:
        connection.send_error(msg["id"], "not_ready", "Task Reminder is not set up")
    return mgr


async def _run(connection: websocket_api.ActiveConnection, msg: dict, coro) -> None:
    """Await a manager call; turn its validation errors into websocket errors."""
    try:
        result = await coro
    except HomeAssistantError as err:
        connection.send_error(msg["id"], "invalid", str(err))
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {vol.Required("type"): "task_reminder/done", vol.Required("task_id"): str}
)
@websocket_api.async_response
async def ws_done(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Complete a task."""
    if mgr := _require(hass, connection, msg):
        await _run(connection, msg, mgr.async_done(msg["task_id"]))


@websocket_api.websocket_command(
    {vol.Required("type"): "task_reminder/cancel", vol.Required("task_id"): str}
)
@websocket_api.async_response
async def ws_cancel(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Cancel a task that is not due yet."""
    if mgr := _require(hass, connection, msg):
        await _run(connection, msg, mgr.async_cancel(msg["task_id"]))


@websocket_api.websocket_command(
    {vol.Required("type"): "task_reminder/snooze", vol.Required("task_id"): str}
)
@websocket_api.async_response
async def ws_snooze(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Snooze a task."""
    if mgr := _require(hass, connection, msg):
        await _run(connection, msg, mgr.async_snooze(msg["task_id"]))


@websocket_api.websocket_command(
    {vol.Required("type"): "task_reminder/dismiss", vol.Required("task_id"): str}
)
@websocket_api.async_response
async def ws_dismiss(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Dismiss a task."""
    if mgr := _require(hass, connection, msg):
        await _run(connection, msg, mgr.async_dismiss(msg["task_id"]))


async def _start(mgr: TaskManager, type_key: str, **kwargs) -> dict[str, str]:
    task = await mgr.async_start_task(type_key, **kwargs)
    return {"task_id": task.id}


@websocket_api.websocket_command(
    {vol.Required("type"): "task_reminder/start", vol.Required("task_type"): str}
)
@websocket_api.async_response
async def ws_start(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Start a configured task type right now (due as its type says)."""
    if mgr := _require(hass, connection, msg):
        await _run(connection, msg, _start(mgr, msg["task_type"]))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "task_reminder/remind",
        vol.Required("title"): vol.All(str, vol.Length(min=1, max=120)),
        vol.Optional("minutes"): vol.All(vol.Coerce(float), vol.Range(min=0, max=7 * 24 * 60)),
    }
)
@websocket_api.async_response
async def ws_remind(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Quick reminder or timer."""
    if mgr := _require(hass, connection, msg):
        due_in = timedelta(minutes=msg["minutes"]) if msg.get("minutes") else None
        await _run(
            connection, msg, _start(mgr, ADHOC_KEY, title=msg["title"].strip(), due_in=due_in)
        )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "task_reminder/silence",
        vol.Required("mode"): vol.In(SILENCE_MODES),
        vol.Optional("until"): cv.datetime,
    }
)
@websocket_api.async_response
async def ws_silence(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Silence reminders until a time, or end silencing."""

    async def set_silence() -> None:
        await mgr.async_set_silence(msg["mode"], msg.get("until"))

    if mgr := _require(hass, connection, msg):
        await _run(connection, msg, set_silence())
