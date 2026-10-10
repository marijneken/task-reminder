"""The room presence provider gives the area you are in; it decides which Alexa speaks first.
A speaker is found through the area of its media player in Home Assistant."""

from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.task_reminder.const import DOMAIN

from .conftest import advance, make_area, place_entity, type_data

PROVIDER = "sensor.room_presence"
LIVING, OFFICE = "alexa_media_echo_living_room", "alexa_media_echo_office"


def _speakers(hass):
    return {
        "living": async_mock_service(hass, "notify", LIVING),
        "office": async_mock_service(hass, "notify", OFFICE),
    }


async def _setup(hass, make_entry, **settings):
    """Two speakers, each with its media player in an area, and the provider as the source."""
    living, office = make_area(hass, "Living room"), make_area(hass, "Office")
    place_entity(hass, "media_player.echo_living_room", area_id=living)
    place_entity(hass, "media_player.echo_office", area_id=office)
    entry = await make_entry(
        type_data("washer"),
        **{"room_provider": PROVIDER, "alexa_services": [LIVING, OFFICE], **settings},
    )
    return entry, living, office


async def _start(hass):
    await hass.services.async_call(DOMAIN, "start", {"type": "washer"}, blocking=True)


async def test_second_reminder_goes_to_the_speaker_in_your_area(hass, freezer, notify, make_entry):
    speakers = _speakers(hass)
    hass.states.async_set(PROVIDER, "living_room")
    await _setup(hass, make_entry)

    await _start(hass)  # 1st: phone only
    assert speakers["living"] == [] and speakers["office"] == []
    await advance(hass, freezer, minutes=5)  # 2nd: the area you are in
    assert len(speakers["living"]) == 1 and speakers["office"] == []


async def test_third_reminder_goes_everywhere(hass, freezer, notify, make_entry):
    speakers = _speakers(hass)
    hass.states.async_set(PROVIDER, "living_room")
    await _setup(hass, make_entry)
    await _start(hass)
    for _ in range(2):
        await advance(hass, freezer, minutes=5)
    assert len(speakers["office"]) == 1 and len(speakers["living"]) == 2


async def test_follows_you_to_another_area(hass, freezer, notify, make_entry):
    speakers = _speakers(hass)
    hass.states.async_set(PROVIDER, "living_room")
    await _setup(hass, make_entry)
    await _start(hass)
    hass.states.async_set(PROVIDER, "office")
    await advance(hass, freezer, minutes=5)
    assert len(speakers["office"]) == 1 and speakers["living"] == []


async def test_a_speaker_gets_its_area_from_its_device(hass, freezer, notify, make_entry):
    speakers = _speakers(hass)
    entry = await make_entry(
        type_data("washer"), room_provider=PROVIDER, alexa_services=[LIVING, OFFICE]
    )
    living, den = make_area(hass, "Living room"), make_area(hass, "Den")
    place_entity(hass, "media_player.echo_living_room", area_id=living)
    # The office speaker has no area of its own: it takes the one of its device.
    place_entity(
        hass, "media_player.echo_office", device_area_id=den, config_entry_id=entry.entry_id
    )
    hass.states.async_set(PROVIDER, den)
    await _start(hass)
    await advance(hass, freezer, minutes=5)
    assert len(speakers["office"]) == 1 and speakers["living"] == []


async def test_an_entitys_own_area_wins_over_its_devices(hass, freezer, notify, make_entry):
    speakers = _speakers(hass)
    entry = await make_entry(
        type_data("washer"), room_provider=PROVIDER, alexa_services=[LIVING, OFFICE]
    )
    living, office, den = (make_area(hass, n) for n in ("Living room", "Office", "Den"))
    place_entity(hass, "media_player.echo_living_room", area_id=living)
    place_entity(
        hass,
        "media_player.echo_office",
        area_id=office,
        device_area_id=den,
        config_entry_id=entry.entry_id,
    )
    hass.states.async_set(PROVIDER, office)
    await _start(hass)
    await advance(hass, freezer, minutes=5)
    assert len(speakers["office"]) == 1 and speakers["living"] == []


async def test_every_speaker_in_the_area_speaks(hass, freezer, notify, make_entry):
    speakers = _speakers(hass)
    living = make_area(hass, "Living room")
    place_entity(hass, "media_player.echo_living_room", area_id=living)
    place_entity(hass, "media_player.echo_office", area_id=living)  # two speakers, one area
    await make_entry(type_data("washer"), room_provider=PROVIDER, alexa_services=[LIVING, OFFICE])
    hass.states.async_set(PROVIDER, living)
    await _start(hass)
    await advance(hass, freezer, minutes=5)
    assert len(speakers["living"]) == 1 and len(speakers["office"]) == 1


