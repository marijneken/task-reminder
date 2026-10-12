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
from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector
from homeassistant.util import slugify

from .const import (
    ADHOC_KEY,
    CONF_ALEXA_SPEAKERS,
    CONF_COLLECTION_END_TIME,
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
    CONF_LIVE_ACTIVITIES,
    CONF_NAME,
    CONF_NOTIFICATION_SOUND,
    CONF_PAUSE_PLAYERS,
    CONF_PERSON,
    CONF_PHONE_SERVICES,
    CONF_QUIET_END,
    CONF_QUIET_START,
    CONF_QUIET_WITHOUT_FLAG,
    CONF_REPEAT_MINUTES,
    CONF_RING,
    CONF_RING_MINUTES,
    CONF_RING_SECONDS,
    CONF_RING_SWAP_SECONDS,
    CONF_ROOM_PROVIDER,
    CONF_SCHEDULE_ENTITY,
    CONF_SINGLE_INSTANCE,
    CONF_SNOOZE_MINUTES,
    CONF_SOUND,
    CONF_START_DAYS_BEFORE,
    CONF_START_ENTITY,
    CONF_START_STATE,
    CONF_START_TAG,
    CONF_THEN_START,
    CONF_TIME_CRITICAL,
    CONF_TURN_OFF_PLAYERS,
    CONF_TV_SERVICES,
    DEFAULT_DONE_WINDOW_MINUTES,
    DEFAULT_KEEPS_GOING_MINUTES,
    DEFAULT_QUIET_END,
    DEFAULT_QUIET_START,
    DEFAULT_REPEAT_MINUTES,
    DEFAULT_RING_MINUTES,
    DEFAULT_RING_SECONDS,
    DEFAULT_RING_SWAP_SECONDS,
    DEFAULT_SNOOZE_MINUTES,
    DEFAULT_START_DAYS_BEFORE,
    DEFAULT_TRIGGER_STATE,
    DOMAIN,
    SOUND_CHOICES,
    SUBENTRY_TYPE,
)
from .policy import parse_minutes


def _number(lo: float, hi: float, unit: str, step: float = 1) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=lo,
            max=hi,
            step=step,
            mode=selector.NumberSelectorMode.BOX,
            unit_of_measurement=unit,
        )
    )


def _sound_selector() -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                selector.SelectOptionDict(value=value, label=label)
                for value, label in SOUND_CHOICES
            ],
            custom_value=True,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


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


# The hub form groups its fields in sections; what is stored stays one flat dict.
_SECTION_FIELDS: dict[str, tuple[str, ...]] = {
    "notifications": (
        CONF_PHONE_SERVICES,
        CONF_EXTRA_SERVICES,
        CONF_TV_SERVICES,
        CONF_ALEXA_SPEAKERS,
    ),
    "sound_ringing": (
        CONF_NOTIFICATION_SOUND,
        CONF_RING_SECONDS,
        CONF_RING_SWAP_SECONDS,
        CONF_RING_MINUTES,
    ),
    "quiet_hours": (CONF_QUIET_START, CONF_QUIET_END),
}
_HUB_KEYS = (
    CONF_PERSON,
    CONF_LIVE_ACTIVITIES,
    *(key for fields in _SECTION_FIELDS.values() for key in fields),
    CONF_PAUSE_PLAYERS,
    CONF_TURN_OFF_PLAYERS,
    CONF_ROOM_PROVIDER,
)


def _flatten(user_input: dict[str, Any]) -> dict[str, Any]:
    """The submitted form (with sections) as one flat dict."""
    flat: dict[str, Any] = {}
    for key, value in user_input.items():
        if key in _SECTION_FIELDS:
            flat.update(value)
        else:
            flat[key] = value
    return flat


def _nest(flat: dict[str, Any]) -> dict[str, Any]:
    """Stored settings in the shape of the form, to prefill it."""
    nested = {k: v for k, v in flat.items() if not any(k in f for f in _SECTION_FIELDS.values())}
    for name, fields in _SECTION_FIELDS.items():
        nested[name] = {k: flat[k] for k in fields if flat.get(k) is not None}
    return nested


def _hub_schema(hass: HomeAssistant) -> vol.Schema:
    notify = _notify_selector(hass)
    players = selector.EntitySelector(
        selector.EntitySelectorConfig(domain="media_player", multiple=True)
    )
    return vol.Schema(
        {
            vol.Required(CONF_PERSON): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="person")
            ),
            vol.Optional(CONF_LIVE_ACTIVITIES, default=False): selector.BooleanSelector(),
            vol.Required("notifications"): section(
                vol.Schema(
                    {
                        vol.Optional(CONF_PHONE_SERVICES, default=[]): notify,
                        vol.Optional(CONF_EXTRA_SERVICES, default=[]): notify,
                        vol.Optional(CONF_TV_SERVICES, default=[]): notify,
                        vol.Optional(CONF_ALEXA_SPEAKERS, default=[]): selector.EntitySelector(
                            selector.EntitySelectorConfig(
                                domain="media_player", integration="alexa_media", multiple=True
                            )
                        ),
                    }
                ),
                {"collapsed": False},
            ),
            vol.Required("sound_ringing"): section(
                vol.Schema(
                    {
                        vol.Optional(CONF_NOTIFICATION_SOUND): _sound_selector(),
                        vol.Optional(CONF_RING_SECONDS, default=DEFAULT_RING_SECONDS): _number(
                            5, 120, "s"
                        ),
                        vol.Optional(
                            CONF_RING_SWAP_SECONDS, default=DEFAULT_RING_SWAP_SECONDS
                        ): _number(0, 10, "s", step=0.1),
                        vol.Optional(CONF_RING_MINUTES, default=DEFAULT_RING_MINUTES): _number(
                            1, 30, "min"
                        ),
                    }
                ),
                {"collapsed": False},
            ),
            vol.Required("quiet_hours"): section(
                vol.Schema(
                    {
                        vol.Required(
                            CONF_QUIET_START, default=DEFAULT_QUIET_START
                        ): selector.TimeSelector(),
                        vol.Required(
                            CONF_QUIET_END, default=DEFAULT_QUIET_END
                        ): selector.TimeSelector(),
                    }
                ),
                {"collapsed": False},
            ),
            vol.Optional(CONF_PAUSE_PLAYERS, default=[]): players,
            vol.Optional(CONF_TURN_OFF_PLAYERS, default=[]): players,
            vol.Optional(CONF_ROOM_PROVIDER): selector.EntitySelector(),
        }
    )


class TaskReminderConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up the hub; task types are added as subentries afterwards."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Hub settings."""
        if user_input is not None:
            return self.async_create_entry(title="Task Reminder", data=_flatten(user_input))
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
            settings = _flatten(user_input)
            # A field left empty is absent from the form: say so, or the value from the first
            # setup (entry data) would shine through again.
            return self.async_create_entry(data={**dict.fromkeys(_HUB_KEYS), **settings})
        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(_hub_schema(self.hass), _nest(current)),
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
        vol.Optional(CONF_COLLECTION_END_TIME): selector.TimeSelector(),
        vol.Optional(CONF_SOUND): _sound_selector(),
        vol.Optional(CONF_RING, default=False): selector.BooleanSelector(),
        vol.Optional(CONF_RING_SECONDS): _number(5, 120, "s"),
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
            if s.subentry_type == SUBENTRY_TYPE
            and s.data.get(CONF_KEY)
            and s.data[CONF_KEY] != exclude
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
