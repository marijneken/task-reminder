"""What the notifications look like."""

from custom_components.task_reminder.const import DOMAIN

from .conftest import advance, sent, type_data


async def _start(hass, type_):
    await hass.services.async_call(DOMAIN, "start", {"type": type_}, blocking=True)


async def test_title_is_fixed_and_body_says_what_is_due(hass, freezer, notify, make_entry):
    await make_entry(type_data("washer"))
    await _start(hass, "washer")
    first = notify["phone"][0].data
    assert first["title"] == "Task Reminder"
    assert first["message"] == "Washer is due"

    await advance(hass, freezer, minutes=5)
    again = sent(notify["phone"])[-1].data
    assert again["title"] == "Task Reminder"
    assert again["message"] == "Washer is still waiting"
    assert notify["alexa"][0].data["message"] == "Washer is still waiting"  # spoken: no title


async def test_custom_message_replaces_the_body(hass, notify, make_entry):
    await make_entry(type_data("washer"))
    await hass.services.async_call(
        DOMAIN, "start", {"type": "washer", "message": "Clothes are done"}, blocking=True
    )
    assert notify["phone"][0].data["message"] == "Clothes are done"


async def test_away_notification_and_summary_use_the_same_title(hass, freezer, notify, make_entry):
    await make_entry(type_data("washer"))
    hass.states.async_set("person.marijn", "not_home")
    await _start(hass, "washer")
    assert notify["phone"][0].data["title"] == "Task Reminder"
    assert notify["phone"][0].data["message"] == "Washer is due (you're away)"


async def test_tap_target_is_only_set_when_configured(hass, notify, make_entry):
    await make_entry(type_data("washer"), tap_url="/lovelace/reminders")
    await _start(hass, "washer")
    data = notify["phone"][0].data["data"]
    assert data["url"] == "/lovelace/reminders"  # iOS
    assert data["clickAction"] == "/lovelace/reminders"  # Android


async def test_no_tap_target_by_default(hass, notify, make_entry):
    await make_entry(type_data("washer"))
    await _start(hass, "washer")
    data = notify["phone"][0].data["data"]
    assert "url" not in data and "clickAction" not in data
