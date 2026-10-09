"""Custom notification sound."""

from custom_components.task_reminder.const import DOMAIN

from .conftest import advance, type_data


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
    sound = notify["phone"][-1].data["data"]["push"]["sound"]
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
