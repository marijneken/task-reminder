"""Custom notification sound."""

from custom_components.task_reminder.const import DOMAIN

from .conftest import advance, sent, type_data


async def _start(hass, type_):
    await hass.services.async_call(DOMAIN, "start", {"type": type_}, blocking=True)


async def test_no_sound_by_default(hass, notify, make_entry):
    await make_entry(type_data("washer"))
    await _start(hass, "washer")
    assert "push" not in notify["phone"][0].data["data"]


async def test_hub_sound_on_normal_reminders(hass, notify, make_entry):
    await make_entry(type_data("washer"), notification_sound="reminder.wav")
    await _start(hass, "washer")
    assert notify["phone"][0].data["data"]["push"] == {"sound": "reminder.wav"}


async def test_sound_combines_with_time_sensitive(hass, notify, make_entry):
    await make_entry(type_data("alarm", time_critical=True), notification_sound="reminder.wav")
    await _start(hass, "alarm")
    assert notify["phone"][0].data["data"]["push"] == {
        "interruption-level": "time-sensitive",
        "sound": "reminder.wav",
    }


async def test_critical_alert_uses_the_sound(hass, freezer, notify, make_entry):
    await make_entry(type_data("washer"), notification_sound="reminder.wav")
    await _start(hass, "washer")
    for _ in range(3):
        await advance(hass, freezer, minutes=5)
    sound = sent(notify["phone"])[-1].data["data"]["push"]["sound"]
    assert sound == {"name": "reminder.wav", "critical": 1, "volume": 1.0}


async def test_task_type_sound_overrides_the_hub_sound(hass, notify, make_entry):
    await make_entry(
        type_data("washer", sound="washer.wav"),
        type_data("dryer"),
        notification_sound="reminder.wav",
    )
    await _start(hass, "washer")
    await _start(hass, "dryer")
    sounds = {c.data["message"]: c.data["data"]["push"]["sound"] for c in notify["phone"]}
    assert sounds == {"Washer is due": "washer.wav", "Dryer is due": "reminder.wav"}


async def test_blank_sound_means_default(hass, notify, make_entry):
    await make_entry(type_data("washer", sound="  "), notification_sound="  ")
    await _start(hass, "washer")
    assert "push" not in notify["phone"][0].data["data"]


async def test_sound_choices_are_valid_and_unique():
    from custom_components.task_reminder.const import SOUND_CHOICES

    values = [v for v, _ in SOUND_CHOICES]
    assert len(values) == len(set(values))
    assert values[0] == "default"
    # The Companion app needs the full file name including the extension (or "default").
    assert all(v == "default" or v.endswith((".caf", ".wav")) for v in values)
    assert all(label.strip() for _, label in SOUND_CHOICES)


async def test_hub_flow_accepts_a_chosen_and_a_typed_sound(hass):
    from homeassistant.data_entry_flow import FlowResultType

    for sound in ("alarm.caf", "my-own-sound.wav"):
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
                "notification_sound": sound,
            },
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"]["notification_sound"] == sound
        await hass.config_entries.async_remove(result["result"].entry_id)


async def test_task_type_flow_accepts_a_sound(hass, notify, make_entry):
    from homeassistant.data_entry_flow import FlowResultType

    from custom_components.task_reminder.const import SUBENTRY_TYPE

    entry = await make_entry()
    flow = hass.config_entries.subentries
    result = await flow.async_init((entry.entry_id, SUBENTRY_TYPE), context={"source": "user"})
    result = await flow.async_configure(
        result["flow_id"],
        {
            "name": "Washer",
            "snooze_minutes": "10, 5",
            "repeat_minutes": 5,
            "keeps_going_minutes": 2,
            "sound": "Bloom.caf",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    await hass.services.async_call(DOMAIN, "start", {"type": "washer"}, blocking=True)
    assert notify["phone"][0].data["data"]["push"] == {"sound": "Bloom.caf"}


async def test_default_sound_value_reaches_the_payload(hass, notify, make_entry):
    await make_entry(type_data("washer"), notification_sound="default")
    await _start(hass, "washer")
    assert notify["phone"][0].data["data"]["push"] == {"sound": "default"}
