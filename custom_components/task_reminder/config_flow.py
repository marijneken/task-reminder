"""Config flow: the hub (settings) and one subentry per task type."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
from homeassistant.util import slugify

from .const import (
    ADHOC_KEY,
    CONF_ALEXA_SERVICES,
    CONF_DISMISSABLE,
    CONF_DONE_ENTITY,
    CONF_DONE_STATE,
    CONF_DONE_TAG,
    CONF_DONE_THEN_ENTITY,
    CONF_DONE_THEN_STATE,
    CONF_DONE_WINDOW_MINUTES,
    CONF_DUE_ENTITY,
    CONF_DUE_STATE,
    CONF_DUE_TIME,
    CONF_DURATION_MINUTES,
    CONF_EXTRA_SERVICES,
    CONF_FLAG_ENTITY,
    CONF_GOOD_MOMENT_ENTITIES,
    CONF_KEEPS_GOING_MINUTES,
    CONF_KEY,
    CONF_NAME,
    CONF_PAUSE_PLAYERS,
    CONF_PERSON,
    CONF_PHONE_SERVICES,
    CONF_QUIET_END,
    CONF_QUIET_START,
    CONF_QUIET_WITHOUT_FLAG,
    CONF_REPEAT_MINUTES,
    CONF_SCHEDULE_ENTITY,
    CONF_SINGLE_INSTANCE,
    CONF_SNOOZE_MINUTES,
    CONF_START_DAYS_BEFORE,
    CONF_START_ENTITY,
    CONF_START_STATE,
    CONF_START_TAG,
    CONF_TAP_URL,
    CONF_THEN_START,
    CONF_TIME_CRITICAL,
    DEFAULT_DONE_WINDOW_MINUTES,
    DEFAULT_KEEPS_GOING_MINUTES,
    DEFAULT_QUIET_END,
    DEFAULT_QUIET_START,
    DEFAULT_REPEAT_MINUTES,
    DEFAULT_SNOOZE_MINUTES,
    DEFAULT_START_DAYS_BEFORE,
    DEFAULT_TRIGGER_STATE,
    DOMAIN,
    SUBENTRY_TYPE,
)
from .policy import parse_minutes


def _notify_selector(hass: HomeAssistant) -> selector.SelectSelector:
    services = sorted(hass.services.async_services_for_domain("notify"))
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=services,
            multiple=True,
            custom_value=True,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _hub_schema(hass: HomeAssistant) -> vol.Schema:
    notify = _notify_selector(hass)
    return vol.Schema(
        {
            vol.Required(CONF_PERSON): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="person")
            ),
            vol.Optional(CONF_PHONE_SERVICES, default=[]): notify,
            vol.Optional(CONF_ALEXA_SERVICES, default=[]): notify,
            vol.Optional(CONF_EXTRA_SERVICES, default=[]): notify,
            vol.Optional(CONF_PAUSE_PLAYERS, default=[]): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="media_player", multiple=True)
            ),
            vol.Optional(CONF_TAP_URL): selector.TextSelector(),
            vol.Required(CONF_QUIET_START, default=DEFAULT_QUIET_START): selector.TimeSelector(),
            vol.Required(CONF_QUIET_END, default=DEFAULT_QUIET_END): selector.TimeSelector(),
        }
    )


class TaskReminderConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up the hub; task types are added as subentries afterwards."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Hub settings."""
        if user_input is not None:
            return self.async_create_entry(title="Task Reminder", data=user_input)
        return self.async_show_form(step_id="user", data_schema=_hub_schema(self.hass))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Hub settings can be changed later."""
        return TaskReminderOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """One subentry per task type."""
        return {SUBENTRY_TYPE: TaskTypeSubentryFlow}


class TaskReminderOptionsFlow(OptionsFlow):
    """Edit hub settings."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Hub settings."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(_hub_schema(self.hass), current),
        )


