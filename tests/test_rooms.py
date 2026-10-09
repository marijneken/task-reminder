"""Room-aware Alexa routing."""

from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.task_reminder.const import DOMAIN, SUBENTRY_ROOM

from .conftest import advance, room_data, type_data

LIVING = "binary_sensor.motion_living_room"
OFFICE = "binary_sensor.motion_office"


def _speakers(hass):
    return {
        "living": async_mock_service(hass, "notify", "alexa_media_echo_living_room"),
        "office": async_mock_service(hass, "notify", "alexa_media_echo_office"),
    }


async def _setup(make_entry, **kwargs):
    return await make_entry(
        type_data("washer"),
        room_data("living_room", [LIVING], "alexa_media_echo_living_room"),
        room_data("office", [OFFICE], "alexa_media_echo_office"),
        room_data("hallway", ["binary_sensor.motion_hallway"]),  # no speaker
        **kwargs,
    )


async def _start(hass):
    await hass.services.async_call(DOMAIN, "start", {"type": "washer"}, blocking=True)


async def test_second_reminder_goes_to_the_room_you_are_in(hass, freezer, notify, make_entry):
    speakers = _speakers(hass)
    hass.states.async_set(LIVING, "on")
    await _setup(make_entry)

    await _start(hass)  # 1st: phone only
    assert speakers["living"] == [] and speakers["office"] == []
    await advance(hass, freezer, minutes=5)  # 2nd: the room you are in
    assert len(speakers["living"]) == 1
    assert speakers["office"] == [] and notify["alexa"] == []  # not the hub's default speaker


async def test_third_reminder_goes_everywhere(hass, freezer, notify, make_entry):
    speakers = _speakers(hass)
    hass.states.async_set(LIVING, "on")
    await _setup(make_entry)
    await _start(hass)
    for _ in range(2):
        await advance(hass, freezer, minutes=5)
    assert len(speakers["office"]) == 1  # widened
    assert len(notify["alexa"]) == 1  # the hub's own list too
    assert len(speakers["living"]) == 2


async def test_follows_you_to_another_room(hass, freezer, notify, make_entry):
    speakers = _speakers(hass)
    hass.states.async_set(LIVING, "on")
    await _setup(make_entry)
    await _start(hass)
    hass.states.async_set(LIVING, "off")
    freezer.tick(1)
    hass.states.async_set(OFFICE, "on")
    await hass.async_block_till_done()
    await advance(hass, freezer, minutes=5)
    assert len(speakers["office"]) == 1 and speakers["living"] == []


async def _presence_ended_then_task(hass, make_entry, minutes_until_due):
    speakers = _speakers(hass)
    await make_entry(
        type_data("washer", duration_minutes=minutes_until_due),
        room_data("living_room", [LIVING], "alexa_media_echo_living_room"),
        room_data("office", [OFFICE], "alexa_media_echo_office"),
    )
    hass.states.async_set(OFFICE, "on")
    await hass.async_block_till_done()
    hass.states.async_set(OFFICE, "off")  # PIR timed out: you may be sitting still
    await hass.async_block_till_done()
    await _start(hass)
    return speakers


async def test_recent_presence_still_counts(hass, freezer, notify, make_entry):
    speakers = await _presence_ended_then_task(hass, make_entry, minutes_until_due=2)
    await advance(hass, freezer, minutes=2)  # due: phone only
    await advance(hass, freezer, minutes=5)  # 2nd reminder, 7 minutes after the last motion
    assert len(speakers["office"]) == 1 and speakers["living"] == []


async def test_old_presence_means_everywhere(hass, freezer, notify, make_entry):
    speakers = await _presence_ended_then_task(hass, make_entry, minutes_until_due=8)
    await advance(hass, freezer, minutes=8)  # due: phone only
    await advance(hass, freezer, minutes=5)  # 2nd reminder, 13 minutes after the last motion
    assert len(speakers["office"]) == 1 and len(speakers["living"]) == 1  # stale: both


async def test_unknown_room_means_everywhere(hass, freezer, notify, make_entry):
    speakers = _speakers(hass)
    await _setup(make_entry)
    await _start(hass)
    await advance(hass, freezer, minutes=5)
    assert len(speakers["living"]) == 1 and len(speakers["office"]) == 1
    assert len(notify["alexa"]) == 1


async def test_room_without_a_speaker_means_everywhere(hass, freezer, notify, make_entry):
    speakers = _speakers(hass)
    hass.states.async_set("binary_sensor.motion_hallway", "on")
    await _setup(make_entry)
    await _start(hass)
    await advance(hass, freezer, minutes=5)
    assert len(speakers["living"]) == 1 and len(speakers["office"]) == 1


async def test_room_speakers_join_the_hub_list_without_being_listed_there(
    hass, freezer, notify, make_entry
):
    speakers = _speakers(hass)
    await _setup(make_entry, alexa_services=[])  # hub lists no speakers at all
    await _start(hass)
    await advance(hass, freezer, minutes=5)
    assert len(speakers["living"]) == 1 and len(speakers["office"]) == 1


async def test_light_ladder_stays_in_the_room(hass, freezer, notify, make_entry):
    speakers = _speakers(hass)
    hass.states.async_set(LIVING, "on")
    hass.states.async_set("input_boolean.papier", "off")  # nothing to take out
    await make_entry(
        type_data("papier", flag_entity="input_boolean.papier"),
        room_data("living_room", [LIVING], "alexa_media_echo_living_room"),
        room_data("office", [OFFICE], "alexa_media_echo_office"),
    )
    await hass.services.async_call(DOMAIN, "start", {"type": "papier"}, blocking=True)
    for _ in range(5):
        await advance(hass, freezer, minutes=5)
    assert len(speakers["living"]) >= 3 and speakers["office"] == []


async def test_task_types_ignore_room_entries(hass, make_entry):
    entry = await _setup(make_entry)
    assert set(entry.runtime_data.types) == {"ad_hoc", "washer"}
    assert set(entry.runtime_data.rooms) == {"living_room", "office", "hallway"}


async def test_room_flow_add_edit_and_duplicates(hass, make_entry):
    entry = await make_entry()
    flow = hass.config_entries.subentries
    result = await flow.async_init((entry.entry_id, SUBENTRY_ROOM), context={"source": "user"})
    result = await flow.async_configure(
        result["flow_id"],
        {
            "name": "Kitchen",
            "presence_entities": ["binary_sensor.motion_kitchen"],
            "alexa_service": "alexa_media_echo_living_room",
        },
    )
    assert result["type"].value == "create_entry"
    await hass.async_block_till_done()
    assert entry.runtime_data.rooms["kitchen"].alexa_service == "alexa_media_echo_living_room"

    dup = await flow.async_init((entry.entry_id, SUBENTRY_ROOM), context={"source": "user"})
    dup = await flow.async_configure(dup["flow_id"], {"name": "kitchen"})
    assert dup["errors"] == {"name": "already_exists"}

    (subentry,) = entry.subentries.values()
    edit = await flow.async_init(
        (entry.entry_id, SUBENTRY_ROOM),
        context={"source": "reconfigure", "subentry_id": subentry.subentry_id},
    )
    edit = await flow.async_configure(edit["flow_id"], {"name": "Kitchen", "alexa_service": "x"})
    assert edit["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert entry.runtime_data.rooms["kitchen"].alexa_service == "x"
