"""NFC tags and good moments."""

from datetime import timedelta

from custom_components.task_reminder.const import DOMAIN

from .conftest import advance, sent, type_data


def _tag(hass, entity_id, tag_id):
    hass.states.async_set(entity_id, "2026-10-09T12:00:00", {"tag_id": tag_id})


async def _scan(hass, tag_id):
    hass.bus.async_fire("tag_scanned", {"tag_id": tag_id, "name": "x"})
    await hass.async_block_till_done()


async def test_tag_starts_and_completes(hass, notify, make_entry):
    entry = await make_entry(
        type_data(
            "washer", duration_minutes=45, start_tag="tag.washer_start", done_tag="tag.washer_done"
        )
    )
    _tag(hass, "tag.washer_start", "AAA")
    _tag(hass, "tag.washer_done", "BBB")

    await _scan(hass, "CCC")  # unrelated tag
    assert entry.runtime_data.tasks == {}

    await _scan(hass, "AAA")
    (task,) = entry.runtime_data.tasks.values()
    assert task.status == "armed"

    await _scan(hass, "BBB")  # even before it is due: a scan is deliberate
    assert entry.runtime_data.tasks == {}


async def test_same_tag_toggles(hass, make_entry):
    entry = await make_entry(
        type_data("timer", duration_minutes=10, start_tag="tag.t", done_tag="tag.t")
    )
    _tag(hass, "tag.t", "XYZ")
    await _scan(hass, "XYZ")
    assert len(entry.runtime_data.tasks) == 1
    await _scan(hass, "XYZ")
    assert entry.runtime_data.tasks == {}
    await _scan(hass, "XYZ")
    assert len(entry.runtime_data.tasks) == 1


async def test_start_tag_while_running_is_ignored(hass, make_entry):
    entry = await make_entry(type_data("washer", duration_minutes=45, start_tag="tag.w"))
    _tag(hass, "tag.w", "AAA")
    await _scan(hass, "AAA")
    (first,) = entry.runtime_data.tasks
    await _scan(hass, "AAA")
    assert list(entry.runtime_data.tasks) == [first]


async def _motion(hass, entity):
    hass.states.async_set(entity, "off")
    hass.states.async_set(entity, "on")
    await hass.async_block_till_done()


async def test_good_moment_brings_the_next_reminder_forward(hass, freezer, notify, make_entry):
    await make_entry(type_data("laundry", good_moment_entities=["binary_sensor.stairs"]))
    await hass.services.async_call(DOMAIN, "start", {"type": "laundry"}, blocking=True)
    assert len(notify["phone"]) == 1

    await advance(hass, freezer, minutes=1)
    await _motion(hass, "binary_sensor.stairs")  # too soon after the last one
    assert len(notify["phone"]) == 1

    await advance(hass, freezer, minutes=2)  # 3 minutes since the reminder, next due in 5
    await _motion(hass, "binary_sensor.stairs")
    assert len(sent(notify["phone"])) == 2  # spoke up early, at the next escalation level
    assert len(notify["alexa"]) == 1


async def test_good_moment_does_not_break_a_snooze_or_wake_armed_tasks(
    hass, freezer, notify, make_entry
):
    entry = await make_entry(
        type_data("laundry", duration_minutes=60, good_moment_entities=["binary_sensor.stairs"])
    )
    await hass.services.async_call(DOMAIN, "start", {"type": "laundry"}, blocking=True)
    await _motion(hass, "binary_sensor.stairs")  # not due yet
    assert notify["phone"] == []

    await advance(hass, freezer, hours=1)
    assert len(notify["phone"]) == 1
    await hass.services.async_call(DOMAIN, "snooze", {"type": "laundry"}, blocking=True)
    freezer.tick(timedelta(minutes=3))
    await _motion(hass, "binary_sensor.stairs")  # snoozed: stay quiet
    reminders = [c for c in notify["phone"] if c.data["message"] != "clear_notification"]
    assert len(reminders) == 1
    (task,) = entry.runtime_data.tasks.values()
    assert task.status == "snoozed"
