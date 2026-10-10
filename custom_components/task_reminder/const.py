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
CONF_TURN_OFF_PLAYERS = "turn_off_players"
CONF_TAP_URL = "tap_url"
CONF_RING = "ring"  # per task type: keep re-triggering the sound until answered
CONF_RING_SECONDS = "ring_seconds"  # hub default and per task type override
CONF_RING_MINUTES = "ring_minutes"  # how long one reminder keeps ringing at most
CONF_RING_SWAP_SECONDS = "ring_swap_seconds"  # extra time per repeat: the swap takes a moment
CONF_ROOM_PROVIDER = "room_provider"  # entity whose state is the area id of the room you are in
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

# Sounds offered in the sound dropdowns: (file name for the Companion app, label).
# "default" is the standard tri-tone; the .caf files are iOS system sounds that must be
# imported once in the app (Settings, Companion App, Notifications, Sounds, System tab);
# the .wav files ship with the app. Any other file name can be typed.
SOUND_CHOICES = [
    ("default", "Default (tri-tone)"),
    ("alarm.caf", "Alarm (system)"),
    ("Alert_ReminderDue_Haptic.caf", "Reminder due (system)"),
    ("Alert_Calendar_Haptic.caf", "Calendar alert (system)"),
    ("Anticipate.caf", "Anticipate (system)"),
    ("Bloom.caf", "Bloom (system)"),
    ("Calypso.caf", "Calypso (system)"),
    ("Choo_Choo.caf", "Choo Choo (system)"),
    ("Descent.caf", "Descent (system)"),
    ("Fanfare.caf", "Fanfare (system)"),
    ("Ladder.caf", "Ladder (system)"),
    ("Minuet.caf", "Minuet (system)"),
    ("News_Flash.caf", "News Flash (system)"),
    ("Noir.caf", "Noir (system)"),
    ("Sherwood_Forest.caf", "Sherwood Forest (system)"),
    ("Spell.caf", "Spell (system)"),
    ("Suspense.caf", "Suspense (system)"),
    ("Telegraph.caf", "Telegraph (system)"),
    ("Tiptoes.caf", "Tiptoes (system)"),
    ("Typewriters.caf", "Typewriters (system)"),
    ("Update.caf", "Update (system)"),
    ("US-EN-Alexa-Mail-Has-Arrived.wav", "Alexa: mail has arrived (pre-installed)"),
    (
        "US-EN-Morgan-Freeman-Someone-Is-Arriving.wav",
        "Morgan Freeman: someone is arriving (pre-installed)",
    ),
]

HISTORY_LIMIT = 10

# Ringing: re-send the reminder so the sound plays again until it is answered.
DEFAULT_RING_SECONDS = 12  # about the length of the sound
MIN_RING_SECONDS = 5
DEFAULT_RING_MINUTES = 3
# Sending the new notification and removing the old one takes a moment, so from the second repeat
# on the sound would start too early. This much is added to the interval (a rough guess, tunable).
DEFAULT_RING_SWAP_SECONDS = 1.5
# The Companion app allows 500 pushes a day per device (critical alerts and commands such as
# clear_notification do not count). Ringing stops here so other notifications keep working.
PUSH_DAILY_BUDGET = 350
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
