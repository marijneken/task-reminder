"""Config flow, subentry flow and entities."""

from datetime import UTC, datetime

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError

from custom_components.task_reminder.const import DOMAIN, SUBENTRY_TYPE

from .conftest import advance, hub_form, type_data

HUB = {
    "person": "person.marijn",
    "phone_services": ["mobile_app_phone"],
    "alexa_speakers": [],
    "extra_services": [],
    "quiet_start": "23:00:00",
    "quiet_end": "07:00:00",
}


async def test_hub_flow_and_single_instance(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], hub_form(**HUB))
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["phone_services"] == ["mobile_app_phone"]

    again = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert again["type"] is FlowResultType.ABORT
    assert again["reason"] == "single_instance_allowed"


async def test_options_flow_changes_settings(hass: HomeAssistant, make_entry) -> None:
    entry = await make_entry()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], hub_form(**{**HUB, "quiet_start": "22:00:00"})
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.runtime_data.settings["quiet_start"] == "22:00:00"


async def _add_type(hass, entry, **overrides):
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE), context={"source": "user"}
    )
    assert result["type"] is FlowResultType.FORM
    return await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "name": "Dishwasher",
            "snooze_minutes": "10, 5",
            "repeat_minutes": 5,
            "keeps_going_minutes": 2,
            **overrides,
        },
    )


async def test_add_task_type_and_use_it(hass: HomeAssistant, make_entry) -> None:
    entry = await make_entry()
    result = await _add_type(hass, entry, duration_minutes=45)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()  # entry reloads with the new type

    (subentry,) = entry.subentries.values()
    assert subentry.unique_id == "dishwasher" and subentry.data["key"] == "dishwasher"
    assert "dishwasher" in entry.runtime_data.types
    assert entry.runtime_data.types["dishwasher"].snooze_minutes == (10, 5)
    await hass.services.async_call(DOMAIN, "start", {"type": "dishwasher"}, blocking=True)


async def test_task_type_validation(hass: HomeAssistant, make_entry) -> None:
    entry = await make_entry(type_data("dishwasher", name="Dishwasher"))
    result = await _add_type(
        hass, entry, name="Dryer", snooze_minutes="ten", duration_minutes=5, due_time="08:00:00"
    )
    assert result["errors"] == {
        "snooze_minutes": "invalid_minutes",
        "due_time": "duration_and_time",
    }
    # Same name again is refused.
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "name": "dishwasher",
            "snooze_minutes": "5",
            "repeat_minutes": 5,
            "keeps_going_minutes": 2,
        },
    )
    assert result["errors"] == {"name": "already_exists"}


async def test_reconfigure_keeps_key(hass: HomeAssistant, make_entry) -> None:
    entry = await make_entry(type_data("dishwasher", name="Dishwasher"))
    (subentry,) = entry.subentries.values()
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE),
        context={"source": "reconfigure", "subentry_id": subentry.subentry_id},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "name": "Dish washer",
            "snooze_minutes": "6, 3",
            "repeat_minutes": 5,
            "keeps_going_minutes": 2,
        },
    )
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert "dishwasher" in entry.runtime_data.types
    assert entry.runtime_data.types["dishwasher"].name == "Dish washer"


async def test_entities(hass: HomeAssistant, freezer, make_entry) -> None:
    await make_entry(type_data("washer"))
    ids = {
        "select": "select.task_reminder_silencing",
        "until": "datetime.task_reminder_silencing_until",
        "count": "sensor.task_reminder_active_tasks",
    }
    assert hass.states.get(ids["select"]).state == "off"
    assert hass.states.get(ids["count"]).state == "0"

    await hass.services.async_call(DOMAIN, "start", {"type": "washer"}, blocking=True)
    state = hass.states.get(ids["count"])
    assert state.state == "1" and state.attributes["tasks"][0]["type"] == "washer"

    # Choosing a mode without an end time is refused.
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": ids["select"], "option": "silent"},
            blocking=True,
        )
    # Set the end time first, then the mode.
    until = datetime(2026, 10, 9, 18, 0, tzinfo=UTC)
    await hass.services.async_call(
        "datetime",
        "set_value",
        {"entity_id": ids["until"], "datetime": until.isoformat()},
        blocking=True,
    )
    await hass.services.async_call(
        "select", "select_option", {"entity_id": ids["select"], "option": "silent"}, blocking=True
    )
    assert hass.states.get(ids["select"]).state == "silent"
    assert hass.states.get(ids["until"]).state == "2026-10-09T18:00:00+00:00"

    # Silence expires on its own.
    await advance(hass, freezer, hours=7)
    assert hass.states.get(ids["select"]).state == "off"


async def test_the_hub_form_is_grouped_in_sections(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    schema = result["data_schema"].schema
    assert [str(key) for key in schema] == [
        "person",
        "notifications",
        "sound_ringing",
        "actions",
        "quiet_hours",
    ]
    inner = {
        name: [str(k) for k in schema[name].schema.schema]
        for name in ("notifications", "sound_ringing", "actions", "quiet_hours")
    }
    assert inner["notifications"] == [
        "live_activities",
        "phone_services",
        "extra_services",
        "tv_services",
        "alexa_speakers",
        "room_provider",
    ]
    assert inner["sound_ringing"] == [
        "notification_sound",
        "ring_seconds",
        "ring_swap_seconds",
        "ring_minutes",
    ]
    assert inner["actions"] == ["pause_players", "turn_off_players"]
    assert inner["quiet_hours"] == ["quiet_start", "quiet_end"]


async def test_the_options_form_shows_the_stored_values(hass: HomeAssistant, make_entry) -> None:
    entry = await make_entry(room_provider="sensor.room", ring_seconds=20)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    schema = result["data_schema"].schema

    def suggested(section_name: str) -> dict:
        inner = next(v for k, v in schema.items() if str(k) == section_name).schema.schema
        return {str(k): k.description for k in inner}

    assert suggested("notifications")["room_provider"] == {"suggested_value": "sensor.room"}
    assert suggested("sound_ringing")["ring_seconds"] == {"suggested_value": 20}


async def test_clearing_a_setting_in_the_options_really_clears_it(hass, make_entry) -> None:
    entry = await make_entry(room_provider="sensor.room", notification_sound="alarm.caf")
    assert entry.runtime_data.settings["room_provider"] == "sensor.room"
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        hub_form(**HUB),  # room provider and sound left empty
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert not entry.runtime_data.settings.get("room_provider")
    assert not entry.runtime_data.settings.get("notification_sound")


async def test_the_hub_form_can_be_sent_to_the_frontend(hass: HomeAssistant) -> None:
    import voluptuous_serialize
    from homeassistant.helpers import config_validation as cv

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    fields = voluptuous_serialize.convert(
        result["data_schema"], custom_serializer=cv.custom_serializer
    )
    sections = {f["name"]: f for f in fields if f.get("type") == "expandable"}
    assert set(sections) == {"notifications", "sound_ringing", "actions", "quiet_hours"}
    assert [f["name"] for f in sections["sound_ringing"]["schema"]][:3] == [
        "notification_sound",
        "ring_seconds",
        "ring_swap_seconds",
    ]
