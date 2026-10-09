"""Buttons: start a test reminder right now."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TaskReminderConfigEntry
from .const import ADHOC_KEY
from .entity import TaskReminderEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TaskReminderConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the test button."""
    async_add_entities([TestReminderButton(entry.runtime_data)])


class TestReminderButton(TaskReminderEntity, ButtonEntity):
    """Starts a reminder that is due immediately: the quickest check that
    notifications, actions (Done / Snooze / Dismiss) and escalation work."""

    __test__ = False  # not a pytest class
    _attr_translation_key = "test_reminder"

    def __init__(self, manager) -> None:
        super().__init__(manager, "test_reminder")

    async def async_press(self) -> None:
        """Start the test reminder."""
        await self.manager.async_start_task(
            ADHOC_KEY, title="Test reminder", message="This is a test reminder"
        )
