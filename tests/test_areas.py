"""The room presence provider gives the area you are in; it decides which Alexa speaks first.
A speaker is a media player, found through its area in Home Assistant. Nothing is matched by name."""

from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.task_reminder.const import DOMAIN

from .conftest import advance, hub_form, make_area, place_entity, type_data

PROVIDER = "sensor.room_presence"
LIVING, OFFICE = "media_player.echo_living_room", "media_player.echo_office"


class _Speakers:
    """What the one notify.alexa_media service was asked to announce, per speaker."""

    def __init__(self, hass):
        self.calls = async_mock_service(hass, "notify", "alexa_media")

    def count(self, speaker):
        return sum(speaker in call.data["target"] for call in self.calls)

    def clear(self):
        self.calls.clear()


def _speakers(hass):
    return _Speakers(hass)


async def _setup(hass, make_entry, **settings):
    """Two speakers, each with its media player in an area, and the provider as the source."""
    living, office = make_area(hass, "Living room"), make_area(hass, "Office")
    place_entity(hass, "media_player.echo_living_room", area_id=living)
    place_entity(hass, "media_player.echo_office", area_id=office)
    entry = await make_entry(
        type_data("washer"),
        **{"room_provider": PROVIDER, "alexa_speakers": [LIVING, OFFICE], **settings},
    )
    return entry, living, office


async def _start(hass):
    await hass.services.async_call(DOMAIN, "start", {"type": "washer"}, blocking=True)


async def test_second_reminder_goes_to_the_speaker_in_your_area(hass, freezer, notify, make_entry):
    speakers = _speakers(hass)
    hass.states.async_set(PROVIDER, "living_room")
    await _setup(hass, make_entry)

    await _start(hass)  # 1st: phone only
    assert speakers.count(LIVING) == 0 and speakers.count(OFFICE) == 0
    await advance(hass, freezer, minutes=5)  # 2nd: the area you are in
    assert speakers.count(LIVING) == 1 and speakers.count(OFFICE) == 0


async def test_third_reminder_goes_everywhere(hass, freezer, notify, make_entry):
    speakers = _speakers(hass)
    hass.states.async_set(PROVIDER, "living_room")
    await _setup(hass, make_entry)
    await _start(hass)
    for _ in range(2):
        await advance(hass, freezer, minutes=5)
    assert speakers.count(OFFICE) == 1 and speakers.count(LIVING) == 2


async def test_follows_you_to_another_area(hass, freezer, notify, make_entry):
    speakers = _speakers(hass)
    hass.states.async_set(PROVIDER, "living_room")
    await _setup(hass, make_entry)
    await _start(hass)
    hass.states.async_set(PROVIDER, "office")
    await advance(hass, freezer, minutes=5)
    assert speakers.count(OFFICE) == 1 and speakers.count(LIVING) == 0


