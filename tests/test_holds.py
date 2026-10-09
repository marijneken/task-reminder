"""Persistence across restarts, silencing, quiet hours and away."""

from datetime import UTC, datetime, timedelta

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.task_reminder.const import DOMAIN

from .conftest import advance, type_data


async def _start(hass, type_, **data):
    resp = await hass.services.async_call(
        DOMAIN, "start", {"type": type_, **data}, blocking=True, return_response=True
    )
    return resp["task_id"]


async def test_restart_keeps_tasks_and_fires_overdue(hass, freezer, notify, make_entry):
    entry = await make_entry(type_data("washer", duration_minutes=30))
    task_id = await _start(hass, "washer")
    await advance(hass, freezer, minutes=10)

    assert await hass.config_entries.async_unload(entry.entry_id)
    # HA is down for an hour; the task became due meanwhile.
    freezer.tick(timedelta(hours=1))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    manager = entry.runtime_data
    assert task_id in manager.tasks
    assert manager.tasks[task_id].status == "notifying"
    assert len(notify["phone"]) == 1  # fired immediately, once


async def test_restart_keeps_snooze_count_and_silence(hass, freezer, make_entry):
    entry = await make_entry(type_data("washer"))
    task_id = await _start(hass, "washer")
    await hass.services.async_call(DOMAIN, "snooze", {"task_id": task_id}, blocking=True)
    until = datetime(2026, 10, 9, 15, 0, tzinfo=UTC)
    await hass.services.async_call(
        DOMAIN, "silence", {"mode": "no_critical", "until": until}, blocking=True
    )
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    manager = entry.runtime_data
    assert manager.tasks[task_id].snooze_count == 1
    assert manager.silence.mode == "no_critical" and manager.silence.until == until


async def test_silent_mode_holds_then_summarises(hass, freezer, notify, make_entry):
    entry = await make_entry(type_data("washer"), type_data("dryer"))
    until = datetime(2026, 10, 9, 14, 0, tzinfo=UTC)
    await hass.services.async_call(
        DOMAIN, "silence", {"mode": "silent", "until": until}, blocking=True
    )
    await _start(hass, "washer")
    await _start(hass, "dryer")
    await advance(hass, freezer, hours=1)
    assert notify["phone"] == []
    assert {t.held_reason for t in entry.runtime_data.tasks.values()} == {"silent"}

    await advance(hass, freezer, hours=1)  # silence ends
    assert entry.runtime_data.silence.mode == "off"
    summary = notify["phone"][0].data
    assert "Washer" in summary["message"] and "Dryer" in summary["message"]
    assert len(notify["phone"]) == 1  # tasks wait a minute after the summary
    await advance(hass, freezer, minutes=1)
    assert len(notify["phone"]) == 3


async def test_single_held_task_is_delivered_directly(hass, freezer, notify, make_entry):
    await make_entry(type_data("washer"))
    until = datetime(2026, 10, 9, 14, 0, tzinfo=UTC)
    await hass.services.async_call(
        DOMAIN, "silence", {"mode": "silent", "until": until}, blocking=True
    )
    await _start(hass, "washer")
    await advance(hass, freezer, hours=2)
    assert len(notify["phone"]) == 1
    assert notify["phone"][0].data["message"] == "Washer is due"


async def test_ending_silence_early_releases_tasks(hass, freezer, notify, make_entry):
    await make_entry(type_data("washer"))
    until = datetime(2026, 10, 9, 20, 0, tzinfo=UTC)
    await hass.services.async_call(
        DOMAIN, "silence", {"mode": "silent", "until": until}, blocking=True
    )
    await _start(hass, "washer")
    await hass.services.async_call(DOMAIN, "silence", {"mode": "off"}, blocking=True)
    await hass.async_block_till_done()
    assert len(notify["phone"]) == 1


async def test_no_critical_mode_downgrades_keeps_going(hass, freezer, notify, make_entry):
    await make_entry(type_data("washer"))
    until = datetime(2026, 10, 9, 20, 0, tzinfo=UTC)
    await hass.services.async_call(
        DOMAIN, "silence", {"mode": "no_critical", "until": until}, blocking=True
    )
    await _start(hass, "washer")
    for _ in range(6):
        await advance(hass, freezer, minutes=5)
    assert len(notify["phone"]) >= 5
    assert all("push" not in c.data["data"] for c in notify["phone"])
    assert len(notify["extra"]) >= 1  # still escalates, just without critical


async def test_silence_needs_future_end_time(hass, make_entry):
    await make_entry(type_data("washer"))
    with pytest.raises(ServiceValidationError, match="end time"):
        await hass.services.async_call(DOMAIN, "silence", {"mode": "silent"}, blocking=True)
    with pytest.raises(ServiceValidationError, match="end time"):
        await hass.services.async_call(
            DOMAIN,
            "silence",
            {"mode": "silent", "until": datetime(2026, 10, 9, 11, 0, tzinfo=UTC)},
            blocking=True,
        )


async def test_quiet_hours_hold_non_critical_only(hass, freezer, notify, make_entry):
    entry = await make_entry(
        type_data("washer", duration_minutes=60),
        type_data("alarm", duration_minutes=60, time_critical=True),
    )
    freezer.move_to(datetime(2026, 10, 9, 22, 30, tzinfo=UTC))
    await _start(hass, "washer")
    await _start(hass, "alarm")
    await advance(hass, freezer, hours=1)  # 23:30, quiet

    assert [c.data["message"] for c in notify["phone"]] == ["Alarm is due"]
    assert notify["phone"][0].data["data"]["push"] == {"interruption-level": "time-sensitive"}
    held = next(t for t in entry.runtime_data.tasks.values() if t.type_key == "washer")
    assert held.status == "held" and held.held_reason == "quiet"

    await advance(hass, freezer, hours=7, minutes=30)  # 07:00
    assert "Washer is due" in [c.data["message"] for c in notify["phone"]]


async def test_away_sends_one_quiet_notification_then_waits_for_home(
    hass, freezer, notify, make_entry
):
    entry = await make_entry(type_data("washer", duration_minutes=30))
    await _start(hass, "washer")
    hass.states.async_set("person.marijn", "not_home")
    await advance(hass, freezer, minutes=30)

    assert len(notify["phone"]) == 1
    sent = notify["phone"][0].data
    assert sent["data"]["push"] == {"interruption-level": "passive"}
    assert "you're away" in sent["message"]
    assert notify["alexa"] == []

    await advance(hass, freezer, hours=3)  # still nothing, no pressure
    assert len(notify["phone"]) == 1

    hass.states.async_set("person.marijn", "home")
    await hass.async_block_till_done()
    assert len(notify["phone"]) == 2
    assert notify["phone"][1].data["message"] == "Washer is due"
    (task,) = entry.runtime_data.tasks.values()
    assert task.status == "notifying"


async def test_unknown_person_state_is_not_away(hass, freezer, notify, make_entry):
    await make_entry(type_data("washer"))
    hass.states.async_set("person.marijn", "unknown")
    await _start(hass, "washer")
    assert len(notify["phone"]) == 1
