"""A TV shows a plain toast from the third reminder on (the other-devices tier)."""

import logging

from homeassistant.core import ServiceCall
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.task_reminder.const import DOMAIN

from .conftest import advance, sent, type_data


async def test_toast_comes_with_the_other_devices(hass, freezer, notify, make_entry):
    toasts = async_mock_service(hass, "notify", "lg_tv")
    await make_entry(type_data("washer"), tv_services=["lg_tv"])
    await hass.services.async_call(DOMAIN, "start", {"type": "washer"}, blocking=True)
    await advance(hass, freezer, minutes=5)  # 2nd reminder: phone and Alexa
    assert toasts == []
    await advance(hass, freezer, minutes=5)  # 3rd: other devices
    (toast,) = toasts
    assert toast.data == {"message": "Washer is still waiting"}  # text only
    assert len(sent(notify["extra"])) == 1  # the iPad still gets its normal notification


async def test_a_tv_that_is_off_does_not_break_anything(hass, freezer, notify, make_entry, caplog):
    def _off(call: ServiceCall) -> None:
        raise RuntimeError("TV is off")

    hass.services.async_register("notify", "lg_tv", _off)
    await make_entry(type_data("washer"), tv_services=["lg_tv"])
    await hass.services.async_call(DOMAIN, "start", {"type": "washer"}, blocking=True)
    with caplog.at_level(logging.WARNING):
        for _ in range(2):
            await advance(hass, freezer, minutes=5)
    assert len(sent(notify["extra"])) == 1
    assert "lg_tv" not in caplog.text  # no warning for a TV that is off


async def test_the_toast_repeats_with_the_ring(hass, freezer, notify, make_entry):
    toasts = async_mock_service(hass, "notify", "lg_tv")
    await make_entry(type_data("alarm", ring=True), tv_services=["lg_tv"])
    await hass.services.async_call(DOMAIN, "start", {"type": "alarm"}, blocking=True)
    for _ in range(2):
        await advance(hass, freezer, minutes=5)  # 3rd reminder: the TV joins
    assert len(toasts) == 1
    await advance(hass, freezer, seconds=12)  # the phone rings again, and so does the TV
    assert len(toasts) == 2
    await advance(hass, freezer, seconds=12)
    assert len(toasts) == 3
    assert {t.data["message"] for t in toasts} == {"Alarm is still waiting"}


async def test_no_repeat_before_the_tv_tier(hass, freezer, notify, make_entry):
    toasts = async_mock_service(hass, "notify", "lg_tv")
    await make_entry(type_data("alarm", ring=True), tv_services=["lg_tv"])
    await hass.services.async_call(DOMAIN, "start", {"type": "alarm"}, blocking=True)
    await advance(hass, freezer, seconds=12)  # phone-only reminder rings
    assert toasts == []


async def test_a_tv_listed_twice_only_gets_the_toast(hass, freezer, notify, make_entry):
    """Under 'other devices' it used to show the word clear_notification."""
    tv = async_mock_service(hass, "notify", "lg_tv")
    await make_entry(type_data("washer"), extra_services=["lg_tv"], tv_services=["lg_tv"])
    await hass.services.async_call(DOMAIN, "start", {"type": "washer"}, blocking=True)
    for _ in range(4):
        await advance(hass, freezer, minutes=5)
    assert tv and all(set(c.data) == {"message"} for c in tv)
    assert all(c.data["message"] != "clear_notification" for c in tv)
