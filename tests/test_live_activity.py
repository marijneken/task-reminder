"""A Live Activity counts down on the lock screen to what is coming up."""

from datetime import timedelta

from homeassistant.util import dt as dt_util

from custom_components.task_reminder.const import DOMAIN

from .conftest import advance, sent


def _live(calls):
    return [c for c in calls if c.data.get("data", {}).get("live_update")]


def _cleared(calls):
    return [
        c.data["data"]["tag"]
        for c in calls
        if c.data.get("message") == "clear_notification" and c.data["data"]["tag"].endswith("_live")
    ]


async def _remind(hass, **data):
    resp = await hass.services.async_call(
        DOMAIN, "remind", {"title": "Egg timer", **data}, blocking=True, return_response=True
    )
    return resp["task_id"]


async def test_off_unless_enabled(hass, notify, make_entry):
    await make_entry()
    await _remind(hass, due_in="00:20:00")
    assert _live(notify["phone"]) == []


async def test_a_timer_counts_down_on_the_lock_screen(hass, freezer, notify, make_entry):
    entry = await make_entry(live_activities=True)
    task_id = await _remind(hass, due_in="00:20:00")
    (call,) = _live(notify["phone"])
    data = call.data["data"]
    assert call.data["title"] == "Egg timer"
    assert call.data["message"] == "Due at 12:20"
    assert data["tag"].endswith("_live") and task_id in data["tag"]
    # real booleans and numbers: the app ignores them when they arrive as strings
    assert data["live_update"] is True and data["chronometer"] is True
    assert data["when"] == int(entry.runtime_data.tasks[task_id].due_at.timestamp())
    assert _live(notify["extra"]) == []  # phones only

    await advance(hass, freezer, minutes=20)  # the reminder arrives, the countdown is over
    assert len(sent(notify["phone"])) == 2  # the live push and the reminder
    assert _cleared(notify["phone"]) == [data["tag"]]


async def test_done_early_ends_the_countdown(hass, notify, make_entry):
    await make_entry(live_activities=True)
    task_id = await _remind(hass, due_in="00:20:00")
    tag = _live(notify["phone"])[0].data["data"]["tag"]
    await hass.services.async_call(DOMAIN, "done", {"task_id": task_id}, blocking=True)
    assert _cleared(notify["phone"]) == [tag]


async def test_starts_within_seven_hours_of_the_due_time(hass, freezer, notify, make_entry):
    await make_entry(live_activities=True)
    await _remind(hass, due_in="10:00:00")
    assert _live(notify["phone"]) == []
    await advance(hass, freezer, hours=2, minutes=59)
    assert _live(notify["phone"]) == []
    await advance(hass, freezer, minutes=1)  # 7 hours to go
    (call,) = _live(notify["phone"])
    assert call.data["message"] == "Due at 22:00"


async def test_a_snooze_counts_down_to_the_next_reminder(hass, freezer, notify, make_entry):
    from .conftest import type_data

    entry = await make_entry(type_data("washer"), live_activities=True)
    task_id = (
        await hass.services.async_call(
            DOMAIN,
            "start",
            {"type": "washer", "due_in": "00:05:00"},
            blocking=True,
            return_response=True,
        )
    )["task_id"]
    await advance(hass, freezer, minutes=5)  # due: the reminder
    assert _live(notify["phone"])[-1].data["message"] == "Due at 12:05"
    await hass.services.async_call(DOMAIN, "snooze", {"task_id": task_id}, blocking=True)
    snoozed = entry.runtime_data.tasks[task_id]
    live = _live(notify["phone"])[-1]
    assert live.data["message"] == "Reminder at 12:15"
    assert live.data["data"]["when"] == int(snoozed.next_at.timestamp())
    assert live.data["data"]["tag"] == _live(notify["phone"])[0].data["data"]["tag"]  # updates it


async def test_not_while_silenced(hass, freezer, notify, make_entry):
    entry = await make_entry(live_activities=True)
    await hass.services.async_call(
        DOMAIN,
        "silence",
        {"mode": "silent", "until": (dt_util.utcnow() + timedelta(hours=1)).isoformat()},
        blocking=True,
    )
    await _remind(hass, due_in="00:20:00")
    assert _live(notify["phone"]) == []
    assert entry.runtime_data.tasks
