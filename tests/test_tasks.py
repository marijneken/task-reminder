"""Task lifecycle: due, snooze, escalation, done, dismiss, persistence."""

from datetime import timedelta

import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from custom_components.task_reminder.const import DOMAIN

from .conftest import advance, sent, type_data


def _manager(entry):
    return entry.runtime_data


async def _start(hass, type_, **data):
    resp = await hass.services.async_call(
        DOMAIN, "start", {"type": type_, **data}, blocking=True, return_response=True
    )
    return resp["task_id"]


async def test_due_after_duration_notifies_phone_only_first(hass, freezer, notify, make_entry):
    await make_entry(type_data("washer", duration_minutes=30))
    await _start(hass, "washer")
    assert notify["phone"] == []

    await advance(hass, freezer, minutes=29)
    assert notify["phone"] == []
    await advance(hass, freezer, minutes=1)

    assert len(notify["phone"]) == 1
    call = notify["phone"][0].data
    assert call["title"] == "Task Reminder"
    assert call["message"] == "Washer is due"
    actions = [a["action"].split("_")[2] for a in call["data"]["actions"]]
    assert actions == ["DONE", "SNOOZE"]
    assert notify["alexa"] == [] and notify["extra"] == []


async def test_unanswered_reminders_escalate_to_critical(hass, freezer, notify, make_entry):
    await make_entry(type_data("washer"))
    await _start(hass, "washer")  # no duration: due now
    assert len(sent(notify["phone"])) == 1

    await advance(hass, freezer, minutes=5)  # level 1: + alexa
    assert len(notify["alexa"]) == 1
    await advance(hass, freezer, minutes=5)  # level 2: + other devices
    assert len(sent(notify["extra"])) == 1
    assert "push" not in sent(notify["phone"])[-1].data["data"]

    await advance(hass, freezer, minutes=5)  # level 3: keeps going, critical
    assert sent(notify["phone"])[-1].data["data"]["push"]["sound"]["critical"] == 1
    before = len(sent(notify["phone"]))
    await advance(hass, freezer, minutes=2)  # now every 2 minutes
    await advance(hass, freezer, minutes=2)
    assert len(sent(notify["phone"])) == before + 2


async def test_snoozes_shrink_and_run_out(hass, freezer, notify, make_entry):
    entry = await make_entry(type_data("washer"))
    task_id = await _start(hass, "washer")
    task = _manager(entry).tasks[task_id]

    for minutes in (10, 5, 3):
        await hass.services.async_call(DOMAIN, "snooze", {"task_id": task_id}, blocking=True)
        assert task.status == "snoozed"
        assert task.next_at - dt_util.utcnow() == timedelta(minutes=minutes)
        await advance(hass, freezer, minutes=minutes)

    with pytest.raises(ServiceValidationError, match="no snoozes left"):
        await hass.services.async_call(DOMAIN, "snooze", {"task_id": task_id}, blocking=True)
    # After the last snooze the next reminder has no Snooze button.
    last = notify["phone"][-1].data["data"]["actions"]
    assert [a["title"] for a in last] == ["Done"]


async def test_done_ends_task_and_clears_notification(hass, freezer, notify, make_entry):
    entry = await make_entry(type_data("washer"))
    task_id = await _start(hass, "washer")
    await hass.services.async_call(DOMAIN, "done", {"type": "washer"}, blocking=True)
    assert _manager(entry).tasks == {}
    assert notify["phone"][-1].data["message"] == "clear_notification"
    # Nothing more fires.
    count = len(notify["phone"])
    await advance(hass, freezer, hours=1)
    assert len(notify["phone"]) == count
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "done", {"task_id": task_id}, blocking=True)


async def test_dismiss_only_for_dismissable(hass, make_entry):
    entry = await make_entry(type_data("laundry"), type_data("trash", dismissable=True))
    laundry = await _start(hass, "laundry")
    trash = await _start(hass, "trash")
    with pytest.raises(ServiceValidationError, match="cannot be dismissed"):
        await hass.services.async_call(DOMAIN, "dismiss", {"task_id": laundry}, blocking=True)
    await hass.services.async_call(DOMAIN, "dismiss", {"task_id": trash}, blocking=True)
    assert set(_manager(entry).tasks) == {laundry}


