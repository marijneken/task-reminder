"""Active tasks overview."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TaskReminderConfigEntry
from .entity import TaskReminderEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TaskReminderConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the active tasks sensor."""
    async_add_entities([ActiveTasksSensor(entry.runtime_data)])


class ActiveTasksSensor(TaskReminderEntity, SensorEntity):
    """Number of running tasks, with the details as attributes."""

    _attr_translation_key = "active_tasks"

    def __init__(self, manager) -> None:
        super().__init__(manager, "active_tasks")

    @property
    def native_value(self) -> int:
        """Count of running tasks."""
        return len(self.manager.tasks)

    @property
    def extra_state_attributes(self) -> dict:
        """Details per task."""
        return {"tasks": [t.as_attributes() for t in self.manager.tasks.values()]}
