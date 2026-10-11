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
