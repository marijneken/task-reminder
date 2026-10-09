"""Entity-state triggers: start, due, done."""

from custom_components.task_reminder.const import DOMAIN

from .conftest import type_data


async def test_start_due_done_triggers(hass, notify, make_entry):
    entry = await make_entry(
        type_data(
            "washer",
            start_entity="input_boolean.washer_nfc",
            due_entity="sensor.washer_state",
            due_state="finished",
            done_entity="binary_sensor.washer_door",
        )
    )
    manager = entry.runtime_data

    hass.states.async_set("input_boolean.washer_nfc", "off")
    hass.states.async_set("input_boolean.washer_nfc", "on")
    await hass.async_block_till_done()
    (task,) = manager.tasks.values()
    assert task.status == "armed" and task.next_at is None  # waits for the cycle to end

    # The door opening while the washer is still running must not complete it.
    hass.states.async_set("binary_sensor.washer_door", "off")
    hass.states.async_set("binary_sensor.washer_door", "on")
    await hass.async_block_till_done()
    assert len(manager.tasks) == 1

    hass.states.async_set("sensor.washer_state", "running")
    hass.states.async_set("sensor.washer_state", "finished")
    await hass.async_block_till_done()
    assert task.status == "notifying" and len(notify["phone"]) == 1

    hass.states.async_set("binary_sensor.washer_door", "off")
    hass.states.async_set("binary_sensor.washer_door", "on")
    await hass.async_block_till_done()
    assert manager.tasks == {}


async def test_unavailable_does_not_trigger(hass, make_entry):
    entry = await make_entry(
        type_data("washer", done_entity="binary_sensor.door", done_state="unavailable")
    )
    await hass.services.async_call(DOMAIN, "start", {"type": "washer"}, blocking=True)
    hass.states.async_set("binary_sensor.door", "unavailable")
    await hass.async_block_till_done()
    assert len(entry.runtime_data.tasks) == 1
