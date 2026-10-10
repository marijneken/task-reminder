"""Pausing and resuming media, and the repair issue for missing notify services."""

from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.task_reminder.const import DOMAIN

from .conftest import advance, sent, type_data

TV = "media_player.living_room_tv"
SPOTIFY = "media_player.spotify"


async def _reach_wide_tier(hass, freezer):
    """Two unanswered reminders later: phone, then Alexa, then other devices."""
    await advance(hass, freezer, minutes=5)
    await advance(hass, freezer, minutes=5)


async def _start(hass, type_):
    await hass.services.async_call(DOMAIN, "start", {"type": type_}, blocking=True)


async def test_pauses_at_the_wide_tier_and_resumes_when_done(hass, freezer, notify, make_entry):
    pause = async_mock_service(hass, "media_player", "media_pause")
    play = async_mock_service(hass, "media_player", "media_play")
    await make_entry(type_data("washer"), pause_players=[TV, SPOTIFY, "media_player.idle"])
    hass.states.async_set(TV, "playing")
    hass.states.async_set(SPOTIFY, "playing")
    hass.states.async_set("media_player.idle", "idle")

    await _start(hass, "washer")  # level 0: phone only
    await advance(hass, freezer, minutes=5)  # level 1: + Alexa
    assert pause == []
    await advance(hass, freezer, minutes=5)  # level 2: + other devices, media pauses
    assert [c.data["entity_id"] for c in pause] == [[TV, SPOTIFY]]  # only what was playing

    await advance(hass, freezer, minutes=5)  # paused once per task, not again
    assert len(pause) == 1

    hass.states.async_set(TV, "paused")
    hass.states.async_set(SPOTIFY, "paused")
    await hass.services.async_call(DOMAIN, "done", {"type": "washer"}, blocking=True)
    assert [c.data["entity_id"] for c in play] == [[TV, SPOTIFY]]


async def test_does_not_resume_what_someone_else_resumed(hass, freezer, make_entry):
    pause = async_mock_service(hass, "media_player", "media_pause")
    play = async_mock_service(hass, "media_player", "media_play")
    await make_entry(type_data("washer"), pause_players=[TV])
    hass.states.async_set(TV, "playing")
    await _start(hass, "washer")
    await _reach_wide_tier(hass, freezer)
    assert len(pause) == 1  # it really was paused
    hass.states.async_set(TV, "playing")  # user pressed play themselves
    await hass.services.async_call(DOMAIN, "done", {"type": "washer"}, blocking=True)
    assert play == []


async def test_dismissing_also_resumes(hass, freezer, make_entry):
    async_mock_service(hass, "media_player", "media_pause")
    play = async_mock_service(hass, "media_player", "media_play")
    await make_entry(type_data("trash", dismissable=True), pause_players=[TV])
    hass.states.async_set(TV, "playing")
    await _start(hass, "trash")
    await _reach_wide_tier(hass, freezer)
    hass.states.async_set(TV, "paused")
    await hass.services.async_call(DOMAIN, "dismiss", {"type": "trash"}, blocking=True)
    assert len(play) == 1


async def test_light_tasks_never_pause_media(hass, freezer, make_entry):
    pause = async_mock_service(hass, "media_player", "media_pause")
    await make_entry(type_data("papier", flag_entity="input_boolean.papier"), pause_players=[TV])
    hass.states.async_set("input_boolean.papier", "off")  # nothing to take out: light ladder
    hass.states.async_set(TV, "playing")
    await _start(hass, "papier")
    for _ in range(6):
        await advance(hass, freezer, minutes=5)
    assert pause == []


async def test_failing_media_service_does_not_break_the_reminder(hass, freezer, notify, make_entry):
    await make_entry(type_data("washer"), pause_players=[TV])  # no media_player services exist
    hass.states.async_set(TV, "playing")
    await _start(hass, "washer")
    await _reach_wide_tier(hass, freezer)
    assert len(sent(notify["extra"])) == 1


async def test_repair_issue_when_no_notify_service(hass, make_entry):
    registry = ir.async_get(hass)
    entry = await make_entry(phone_services=[], alexa_speakers=[], extra_services=[])
    assert registry.async_get_issue(DOMAIN, "no_notify_services") is not None

    hass.config_entries.async_update_entry(
        entry, data={**entry.data, "phone_services": ["mobile_app_phone"]}
    )
    await hass.async_block_till_done()
    assert registry.async_get_issue(DOMAIN, "no_notify_services") is None


async def test_no_issue_when_configured(hass, make_entry):
    await make_entry()
    assert ir.async_get(hass).async_get_issue(DOMAIN, "no_notify_services") is None
