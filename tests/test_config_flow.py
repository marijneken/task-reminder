"""Config flow, subentry flow and entities."""

from datetime import UTC, datetime

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError

from custom_components.task_reminder.const import DOMAIN, SUBENTRY_TYPE

from .conftest import advance, type_data

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
    result = await hass.config_entries.flow.async_configure(result["flow_id"], HUB)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["phone_services"] == ["mobile_app_phone"]

    again = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert again["type"] is FlowResultType.ABORT
    assert again["reason"] == "single_instance_allowed"


async def test_options_flow_changes_settings(hass: HomeAssistant, make_entry) -> None:
    entry = await make_entry()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**HUB, "quiet_start": "22:00:00"}
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
