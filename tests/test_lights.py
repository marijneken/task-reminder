"""Lights as the last annoyance of the keeps-going stage: the lights of the area you are in."""

from datetime import UTC, datetime

from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.task_reminder.const import DOMAIN

from .conftest import advance, make_area, type_data

PROVIDER = "sensor.room_presence"


async def _start(hass, type_="washer"):
    await hass.services.async_call(DOMAIN, "start", {"type": type_}, blocking=True)


async def _to_keeps_going(hass, freezer):
    """Phone, Alexa, other devices; the next reminder is the first of the keeps-going stage."""
    for _ in range(2):
        await advance(hass, freezer, minutes=5)


async def test_the_lights_of_the_area_you_are_in_flash(hass, freezer, make_entry):
    flash = async_mock_service(hass, "light", "turn_on")
    area = make_area(hass, "Living room")
    hass.states.async_set(PROVIDER, area)
    await make_entry(type_data("washer"), room_provider=PROVIDER)
    await _start(hass)
    await _to_keeps_going(hass, freezer)
    assert flash == []  # nothing before the keeps-going stage

    await advance(hass, freezer, minutes=5)  # first keeps-going reminder
    assert len(flash) == 1
    assert flash[0].data["area_id"] == area and flash[0].data["flash"] == "long"
    await advance(hass, freezer, minutes=2)
    await advance(hass, freezer, minutes=2)
    assert len(flash) == 3  # and again with each following reminder


async def test_it_follows_you_to_another_area(hass, freezer, make_entry):
    flash = async_mock_service(hass, "light", "turn_on")
    living, office = make_area(hass, "Living room"), make_area(hass, "Office")
    hass.states.async_set(PROVIDER, living)
    await make_entry(type_data("washer"), room_provider=PROVIDER)
    await _start(hass)
    await _to_keeps_going(hass, freezer)
    await advance(hass, freezer, minutes=5)
    hass.states.async_set(PROVIDER, office)
    await advance(hass, freezer, minutes=2)
    assert [c.data["area_id"] for c in flash] == [living, office]


async def test_nothing_flashes_when_you_are_nowhere_we_know(hass, freezer, make_entry):
    flash = async_mock_service(hass, "light", "turn_on")
    make_area(hass, "Living room")
    await make_entry(type_data("washer"), room_provider=PROVIDER)
    for state in ("none", "away", "somewhere_else"):
        hass.states.async_set(PROVIDER, state)
        await _start(hass)
        await _to_keeps_going(hass, freezer)
        await advance(hass, freezer, minutes=5)
        await hass.services.async_call(DOMAIN, "done", {"type": "washer"}, blocking=True)
    assert flash == []


async def test_nothing_flashes_without_a_provider_or_a_known_area(hass, freezer, make_entry):
    flash = async_mock_service(hass, "light", "turn_on")
    await make_entry(type_data("washer"))  # no provider, no rooms
    await _start(hass)
    await _to_keeps_going(hass, freezer)
    await advance(hass, freezer, minutes=5)
    assert flash == []


async def test_never_while_silencing_is_active(hass, freezer, make_entry):
    flash = async_mock_service(hass, "light", "turn_on")
    hass.states.async_set(PROVIDER, make_area(hass, "Living room"))
    await make_entry(type_data("washer"), room_provider=PROVIDER)
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
    hass.states.async_set(PROVIDER, make_area(hass, "Living room"))
    await make_entry(
        type_data("papier", flag_entity="input_boolean.papier"), room_provider=PROVIDER
    )
    hass.states.async_set("input_boolean.papier", "off")  # nothing to take out
    await _start(hass, "papier")
    for _ in range(8):
        await advance(hass, freezer, minutes=5)
    assert flash == []


async def test_a_failing_light_does_not_break_reminding(hass, freezer, notify, make_entry):
    hass.states.async_set(PROVIDER, make_area(hass, "Living room"))
    await make_entry(type_data("washer"), room_provider=PROVIDER)  # no light service exists
    await _start(hass)
    await _to_keeps_going(hass, freezer)

    def count():
        return len([c for c in notify["phone"] if c.data["message"] != "clear_notification"])

    before = count()
    await advance(hass, freezer, minutes=5)
    assert count() == before + 1


async def test_ringing_repeats_do_not_flash_again(hass, freezer, make_entry):
    flash = async_mock_service(hass, "light", "turn_on")
    hass.states.async_set(PROVIDER, make_area(hass, "Living room"))
    await make_entry(type_data("alarm", ring=True, snooze_minutes="1"), room_provider=PROVIDER)
    await _start(hass, "alarm")
    await advance(hass, freezer, minutes=5)  # the first keeps-going reminder flashes once
    assert len(flash) == 1
    for _ in range(5):
        await advance(hass, freezer, seconds=12)  # ring re-triggers: sound only
    assert len(flash) == 1
