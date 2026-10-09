"""End time for silencing."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TaskReminderConfigEntry
from .entity import TaskReminderEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TaskReminderConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the end time entity."""
    async_add_entities([SilenceUntil(entry.runtime_data)])


class SilenceUntil(TaskReminderEntity, DateTimeEntity):
    """Shows the end of the running silence, or the one prepared for the next."""

    _attr_translation_key = "silence_until"

    def __init__(self, manager) -> None:
        super().__init__(manager, "silence_until")

    @property
    def native_value(self) -> datetime | None:
        """Running silence end, else the prepared one."""
        return self.manager.silence.until or self.manager.pending_until

    async def async_set_value(self, value: datetime) -> None:
        """Set the end time."""
        await self.manager.async_set_pending_until(value)