async def test_a_speaker_gets_its_area_from_its_device(hass, freezer, notify, make_entry):
    speakers = _speakers(hass)
    entry = await make_entry(
        type_data("washer"), room_provider=PROVIDER, alexa_speakers=[LIVING, OFFICE]
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
    assert speakers.count(OFFICE) == 1 and speakers.count(LIVING) == 0


async def test_an_entitys_own_area_wins_over_its_devices(hass, freezer, notify, make_entry):
    speakers = _speakers(hass)
    entry = await make_entry(
        type_data("washer"), room_provider=PROVIDER, alexa_speakers=[LIVING, OFFICE]
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
    assert speakers.count(OFFICE) == 1 and speakers.count(LIVING) == 0


async def test_every_speaker_in_the_area_speaks(hass, freezer, notify, make_entry):
    speakers = _speakers(hass)
    living = make_area(hass, "Living room")
    place_entity(hass, "media_player.echo_living_room", area_id=living)
    place_entity(hass, "media_player.echo_office", area_id=living)  # two speakers, one area
    await make_entry(type_data("washer"), room_provider=PROVIDER, alexa_speakers=[LIVING, OFFICE])
    hass.states.async_set(PROVIDER, living)
    await _start(hass)
    await advance(hass, freezer, minutes=5)
    assert speakers.count(LIVING) == 1 and speakers.count(OFFICE) == 1


async def test_unknown_place_means_everywhere(hass, freezer, notify, make_entry):
    for state in ("unknown", "unavailable", "none", "away", "not_home", "", "no_such_area"):
        speakers = _speakers(hass)
        hass.states.async_set(PROVIDER, state)
        entry, *_ = await _setup(hass, make_entry)
        await _start(hass)
        await advance(hass, freezer, minutes=5)
        assert speakers.count(LIVING) == 1 and speakers.count(OFFICE) == 1, state
        await hass.config_entries.async_remove(entry.entry_id)
        await hass.async_block_till_done()
        speakers.clear()


async def test_no_provider_at_all_means_everywhere(hass, freezer, notify, make_entry):
    speakers = _speakers(hass)
    await _setup(hass, make_entry, room_provider=None)
    await _start(hass)
    await advance(hass, freezer, minutes=5)
    assert speakers.count(LIVING) == 1 and speakers.count(OFFICE) == 1


async def test_an_area_without_a_speaker_means_everywhere(hass, freezer, notify, make_entry):
    speakers = _speakers(hass)
    make_area(hass, "Kitchen")
    hass.states.async_set(PROVIDER, "kitchen")  # a real area, but no speaker has it
    await _setup(hass, make_entry)
    await _start(hass)
    await advance(hass, freezer, minutes=5)
    assert speakers.count(LIVING) == 1 and speakers.count(OFFICE) == 1


async def test_a_speaker_without_an_area_still_joins_the_wide_tier(
    hass, freezer, notify, make_entry
):
    speakers = _speakers(hass)
    living = make_area(hass, "Living room")
    place_entity(hass, "media_player.echo_living_room", area_id=living)
    # media_player.echo_office is not in any area (not even registered)
    await make_entry(type_data("washer"), room_provider=PROVIDER, alexa_speakers=[LIVING, OFFICE])
    hass.states.async_set(PROVIDER, living)
    await _start(hass)
    await advance(hass, freezer, minutes=5)
    assert speakers.count(LIVING) == 1 and speakers.count(OFFICE) == 0  # only the one in the area
    await advance(hass, freezer, minutes=5)
    assert speakers.count(OFFICE) == 1  # everywhere from the third reminder


async def test_motion_sensors_are_not_used(hass, freezer, notify, make_entry):
    speakers = _speakers(hass)
    await _setup(hass, make_entry)  # the provider has no state at all
    hass.states.async_set("binary_sensor.motion_living_room", "on")
    await _start(hass)
    await advance(hass, freezer, minutes=5)
    assert speakers.count(LIVING) == 1 and speakers.count(OFFICE) == 1


async def test_light_ladder_stays_in_your_area(hass, freezer, notify, make_entry):
    speakers = _speakers(hass)
    hass.states.async_set("input_boolean.papier", "off")  # nothing to take out
    living, office = make_area(hass, "Living room"), make_area(hass, "Office")
    place_entity(hass, "media_player.echo_living_room", area_id=living)
    place_entity(hass, "media_player.echo_office", area_id=office)
    await make_entry(
        type_data("papier", flag_entity="input_boolean.papier"),
        room_provider=PROVIDER,
        alexa_speakers=[LIVING, OFFICE],
    )
    hass.states.async_set(PROVIDER, living)
    await hass.services.async_call(DOMAIN, "start", {"type": "papier"}, blocking=True)
    for _ in range(5):
        await advance(hass, freezer, minutes=5)
    assert speakers.count(LIVING) >= 3 and speakers.count(OFFICE) == 0


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
        hub_form(
            person="person.marijn", phone_services=["mobile_app_phone"], room_provider=PROVIDER
        ),
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["room_provider"] == PROVIDER


async def test_speaker_names_do_not_matter(hass, freezer, notify, make_entry):
    speakers = _speakers(hass)
    den, loft = make_area(hass, "Den"), make_area(hass, "Loft")
    place_entity(hass, "media_player.marijns_echo_dot", area_id=den)
    place_entity(hass, "media_player.echo_dot_2", area_id=loft)
    await make_entry(
        type_data("washer"),
        room_provider=PROVIDER,
        alexa_speakers=["media_player.marijns_echo_dot", "media_player.echo_dot_2"],
    )
    hass.states.async_set(PROVIDER, loft)
    await _start(hass)
    await advance(hass, freezer, minutes=5)
    assert [c.data["target"] for c in speakers.calls] == [["media_player.echo_dot_2"]]
    await advance(hass, freezer, minutes=5)  # everywhere: one announcement, both targets
    assert speakers.calls[-1].data["target"] == [
        "media_player.marijns_echo_dot",
        "media_player.echo_dot_2",
    ]
    assert speakers.calls[-1].data["data"] == {"type": "announce"}