async def test_single_instance_returns_running_task(hass, make_entry):
    await make_entry(type_data("laundry"), type_data("timer", single_instance=False))
    assert await _start(hass, "laundry") == await _start(hass, "laundry")
    assert await _start(hass, "timer") != await _start(hass, "timer")


async def test_unknown_type_rejected(hass, make_entry):
    await make_entry(type_data("laundry"))
    with pytest.raises(ServiceValidationError, match="Unknown task type"):
        await _start(hass, "nope")


async def test_then_start_chains_dryer_after_washer(hass, make_entry):
    entry = await make_entry(
        type_data("washer", then_start="dryer"), type_data("dryer", duration_minutes=60)
    )
    await _start(hass, "washer")
    await hass.services.async_call(DOMAIN, "done", {"type": "washer"}, blocking=True)
    assert [t.type_key for t in _manager(entry).tasks.values()] == ["dryer"]


async def test_due_at_time_of_day(hass, freezer, notify, make_entry):
    await make_entry(type_data("pills", due_time="18:00:00"))
    await _start(hass, "pills")
    await advance(hass, freezer, hours=5, minutes=59)
    assert notify["phone"] == []
    await advance(hass, freezer, minutes=1)
    assert len(notify["phone"]) == 1


async def test_failed_delivery_retries_without_escalating(hass, freezer, notify, make_entry):
    entry = await make_entry(type_data("washer"))

    async def boom(call):
        raise RuntimeError("phone unreachable")

    hass.services.async_register("notify", "mobile_app_phone", boom)
    task_id = await _start(hass, "washer")
    task = _manager(entry).tasks[task_id]
    assert task.level == 0  # nothing was delivered, so no escalation step used

    hass.services.async_register(
        "notify", "mobile_app_phone", lambda call: notify["phone"].append(call)
    )
    await advance(hass, freezer, minutes=1)
    assert task.level == 1


async def test_notification_actions_drive_tasks(hass, freezer, make_entry):
    entry = await make_entry(type_data("washer"))
    task_id = await _start(hass, "washer")
    hass.bus.async_fire(
        "mobile_app_notification_action", {"action": f"TASK_REMINDER_SNOOZE_{task_id}"}
    )
    await hass.async_block_till_done()
    assert _manager(entry).tasks[task_id].status == "snoozed"
    hass.bus.async_fire(
        "mobile_app_notification_action", {"action": f"TASK_REMINDER_DONE_{task_id}"}
    )
    await hass.async_block_till_done()
    assert _manager(entry).tasks == {}
    # Other apps' actions are ignored.
    hass.bus.async_fire("mobile_app_notification_action", {"action": "SOMETHING_ELSE"})
    await hass.async_block_till_done()


async def test_finished_event(hass, make_entry):
    await make_entry(type_data("washer"))
    events = []
    hass.bus.async_listen("task_reminder_finished", events.append)
    await _start(hass, "washer")
    await hass.services.async_call(DOMAIN, "done", {"type": "washer"}, blocking=True)
    await hass.async_block_till_done()
    assert events[0].data["outcome"] == "done"


async def test_removing_the_integration_forgets_its_tasks(hass, make_entry, hass_storage):
    entry = await make_entry(type_data("washer"))
    await _start(hass, "washer")
    assert hass_storage["task_reminder"]["data"]["tasks"]

    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert "task_reminder" not in hass_storage  # nothing left behind

    entry = await make_entry(type_data("washer"))
    assert entry.runtime_data.tasks == {}  # adding it again starts clean


async def test_a_reload_keeps_the_tasks(hass, make_entry):
    entry = await make_entry(type_data("washer"))
    await _start(hass, "washer")
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert len(entry.runtime_data.tasks) == 1  # only removal forgets
