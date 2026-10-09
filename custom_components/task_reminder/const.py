"""Constants for Task Reminder."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "task_reminder"

SUBENTRY_TYPE = "task_type"

# Built-in type behind the `remind` action and the test button. Needs no setup.
ADHOC_KEY = "ad_hoc"

# Hub settings (entry data, overridden by entry options)
CONF_PERSON = "person"
CONF_PHONE_SERVICES = "phone_services"
CONF_ALEXA_SERVICES = "alexa_services"
CONF_EXTRA_SERVICES = "extra_services"
CONF_PAUSE_PLAYERS = "pause_players"
CONF_TAP_URL = "tap_url"
CONF_NOTIFICATION_SOUND = "notification_sound"
CONF_SOUND = "sound"  # per task type, overrides the hub sound
CONF_QUIET_START = "quiet_start"
CONF_QUIET_END = "quiet_end"

DEFAULT_QUIET_START = "23:00:00"
DEFAULT_QUIET_END = "07:00:00"

# Task type settings (subentry data)
CONF_KEY = "key"
CONF_NAME = "name"
CONF_DISMISSABLE = "dismissable"
CONF_TIME_CRITICAL = "time_critical"
CONF_SINGLE_INSTANCE = "single_instance"
CONF_DURATION_MINUTES = "duration_minutes"
CONF_DUE_TIME = "due_time"
CONF_SNOOZE_MINUTES = "snooze_minutes"
CONF_REPEAT_MINUTES = "repeat_minutes"
CONF_KEEPS_GOING_MINUTES = "keeps_going_minutes"
CONF_START_ENTITY = "start_entity"
CONF_START_STATE = "start_state"
CONF_DUE_ENTITY = "due_entity"
CONF_DUE_STATE = "due_state"
CONF_DONE_ENTITY = "done_entity"
CONF_DONE_STATE = "done_state"
CONF_THEN_START = "then_start"
CONF_FLAG_ENTITY = "flag_entity"
CONF_SCHEDULE_ENTITY = "schedule_entity"
CONF_START_TAG = "start_tag"
CONF_DONE_TAG = "done_tag"
CONF_GOOD_MOMENT_ENTITIES = "good_moment_entities"
CONF_START_DAYS_BEFORE = "start_days_before"
CONF_QUIET_WITHOUT_FLAG = "quiet_without_flag"
CONF_DONE_THEN_ENTITY = "done_then_entity"
CONF_DONE_THEN_STATE = "done_then_state"
CONF_DONE_WINDOW_MINUTES = "done_window_minutes"

DEFAULT_SNOOZE_MINUTES = "10, 5, 3"
DEFAULT_REPEAT_MINUTES = 5
DEFAULT_KEEPS_GOING_MINUTES = 2
DEFAULT_TRIGGER_STATE = "on"
DEFAULT_DONE_WINDOW_MINUTES = 5
DEFAULT_START_DAYS_BEFORE = 1

# Attributes of the afvalbeheer collection sensors
ATTR_DAYS_UNTIL = "Days_until"
ATTR_SORT_DATE = "Sort_date"

# Silencing
SILENCE_OFF = "off"
SILENCE_NO_CRITICAL = "no_critical"
SILENCE_SILENT = "silent"
SILENCE_MODES = [SILENCE_OFF, SILENCE_NO_CRITICAL, SILENCE_SILENT]

# Held reasons
HOLD_SILENT = "silent"
HOLD_QUIET = "quiet"
HOLD_AWAY = "away"

# After a silent period ends with several piled-up tasks, the summary goes out
# first and the individual reminders follow after this delay.
# A good moment (e.g. motion on the stairs) only brings a reminder forward when
# the last one is at least this old, so it cannot turn into a barrage.
GOOD_MOMENT_COOLDOWN = timedelta(minutes=2)
EVENT_TAG_SCANNED = "tag_scanned"
SUMMARY_GRACE = timedelta(minutes=1)
# Delay before retrying when no notification channel accepted a message.
DELIVERY_RETRY = timedelta(minutes=1)

STORAGE_VERSION = 1
STORAGE_KEY = DOMAIN

# Every push notification carries this title; the body says what is due.
NOTIFICATION_TITLE = "Task Reminder"

SIGNAL_UPDATE = f"{DOMAIN}_update"

EVENT_FINISHED = f"{DOMAIN}_finished"

# Companion app notification action ids: TASK_REMINDER_<ACTION>_<task id>
ACTION_PREFIX = "TASK_REMINDER_"
ACTION_DONE = "DONE"
ACTION_SNOOZE = "SNOOZE"
ACTION_DISMISS = "DISMISS"
EVENT_MOBILE_ACTION = "mobile_app_notification_action"
