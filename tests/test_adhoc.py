"""Ad hoc reminders and timers: the remind action and the test button."""

from datetime import UTC, datetime

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.task_reminder.const import DOMAIN

from .conftest import advance


async def _remind(hass, **data):
    resp = await hass.services.async_call(
        DOMAIN, "remind", data, blocking=True, return_response=True
    )
    return resp["task_id"]


async def test_remind_needs_no_task_type(hass, notify, make_entry):
    await make_entry()  # no task types configured at all
    await _remind(hass, title="Call the plumber")
    assert len(notify["phone"]) == 1
    assert notify["phone"][0].data["title"] == "Task Reminder"
    assert notify["phone"][0].data["message"] == "Call the plumber is due"


async def test_egg_timer(hass, freezer, notify, make_entry):
    entry = await make_entry()
    await _remind(hass, title="Egg timer", message="The eggs are done", due_in={"minutes": 7})
    assert notify["phone"] == []
    await advance(hass, freezer, minutes=6)
    assert notify["phone"] == []
    await advance(hass, freezer, minutes=1)
    assert notify["phone"][0].data["message"] == "The eggs are done"

    await hass.services.async_call(DOMAIN, "done", {"type": "ad_hoc"}, blocking=True)
    assert entry.runtime_data.tasks == {}


async def test_remind_at_a_time(hass, freezer, notify, make_entry):
    await make_entry()
    await _remind(hass, title="Call", due_at=datetime(2026, 10, 9, 15, 0, tzinfo=UTC))
    await advance(hass, freezer, hours=2, minutes=59)
    assert notify["phone"] == []
    await advance(hass, freezer, minutes=1)
    assert len(notify["phone"]) == 1


async def test_several_at_once_and_dismiss_only_when_asked(hass, notify, make_entry):
    entry = await make_entry()
    first = await _remind(hass, title="Egg timer", dismissable=True)
    second = await _remind(hass, title="Laundry out")
    assert first != second and len(entry.runtime_data.tasks) == 2
    first_actions = [a["title"] for a in notify["phone"][0].data["data"]["actions"]]
    second_actions = [a["title"] for a in notify["phone"][1].data["data"]["actions"]]
    assert first_actions == ["Done", "Snooze", "Dismiss"]
    assert second_actions == ["Done", "Snooze"]  # Dismiss would only duplicate Done
    with pytest.raises(ServiceValidationError, match="cannot be dismissed"):
        await hass.services.async_call(DOMAIN, "dismiss", {"task_id": second}, blocking=True)
    await hass.services.async_call(DOMAIN, "dismiss", {"task_id": first}, blocking=True)
    assert set(entry.runtime_data.tasks) == {second}


async def test_overrides_apply_to_that_reminder_only(hass, freezer, notify, make_entry):
    entry = await make_entry()
    freezer.move_to(datetime(2026, 10, 9, 23, 30, tzinfo=UTC))  # quiet hours
    # Asked for explicitly: breaks quiet hours by default.
    await _remind(hass, title="Now")
    assert len(notify["phone"]) == 1
    # Opted out: waits for the morning, and cannot be dismissed.
    held = await _remind(hass, title="Whenever", time_critical=False, dismissable=False)
    task = entry.runtime_data.tasks[held]
    assert task.status == "held" and task.held_reason == "quiet"
    with pytest.raises(ServiceValidationError, match="cannot be dismissed"):
        await hass.services.async_call(DOMAIN, "dismiss", {"task_id": held}, blocking=True)
    # The first one was not affected.
    other = next(t for t in entry.runtime_data.tasks.values() if t.title == "Now")
    assert other.status == "notifying"


async def test_overrides_survive_a_restart(hass, freezer, make_entry):
    entry = await make_entry()
    freezer.move_to(datetime(2026, 10, 9, 23, 30, tzinfo=UTC))
    task_id = await _remind(hass, title="Whenever", time_critical=False)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    task = entry.runtime_data.tasks[task_id]
    assert task.status == "held" and task.extra["overrides"] == {"time_critical": False}


async def test_due_in_and_due_at_are_exclusive(hass, make_entry):
    await make_entry()
    with pytest.raises(Exception, match="due"):
        await hass.services.async_call(
            DOMAIN,
            "remind",
            {"title": "x", "due_in": {"minutes": 1}, "due_at": "2026-10-09T15:00:00+00:00"},
            blocking=True,
        )


async def test_test_button(hass, notify, make_entry):
    entry = await make_entry()
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.task_reminder_test_reminder"}, blocking=True
    )
    assert len(entry.runtime_data.tasks) == 1
    assert notify["phone"][0].data["title"] == "Task Reminder"
    assert notify["phone"][0].data["message"] == "This is a test reminder"


async def test_ad_hoc_name_is_reserved(hass, make_entry):
    from custom_components.task_reminder.const import SUBENTRY_TYPE

    entry = await make_entry()
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE), context={"source": "user"}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {"name": "Ad hoc", "snooze_minutes": "5", "repeat_minutes": 5, "keeps_going_minutes": 2},
    )
    assert result["errors"] == {"name": "reserved_name"}
