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


# --- the decision follows where you are ------------------------------------------------------

PROVIDER = "sensor.room_presence"


async def _setup_tvs(hass, make_entry, **players):
    """players: entity id -> (state, area name or None). Areas become real HA areas."""
    from .conftest import make_area, place_entity

    for entity_id, (state, area_name) in players.items():
        area = make_area(hass, area_name) if area_name else None
        if area:
            place_entity(hass, entity_id, area_id=area)
        hass.states.async_set(entity_id, state)
    await make_entry(type_data("washer"), turn_off_players=list(players), room_provider=PROVIDER)


async def _run_to_turn_off(hass, freezer):
    await _start(hass)
    await _to_keeps_going(hass, freezer)
    await advance(hass, freezer, minutes=2)  # the 2nd keeps-going reminder


async def test_a_tv_in_your_area_goes_off_even_when_paused(hass, freezer, make_entry):
    off = async_mock_service(hass, "media_player", "turn_off")
    async_mock_service(hass, "media_player", "media_pause")
    hass.states.async_set(PROVIDER, "living_room")
    await _setup_tvs(hass, make_entry, **{TV: ("paused", "Living room")})
    await _run_to_turn_off(hass, freezer)
    assert [c.data["entity_id"] for c in off] == [[TV]]


async def test_a_tv_in_another_area_that_is_not_playing_is_left_alone(hass, freezer, make_entry):
    off = async_mock_service(hass, "media_player", "turn_off")
    async_mock_service(hass, "media_player", "media_pause")
    hass.states.async_set(PROVIDER, "office")  # you are in the office, the TV is in the living room
    await _setup_tvs(hass, make_entry, **{TV: ("idle", "Living room")})
    from .conftest import make_area

    make_area(hass, "Office")
    await _run_to_turn_off(hass, freezer)
    assert off == []


async def test_a_playing_tv_goes_off_wherever_you_are(hass, freezer, make_entry):
    off = async_mock_service(hass, "media_player", "turn_off")
    async_mock_service(hass, "media_player", "media_pause")
    hass.states.async_set(PROVIDER, "office")
    await _setup_tvs(hass, make_entry, **{TV: ("playing", "Living room")})
    from .conftest import make_area

    make_area(hass, "Office")
    await _run_to_turn_off(hass, freezer)
    assert [c.data["entity_id"] for c in off] == [[TV]]  # a playing TV means someone is watching


async def test_only_the_tv_you_are_watching_goes_off(hass, freezer, make_entry):
    off = async_mock_service(hass, "media_player", "turn_off")
    async_mock_service(hass, "media_player", "media_pause")
    hass.states.async_set(PROVIDER, "living_room")
    await _setup_tvs(
        hass,
        make_entry,
        **{TV: ("paused", "Living room"), LG: ("paused", "Bedroom")},
    )
    await _run_to_turn_off(hass, freezer)
    assert [c.data["entity_id"] for c in off] == [[TV]]


async def test_unknown_place_turns_off_any_tv_that_is_on(hass, freezer, make_entry):
    for state in ("unknown", "unavailable", "none", "no_such_area"):
        off = async_mock_service(hass, "media_player", "turn_off")
        async_mock_service(hass, "media_player", "media_pause")
        hass.states.async_set(PROVIDER, state)
        await _setup_tvs(hass, make_entry, **{TV: ("idle", "Living room"), LG: ("off", None)})
        await _run_to_turn_off(hass, freezer)
        assert [c.data["entity_id"] for c in off] == [[TV]], state  # the one that is on
        for entry in hass.config_entries.async_entries(DOMAIN):
            await hass.config_entries.async_remove(entry.entry_id)
        await hass.async_block_till_done()


async def test_a_tv_without_an_area_is_only_turned_off_when_playing(hass, freezer, make_entry):
    off = async_mock_service(hass, "media_player", "turn_off")
    async_mock_service(hass, "media_player", "media_pause")
    from .conftest import make_area

    make_area(hass, "Living room")
    hass.states.async_set(PROVIDER, "living_room")
    await _setup_tvs(hass, make_entry, **{TV: ("paused", None)})  # no area: cannot be matched
    await _run_to_turn_off(hass, freezer)
    assert off == []


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
    assert f"Not turning off {TV}: state off" in caplog.text  # and it says why

    hass.states.async_set(TV, "on")  # the TV was switched on in the meantime
    await advance(hass, freezer, minutes=2)
    assert [c.data["entity_id"] for c in off] == [[TV]]