async def test_unknown_place_means_everywhere(hass, freezer, notify, make_entry):
    for state in ("unknown", "unavailable", "none", "away", "not_home", "", "no_such_area"):
        speakers = _speakers(hass)
        hass.states.async_set(PROVIDER, state)
        entry, *_ = await _setup(hass, make_entry)
        await _start(hass)
        await advance(hass, freezer, minutes=5)
        assert len(speakers["living"]) == 1 and len(speakers["office"]) == 1, state
        await hass.config_entries.async_remove(entry.entry_id)
        await hass.async_block_till_done()
        for calls in speakers.values():
            calls.clear()


async def test_no_provider_at_all_means_everywhere(hass, freezer, notify, make_entry):
    speakers = _speakers(hass)
    await _setup(hass, make_entry, room_provider=None)
    await _start(hass)
    await advance(hass, freezer, minutes=5)
    assert len(speakers["living"]) == 1 and len(speakers["office"]) == 1


async def test_an_area_without_a_speaker_means_everywhere(hass, freezer, notify, make_entry):
    speakers = _speakers(hass)
    make_area(hass, "Kitchen")
    hass.states.async_set(PROVIDER, "kitchen")  # a real area, but no speaker has it
    await _setup(hass, make_entry)
    await _start(hass)
    await advance(hass, freezer, minutes=5)
    assert len(speakers["living"]) == 1 and len(speakers["office"]) == 1


async def test_a_speaker_without_an_area_still_joins_the_wide_tier(
    hass, freezer, notify, make_entry
):
    speakers = _speakers(hass)
    living = make_area(hass, "Living room")
    place_entity(hass, "media_player.echo_living_room", area_id=living)
    # media_player.echo_office is not in any area (not even registered)
    await make_entry(type_data("washer"), room_provider=PROVIDER, alexa_services=[LIVING, OFFICE])
    hass.states.async_set(PROVIDER, living)
    await _start(hass)
    await advance(hass, freezer, minutes=5)
    assert len(speakers["living"]) == 1 and speakers["office"] == []  # only the one in the area
    await advance(hass, freezer, minutes=5)
    assert len(speakers["office"]) == 1  # everywhere from the third reminder


async def test_motion_sensors_are_not_used(hass, freezer, notify, make_entry):
    speakers = _speakers(hass)
    await _setup(hass, make_entry)  # the provider has no state at all
    hass.states.async_set("binary_sensor.motion_living_room", "on")
    await _start(hass)
    await advance(hass, freezer, minutes=5)
    assert len(speakers["living"]) == 1 and len(speakers["office"]) == 1


async def test_light_ladder_stays_in_your_area(hass, freezer, notify, make_entry):
    speakers = _speakers(hass)
    hass.states.async_set("input_boolean.papier", "off")  # nothing to take out
    living, office = make_area(hass, "Living room"), make_area(hass, "Office")
    place_entity(hass, "media_player.echo_living_room", area_id=living)
    place_entity(hass, "media_player.echo_office", area_id=office)
    await make_entry(
        type_data("papier", flag_entity="input_boolean.papier"),
        room_provider=PROVIDER,
        alexa_services=[LIVING, OFFICE],
    )
    hass.states.async_set(PROVIDER, living)
    await hass.services.async_call(DOMAIN, "start", {"type": "papier"}, blocking=True)
    for _ in range(5):
        await advance(hass, freezer, minutes=5)
    assert len(speakers["living"]) >= 3 and speakers["office"] == []


async def test_old_room_entries_are_ignored(hass, make_entry):
    from homeassistant.config_entries import ConfigSubentryData

    old_room = ConfigSubentryData(
        data={"key": "office", "name": "Office"},
        subentry_type="room",
        title="Office",
        unique_id="room_office",
    )
    entry = await make_entry(type_data("washer"), old_room)
    assert set(entry.runtime_data.types) == {"ad_hoc", "washer"}  # the leftover does no harm


async def test_the_hub_flow_accepts_a_room_provider(hass):
    from homeassistant.data_entry_flow import FlowResultType

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "person": "person.marijn",
            "phone_services": ["mobile_app_phone"],
            "alexa_services": [],
            "extra_services": [],
            "quiet_start": "23:00:00",
            "quiet_end": "07:00:00",
            "room_provider": PROVIDER,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["room_provider"] == PROVIDER
