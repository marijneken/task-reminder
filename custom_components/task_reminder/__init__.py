"""Task Reminder: reminders that keep going until the task is actually done."""

from __future__ import annotations

from datetime import timedelta

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.typing import ConfigType

from .const import ADHOC_KEY, DOMAIN, SILENCE_MODES
from .manager import TaskManager
from .panel import async_setup_panel

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS = [Platform.BUTTON, Platform.SELECT, Platform.DATETIME, Platform.SENSOR]

type TaskReminderConfigEntry = ConfigEntry[TaskManager]

TARGET = {
    vol.Optional("task_id"): cv.string,
    vol.Optional("type"): cv.string,
}
SERVICE_START = "start"
SERVICE_REMIND = "remind"
SERVICE_DONE = "done"
SERVICE_SNOOZE = "snooze"
SERVICE_DISMISS = "dismiss"
SERVICE_SILENCE = "silence"


def _manager(hass: HomeAssistant) -> TaskManager:
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise ServiceValidationError("Task Reminder is not set up")
    return entries[0].runtime_data


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the actions once; they work whenever the entry is loaded."""
    await async_setup_panel(hass)

    async def start(call: ServiceCall) -> ServiceResponse:
        task = await _manager(hass).async_start_task(
            call.data["type"],
            title=call.data.get("title"),
            message=call.data.get("message"),
            due_in=call.data.get("due_in"),
            due_at=call.data.get("due_at"),
        )
        return {"task_id": task.id}

    async def remind(call: ServiceCall) -> ServiceResponse:
        overrides = {k: call.data[k] for k in ("time_critical", "dismissable") if k in call.data}
        task = await _manager(hass).async_start_task(
            ADHOC_KEY,
            title=call.data["title"],
            message=call.data.get("message"),
            due_in=call.data.get("due_in"),
            due_at=call.data.get("due_at"),
            overrides=overrides or None,
        )
        return {"task_id": task.id}

    async def done(call: ServiceCall) -> None:
        await _manager(hass).async_done(call.data.get("task_id"), call.data.get("type"))

    async def snooze(call: ServiceCall) -> None:
        await _manager(hass).async_snooze(call.data.get("task_id"), call.data.get("type"))

    async def dismiss(call: ServiceCall) -> None:
        await _manager(hass).async_dismiss(call.data.get("task_id"), call.data.get("type"))

    async def silence(call: ServiceCall) -> None:
        await _manager(hass).async_set_silence(call.data["mode"], call.data.get("until"))

    hass.services.async_register(
        DOMAIN,
        SERVICE_START,
        start,
        schema=vol.Schema(
            {
                vol.Required("type"): cv.string,
                vol.Optional("title"): cv.string,
                vol.Optional("message"): cv.string,
                vol.Optional("due_in"): vol.All(cv.time_period, vol.Range(min=timedelta(0))),
                vol.Optional("due_at"): cv.datetime,
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REMIND,
        remind,
        schema=vol.Schema(
            {
                vol.Required("title"): cv.string,
                vol.Optional("message"): cv.string,
                vol.Exclusive("due_in", "due"): vol.All(
                    cv.time_period, vol.Range(min=timedelta(0))
                ),
                vol.Exclusive("due_at", "due"): cv.datetime,
                vol.Optional("time_critical"): cv.boolean,
                vol.Optional("dismissable"): cv.boolean,
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )
    for name, handler in (
        (SERVICE_DONE, done),
        (SERVICE_SNOOZE, snooze),
        (SERVICE_DISMISS, dismiss),
    ):
        hass.services.async_register(DOMAIN, name, handler, schema=vol.Schema(TARGET))
    hass.services.async_register(
        DOMAIN,
        SERVICE_SILENCE,
        silence,
        schema=vol.Schema(
            {
                vol.Required("mode"): vol.In(SILENCE_MODES),
                vol.Optional("until"): cv.datetime,
            }
        ),
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: TaskReminderConfigEntry) -> bool:
    """Set up the hub: load saved tasks, wait for HA to start, then run."""
    manager = TaskManager(hass, entry)
    await manager.async_load()
    entry.runtime_data = manager
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_reload))
    entry.async_on_unload(manager.async_unload)
    entry.async_on_unload(async_at_started(hass, manager.async_start))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TaskReminderConfigEntry) -> bool:
    """Unload; running tasks stay in storage."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _reload(hass: HomeAssistant, entry: TaskReminderConfigEntry) -> None:
    """Settings or task types changed."""
    await hass.config_entries.async_reload(entry.entry_id)
