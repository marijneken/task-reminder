"""Fill flag, quiet heads-up and two-door done sequence."""

from datetime import timedelta

import pytest
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.task_reminder.const import DOMAIN

from .conftest import advance, sent, type_data

FLAG = "input_boolean.papier_has_waste"


async def _start(hass, type_):
    resp = await hass.services.async_call(
        DOMAIN, "start", {"type": type_}, blocking=True, return_response=True
    )
    return resp["task_id"]


async def test_flag_off_means_dismissable_and_lighter(hass, freezer, notify, make_entry):
    entry = await make_entry(type_data("papier", flag_entity=FLAG))
    hass.states.async_set(FLAG, "off")
    task_id = await _start(hass, "papier")

    actions = [a["title"] for a in notify["phone"][0].data["data"]["actions"]]
    assert actions == ["Done", "Snooze", "Dismiss"]

    for _ in range(8):  # light ladder: never other devices, never critical
        await advance(hass, freezer, minutes=5)
    assert sent(notify["extra"]) == []
    assert all("push" not in c.data["data"] for c in sent(notify["phone"]))
    assert len(notify["alexa"]) >= 1

    await hass.services.async_call(DOMAIN, "dismiss", {"task_id": task_id}, blocking=True)
    assert entry.runtime_data.tasks == {}


async def test_flag_on_means_not_dismissable_full_ladder(hass, freezer, notify, make_entry):
    await make_entry(type_data("papier", flag_entity=FLAG))
    hass.states.async_set(FLAG, "on")
    task_id = await _start(hass, "papier")
    assert [a["title"] for a in notify["phone"][0].data["data"]["actions"]] == ["Done", "Snooze"]
    with pytest.raises(ServiceValidationError, match="cannot be dismissed"):
        await hass.services.async_call(DOMAIN, "dismiss", {"task_id": task_id}, blocking=True)
    for _ in range(4):
        await advance(hass, freezer, minutes=5)
    assert len(notify["extra"]) >= 1
    assert any("push" in c.data["data"] for c in notify["phone"])


async def test_done_resets_flag_but_dismiss_does_not(hass, make_entry):
    turn_off = async_mock_service(hass, "homeassistant", "turn_off")
    await make_entry(type_data("papier", flag_entity=FLAG))
    hass.states.async_set(FLAG, "off")
    dismissed = await _start(hass, "papier")
    await hass.services.async_call(DOMAIN, "dismiss", {"task_id": dismissed}, blocking=True)
    assert turn_off == []

    hass.states.async_set(FLAG, "on")
    await _start(hass, "papier")
    await hass.services.async_call(DOMAIN, "done", {"type": "papier"}, blocking=True)
    assert [c.data["entity_id"] for c in turn_off] == [FLAG]


async def test_gft_quiet_heads_up_without_flag(hass, notify, make_entry):
    entry = await make_entry(
        type_data("gft", flag_entity="input_boolean.gft", quiet_without_flag=True)
    )
    hass.states.async_set("input_boolean.gft", "off")
    await _start(hass, "gft")
    assert len(notify["phone"]) == 2  # heads-up, then clear_notification
    assert notify["phone"][0].data["data"]["push"] == {"interruption-level": "passive"}
    assert notify["alexa"] == []
    assert entry.runtime_data.tasks == {}


async def test_gft_with_flag_reminds_normally(hass, notify, make_entry):
    entry = await make_entry(
        type_data("gft", flag_entity="input_boolean.gft", quiet_without_flag=True)
    )
    hass.states.async_set("input_boolean.gft", "on")
    await _start(hass, "gft")
    assert len(entry.runtime_data.tasks) == 1
    assert notify["phone"][0].data["message"] == "Gft is due"


async def test_two_door_sequence(hass, freezer, make_entry):
    entry = await make_entry(
        type_data(
            "restafval",
            done_entity="binary_sensor.back_door",
            done_then_entity="binary_sensor.porch_door",
            done_window_minutes=5,
        )
    )
    manager = entry.runtime_data

    async def open_door(entity):
        hass.states.async_set(entity, "off")
        hass.states.async_set(entity, "on")
        await hass.async_block_till_done()

    await _start(hass, "restafval")  # due now
    await open_door("binary_sensor.porch_door")  # porch alone: nothing
    assert len(manager.tasks) == 1
    await open_door("binary_sensor.back_door")
    assert len(manager.tasks) == 1  # back door alone does not complete it
    await open_door("binary_sensor.porch_door")
    assert manager.tasks == {}

    # Too slow: second door after the window does not count.
    await _start(hass, "restafval")
    await open_door("binary_sensor.back_door")
    freezer.tick(timedelta(minutes=6))
    await open_door("binary_sensor.porch_door")
    assert len(manager.tasks) == 1


async def test_bin_out_then_bin_back_with_the_same_two_doors(hass, freezer, notify, make_entry):
    """Put the bin out the evening before (schedule, 18:00), which starts "bring it back"
    (16:00 on collection day); both finish with the same back door + porch door sequence."""
    doors = {
        "done_entity": "binary_sensor.back_door",
        "done_then_entity": "binary_sensor.porch_door",
        "done_window_minutes": 5,
    }
    entry = await make_entry(
        type_data(
            "papier",
            schedule_entity="sensor.almere_papier",
            due_time="18:00:00",
            then_start="papier_back",
            **doors,
        ),
        type_data("papier_back", due_time="16:00:00", **doors),
    )
    manager = entry.runtime_data

    async def through_the_doors():
        for entity in ("binary_sensor.back_door", "binary_sensor.porch_door"):
            hass.states.async_set(entity, "off")
            hass.states.async_set(entity, "on")
            await hass.async_block_till_done()

    hass.states.async_set(
        "sensor.almere_papier", "x", {"Sort_date": 20261010, "Days_until": 1}
    )  # collection tomorrow
    await hass.async_block_till_done()
    await through_the_doors()  # before 18:00: nothing is due yet, nothing counts
    assert [t.type_key for t in manager.tasks.values()] == ["papier"]

    await advance(hass, freezer, hours=6)  # 18:00
    assert len(sent(notify["phone"])) == 1
    await through_the_doors()  # the bin is out
    assert [t.type_key for t in manager.tasks.values()] == ["papier_back"]

    await through_the_doors()  # the same doors again, too early: the bin is not back yet
    assert [t.type_key for t in manager.tasks.values()] == ["papier_back"]

    await advance(hass, freezer, hours=22)  # 16:00 on collection day
    assert sent(notify["phone"])[-1].data["message"] == "Papier_Back is due"
    await through_the_doors()  # the bin is back
    assert manager.tasks == {}
