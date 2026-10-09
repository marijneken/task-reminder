"""Silencing mode."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TaskReminderConfigEntry
from .const import SILENCE_MODES
from .entity import TaskReminderEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TaskReminderConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the silencing select."""
    async_add_entities([SilenceSelect(entry.runtime_data)])


class SilenceSelect(TaskReminderEntity, SelectEntity):
    """off / no critical alerts / silent. Anything but off needs an end time:
    set the end time entity first (or use the silence action)."""

    _attr_translation_key = "silence_mode"
    _attr_options = SILENCE_MODES

    def __init__(self, manager) -> None:
        super().__init__(manager, "silence_mode")

    @property
    def current_option(self) -> str:
        """Current mode."""
        return self.manager.silence.mode

    async def async_select_option(self, option: str) -> None:
        """Change mode; raises when no end time is available."""
        await self.manager.async_set_silence(option, None)
