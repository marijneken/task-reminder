"""Fixtures."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.task_reminder.const import DOMAIN, SUBENTRY_ROOM, SUBENTRY_TYPE

START = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow loading the custom integration."""


@pytest.fixture(autouse=True)
async def utc_and_start(hass: HomeAssistant, freezer) -> None:
    """Midday UTC so quiet hours (23-07) are out of the way unless a test moves time."""
    await hass.config.async_set_time_zone("UTC")
    freezer.move_to(START)


def type_data(key: str, **overrides: Any) -> ConfigSubentryData:
    data = {
        "key": key,
        "name": key.title(),
        "snooze_minutes": "10, 5, 3",
        "repeat_minutes": 5,
        "keeps_going_minutes": 2,
        **overrides,
    }
    return ConfigSubentryData(
        data=data, subentry_type=SUBENTRY_TYPE, title=data["name"], unique_id=key
    )


def sent(calls):
    """The reminders in a list of notify calls, without the clear_notification commands that
    remove an older notification when a new one is sent."""
    return [c for c in calls if c.data.get("message") != "clear_notification"]


def on_screen(calls):
    """Tags of the notifications that are on the phone: sent and not (yet) cleared."""
    shown: list[str] = []
    for c in calls:
        tag = c.data["data"]["tag"]
        if c.data["message"] == "clear_notification":
            if tag in shown:
                shown.remove(tag)
        elif tag not in shown:
            shown.append(tag)
    return shown


def room_data(key: str, presence: list[str] | None = None, alexa: str | None = None):
    data = {"key": key, "name": key.title(), "presence_entities": presence or []}
    if alexa:
        data["alexa_service"] = alexa
    return ConfigSubentryData(
        data=data, subentry_type=SUBENTRY_ROOM, title=data["name"], unique_id=f"room_{key}"
    )


@pytest.fixture
def notify(hass: HomeAssistant) -> dict[str, list]:
    """Mock the notify services the hub points at."""
    return {
        "phone": async_mock_service(hass, "notify", "mobile_app_phone"),
        "alexa": async_mock_service(hass, "notify", "alexa_media_echo"),
        "extra": async_mock_service(hass, "notify", "mobile_app_ipad"),
    }


@pytest.fixture
def make_entry(hass: HomeAssistant, notify):
    """Create and set up the hub with the given task types."""

    async def _make(*types: ConfigSubentryData, **settings: Any) -> MockConfigEntry:
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Task Reminder",
            data={
                "person": "person.marijn",
                "phone_services": ["mobile_app_phone"],
                "alexa_services": ["alexa_media_echo"],
                "extra_services": ["mobile_app_ipad"],
                "quiet_start": "23:00:00",
                "quiet_end": "07:00:00",
                **settings,
            },
            subentries_data=list(types),
        )
        entry.add_to_hass(hass)
        hass.states.async_set("person.marijn", "home")
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        return entry

    return _make


async def advance(hass: HomeAssistant, freezer, **delta: float) -> None:
    """Move the clock and let due timers fire."""
    freezer.tick(timedelta(**delta))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