def _type_schema(other_types: dict[str, str]) -> vol.Schema:
    entity = selector.EntitySelector()
    tag = selector.EntitySelector(selector.EntitySelectorConfig(domain="tag"))
    text = selector.TextSelector()

    def minutes(lo: int, hi: int, unit: str = "min") -> selector.NumberSelector:
        return selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=lo,
                max=hi,
                step=1,
                mode=selector.NumberSelectorMode.BOX,
                unit_of_measurement=unit,
            )
        )

    fields: dict[Any, Any] = {
        vol.Required(CONF_NAME): text,
        vol.Optional(CONF_DISMISSABLE, default=False): selector.BooleanSelector(),
        vol.Optional(CONF_TIME_CRITICAL, default=False): selector.BooleanSelector(),
        vol.Optional(CONF_SINGLE_INSTANCE, default=True): selector.BooleanSelector(),
        vol.Optional(CONF_DURATION_MINUTES): minutes(1, 10080),
        vol.Optional(CONF_DUE_TIME): selector.TimeSelector(),
        vol.Required(CONF_SNOOZE_MINUTES, default=DEFAULT_SNOOZE_MINUTES): text,
        vol.Required(CONF_REPEAT_MINUTES, default=DEFAULT_REPEAT_MINUTES): minutes(1, 240),
        vol.Required(CONF_KEEPS_GOING_MINUTES, default=DEFAULT_KEEPS_GOING_MINUTES): minutes(
            1, 240
        ),
        vol.Optional(CONF_SCHEDULE_ENTITY): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ),
        vol.Optional(CONF_START_DAYS_BEFORE, default=DEFAULT_START_DAYS_BEFORE): minutes(
            0, 14, "d"
        ),
        vol.Optional(CONF_START_ENTITY): entity,
        vol.Optional(CONF_START_TAG): tag,
        vol.Optional(CONF_DONE_TAG): tag,
        vol.Optional(CONF_GOOD_MOMENT_ENTITIES): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="binary_sensor", multiple=True)
        ),
        vol.Optional(CONF_START_STATE, default=DEFAULT_TRIGGER_STATE): text,
        vol.Optional(CONF_DUE_ENTITY): entity,
        vol.Optional(CONF_DUE_STATE, default=DEFAULT_TRIGGER_STATE): text,
        vol.Optional(CONF_DONE_ENTITY): entity,
        vol.Optional(CONF_DONE_STATE, default=DEFAULT_TRIGGER_STATE): text,
        vol.Optional(CONF_DONE_THEN_ENTITY): entity,
        vol.Optional(CONF_DONE_THEN_STATE, default=DEFAULT_TRIGGER_STATE): text,
        vol.Optional(CONF_DONE_WINDOW_MINUTES, default=DEFAULT_DONE_WINDOW_MINUTES): minutes(
            1, 120
        ),
        vol.Optional(CONF_FLAG_ENTITY): entity,
        vol.Optional(CONF_QUIET_WITHOUT_FLAG, default=False): selector.BooleanSelector(),
    }
    if other_types:
        fields[vol.Optional(CONF_THEN_START)] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    selector.SelectOptionDict(value=k, label=n) for k, n in other_types.items()
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )
    return vol.Schema(fields)


class TaskTypeSubentryFlow(ConfigSubentryFlow):
    """Add or edit a task type."""

    def _others(self, exclude: str | None = None) -> dict[str, str]:
        entry = self._get_entry()
        return {
            s.data[CONF_KEY]: s.title
            for s in entry.subentries.values()
            if s.data.get(CONF_KEY) and s.data[CONF_KEY] != exclude
        }

    def _validate(self, user_input: dict[str, Any]) -> dict[str, str]:
        errors: dict[str, str] = {}
        try:
            parse_minutes(user_input[CONF_SNOOZE_MINUTES])
        except ValueError:
            errors[CONF_SNOOZE_MINUTES] = "invalid_minutes"
        if user_input.get(CONF_DURATION_MINUTES) and user_input.get(CONF_DUE_TIME):
            errors[CONF_DUE_TIME] = "duration_and_time"
        return errors

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """New task type."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = self._validate(user_input)
            key = slugify(user_input[CONF_NAME])
            if not key:
                errors[CONF_NAME] = "invalid_name"
            elif key == ADHOC_KEY:
                errors[CONF_NAME] = "reserved_name"
            elif key in self._others():
                errors[CONF_NAME] = "already_exists"
            if not errors:
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data={**user_input, CONF_KEY: key},
                    unique_id=key,
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                _type_schema(self._others()), user_input
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Edit a task type; its key stays stable so running tasks keep working."""
        subentry = self._get_reconfigure_subentry()
        key = subentry.data[CONF_KEY]
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = self._validate(user_input)
            if not errors:
                return self.async_update_and_abort(
                    self._get_entry(),
                    subentry,
                    title=user_input[CONF_NAME],
                    data={**user_input, CONF_KEY: key},
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                _type_schema(self._others(exclude=key)), user_input or dict(subentry.data)
            ),
            errors=errors,
        )
