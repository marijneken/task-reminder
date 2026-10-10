"""Lights as the last annoyance of the keeps-going stage."""

from datetime import UTC, datetime

from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.task_reminder.const import DOMAIN

from .conftest import advance, type_data

LIGHTS = ["light.living_room", "light.hallway"]


async def _start(hass, type_="washer"):
    await hass.services.async_call(DOMAIN, "start", {"type": type_}, blocking=True)


async def _to_keeps_going(hass, freezer):
    """Phone, Alexa, other devices; the next reminder is the first of the keeps-going stage."""
    for _ in range(2):
        await advance(hass, freezer, minutes=5)


async def test_lights_flash_with_every_keeps_going_reminder(hass, freezer, make_entry):
    flash = async_mock_service(hass, "light", "turn_on")
    await make_entry(type_data("washer"), flash_lights=LIGHTS)
    await _start(hass)
    await _to_keeps_going(hass, freezer)
    assert flash == []  # nothing before the keeps-going stage

    await advance(hass, freezer, minutes=5)  # first keeps-going reminder
    assert len(flash) == 1
    assert flash[0].data["entity_id"] == LIGHTS and flash[0].data["flash"] == "long"
    await advance(hass, freezer, minutes=2)
    await advance(hass, freezer, minutes=2)
    assert len(flash) == 3  # and again with each following reminder


async def test_nothing_is_flashed_without_chosen_lights(hass, freezer, make_entry):
    flash = async_mock_service(hass, "light", "turn_on")
    await make_entry(type_data("washer"))
    await _start(hass)
    await _to_keeps_going(hass, freezer)
    await advance(hass, freezer, minutes=5)
    assert flash == []


async def test_never_while_silencing_is_active(hass, freezer, make_entry):
    flash = async_mock_service(hass, "light", "turn_on")
    await make_entry(type_data("washer"), flash_lights=LIGHTS)
    await hass.services.async_call(
        DOMAIN,
        "silence",
        {"mode": "no_critical", "until": datetime(2026, 10, 9, 20, 0, tzinfo=UTC)},
        blocking=True,
    )
    await _start(hass)
    for _ in range(5):
        await advance(hass, freezer, minutes=5)
    assert flash == []


async def test_not_for_the_light_ladder(hass, freezer, make_entry):
    flash = async_mock_service(hass, "light", "turn_on")
    await make_entry(type_data("papier", flag_entity="input_boolean.papier"), flash_lights=LIGHTS)
    hass.states.async_set("input_boolean.papier", "off")  # nothing to take out
    await _start(hass, "papier")
    for _ in range(8):
        await advance(hass, freezer, minutes=5)
    assert flash == []


async def test_a_failing_light_does_not_break_reminding(hass, freezer, notify, make_entry):
    await make_entry(type_data("washer"), flash_lights=LIGHTS)  # no light service exists
    await _start(hass)
    await _to_keeps_going(hass, freezer)
    before = len([c for c in notify["phone"] if c.data["message"] != "clear_notification"])
    await advance(hass, freezer, minutes=5)
    assert (
        len([c for c in notify["phone"] if c.data["message"] != "clear_notification"]) == before + 1
    )


async def test_ringing_repeats_do_not_flash_again(hass, freezer, make_entry):
    flash = async_mock_service(hass, "light", "turn_on")
    await make_entry(type_data("alarm", ring=True, snooze_minutes="1"), flash_lights=LIGHTS)
    await _start(hass, "alarm")
    await advance(hass, freezer, minutes=5)  # the first keeps-going reminder flashes once
    assert len(flash) == 1
    for _ in range(5):
        await advance(hass, freezer, seconds=12)  # ring re-triggers: sound only
    assert len(flash) == 1
