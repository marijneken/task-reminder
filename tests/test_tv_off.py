"""The last step of the escalation ladder: turn the TV off."""

from datetime import UTC, datetime

from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.task_reminder.const import DOMAIN

from .conftest import advance, sent, type_data

TV = "media_player.living_room_tv"
LG = "media_player.lg_tv"


async def _start(hass, type_="washer"):
    await hass.services.async_call(DOMAIN, "start", {"type": type_}, blocking=True)


async def _to_keeps_going(hass, freezer):
    """Phone, Alexa, other devices, then the first keeps-going reminder (snoozes used up)."""
    for _ in range(3):
        await advance(hass, freezer, minutes=5)


async def test_tv_goes_off_at_the_second_keeps_going_reminder(hass, freezer, make_entry):
    off = async_mock_service(hass, "media_player", "turn_off")
    async_mock_service(hass, "media_player", "media_pause")
    await make_entry(type_data("washer"), turn_off_players=[TV, LG])
    hass.states.async_set(TV, "playing")
    hass.states.async_set(LG, "off")  # already off: left alone
    await _start(hass)
    await _to_keeps_going(hass, freezer)
    assert off == []  # first keeps-going reminder: critical alert only, TV untouched

    await advance(hass, freezer, minutes=2)  # second keeps-going reminder
    assert [c.data["entity_id"] for c in off] == [[TV]]

    await advance(hass, freezer, minutes=2)  # not again for the same task
    assert len(off) == 1


async def test_never_while_silencing_is_active(hass, freezer, make_entry):
    off = async_mock_service(hass, "media_player", "turn_off")
    await make_entry(type_data("washer"), turn_off_players=[TV])
    hass.states.async_set(TV, "playing")
    await hass.services.async_call(
        DOMAIN,
        "silence",
        {"mode": "no_critical", "until": datetime(2026, 10, 9, 20, 0, tzinfo=UTC)},
        blocking=True,
    )
    await _start(hass)
    for _ in range(3):
        await advance(hass, freezer, minutes=5)
    for _ in range(3):
        await advance(hass, freezer, minutes=2)
    assert off == []


async def test_light_tasks_never_turn_the_tv_off(hass, freezer, make_entry):
    off = async_mock_service(hass, "media_player", "turn_off")
    await make_entry(type_data("papier", flag_entity="input_boolean.papier"), turn_off_players=[TV])
    hass.states.async_set("input_boolean.papier", "off")
    hass.states.async_set(TV, "playing")
    await _start(hass, "papier")
    for _ in range(8):
        await advance(hass, freezer, minutes=5)
    assert off == []


async def test_nothing_happens_without_chosen_players(hass, freezer, make_entry):
    off = async_mock_service(hass, "media_player", "turn_off")
    await make_entry(type_data("washer"))
    hass.states.async_set(TV, "playing")
    await _start(hass)
    await _to_keeps_going(hass, freezer)
    await advance(hass, freezer, minutes=2)
    assert off == []


async def test_a_failing_tv_does_not_break_reminding(hass, freezer, notify, make_entry):
    await make_entry(type_data("washer"), turn_off_players=[TV])  # no media_player services exist
    hass.states.async_set(TV, "playing")
    await _start(hass)
    await _to_keeps_going(hass, freezer)
    before = len(sent(notify["phone"]))
    await advance(hass, freezer, minutes=2)
    assert len(sent(notify["phone"])) == before + 1


async def test_the_tv_is_not_turned_back_on_when_done(hass, freezer, make_entry):
    off = async_mock_service(hass, "media_player", "turn_off")
    on = async_mock_service(hass, "media_player", "turn_on")
    await make_entry(type_data("washer"), turn_off_players=[TV])
    hass.states.async_set(TV, "playing")
    await _start(hass)
    await _to_keeps_going(hass, freezer)
    await advance(hass, freezer, minutes=2)
    assert len(off) == 1
    await hass.services.async_call(DOMAIN, "done", {"type": "washer"}, blocking=True)
    assert on == []


# --- anything that is on goes off -------------------------------------------------------------


async def _run_to_turn_off(hass, freezer):
    await _start(hass)
    await _to_keeps_going(hass, freezer)
    await advance(hass, freezer, minutes=2)  # the 2nd keeps-going reminder


async def test_a_paused_or_idle_player_goes_off_too(hass, freezer, make_entry):
    off = async_mock_service(hass, "media_player", "turn_off")
    async_mock_service(hass, "media_player", "media_pause")
    await make_entry(type_data("washer"), turn_off_players=[TV, LG, "media_player.atv"])
    hass.states.async_set(TV, "paused")
    hass.states.async_set(LG, "on")
    hass.states.async_set("media_player.atv", "idle")
    await _run_to_turn_off(hass, freezer)
    assert [c.data["entity_id"] for c in off] == [[TV, LG, "media_player.atv"]]


async def test_players_that_are_not_on_are_left_alone(hass, freezer, make_entry):
    off = async_mock_service(hass, "media_player", "turn_off")
    async_mock_service(hass, "media_player", "media_pause")
    states = {
        TV: "off",
        LG: "standby",
        "media_player.a": "unavailable",
        "media_player.b": "unknown",
    }
    await make_entry(type_data("washer"), turn_off_players=list(states))
    for entity_id, state in states.items():
        hass.states.async_set(entity_id, state)
    await _run_to_turn_off(hass, freezer)
    assert off == []


async def test_where_you_are_does_not_matter_for_turning_off(hass, freezer, make_entry):
    """A paused TV in the living room goes off while you are in the office, and a TV with no
    area at all goes off too: the setting is the list of what to turn off."""
    from .conftest import make_area, place_entity

    off = async_mock_service(hass, "media_player", "turn_off")
    async_mock_service(hass, "media_player", "media_pause")
    place_entity(hass, TV, area_id=make_area(hass, "Living room"))
    hass.states.async_set(TV, "paused")
    hass.states.async_set(LG, "on")  # no area
    hass.states.async_set("sensor.room_presence", make_area(hass, "Office"))
    await make_entry(
        type_data("washer"), turn_off_players=[TV, LG], room_provider="sensor.room_presence"
    )
    await _run_to_turn_off(hass, freezer)
    assert [c.data["entity_id"] for c in off] == [[TV, LG]]


async def test_tries_again_when_the_tv_was_not_on_at_the_time(hass, freezer, make_entry, caplog):
    import logging

    off = async_mock_service(hass, "media_player", "turn_off")
    await make_entry(type_data("washer"), turn_off_players=[TV])
    hass.states.async_set(TV, "off")
    await _start(hass)
    await _to_keeps_going(hass, freezer)
    with caplog.at_level(logging.INFO):
        await advance(hass, freezer, minutes=2)  # second keeps-going reminder: TV is off
    assert off == []
    assert f"Not turning off {TV}: it is off" in caplog.text  # and it says why

    hass.states.async_set(TV, "on")  # the TV was switched on in the meantime
    await advance(hass, freezer, minutes=2)
    assert [c.data["entity_id"] for c in off] == [[TV]]
