# Task Reminder

Home Assistant custom integration (`task_reminder`) that reminds you of tasks
and keeps reminding until the task is actually done. Snoozes get shorter and
then stop, reminders widen from phone to Alexa to every device, and only doing
the task (or dismissing a task that allows it) ends it. Everything is stored
with absolute times, so a restart loses nothing.

## Install

1. HACS → ⋮ → Custom repositories → `https://github.com/marijneken/task-reminder`, type Integration.
2. Download **Task Reminder**, restart Home Assistant.
3. Settings → Devices & services → Add integration → Task Reminder. Choose your
   person entity and the notify services (phone, other devices) and your Alexa speakers.
4. On the integration page, **Add task type** for each kind of recurring reminder (washer, trash, ...).

Every bump of `version` in `manifest.json` on `main` publishes a release `vX.Y.Z`; HACS
shows the installed version and offers new ones as updates (restart Home Assistant after
updating).

## What a notification looks like

Every push has the title **Task Reminder**; the body says what is due ("Washer is due", later "Washer is still
waiting"). Buttons: **Done** (you did it: finishes the task, starts a chained one, resets a fill flag),
**Snooze** (while snoozes are left) and **Dismiss** (only for dismissable tasks: ends it *without* doing it).
On iOS the buttons appear when you long-press or pull down the notification; the Apple Watch shows them directly.
The icon is always the Home Assistant app icon on iOS. Tapping opens Home Assistant at the page you set in the
integration settings (`/lovelace/...`), or its default page when empty.

## Where you are: the room presence provider

Choose a **Room presence provider** in the integration settings: an entity whose state is the id of the Home
Assistant **area** you are in (from your own presence system). Only areas are used; there is nothing else to
configure. It decides three things:

- **Which Alexa speaks first.** The 2nd reminder is announced only by the speakers in your area, from the 3rd
  reminder every speaker is used. Pick your Echo speakers (their Alexa Media Player `media_player` entities) in
  the settings and put each one in its area in Home Assistant; that is all, nothing is matched by name. An
  entity's own area wins over its device's. Announcements go through `notify.alexa_media` with the speakers as
  targets.
- **Which lights flash.** In the keeps-going stage, every reminder flashes the lights of your area (a long flash,
  then back to how they were) as one more annoyance. Never while silencing is active, never for the light ladder,
  and not for the repeats of a ringing reminder.
- **Whether a TV is worth turning off** (see below): when you are in its area, or when it is playing.

When the provider is not set, unknown or unavailable, or names no area (`none`, `away`, an area that does not
exist), your place is **unknown**: every speaker announces, no lights flash, and any TV that is on is a candidate.
The Tasks panel shows the area you are in, in its header.

## Notification sound (iPhone)

Pick the sound in the integration settings (**Notification sound (iPhone)**), and optionally per task type
(for example another sound for the washer). It is a dropdown with the standard sounds; you can also type the
exact file name of any other sound. Critical alerts use the same sound. Empty keeps the default.

- `Default (tri-tone)` and the **pre-installed** sounds (`US-EN-...wav`, spoken clips) work right away.
- The **iOS system sounds** (Alarm, Anticipate, Bloom, Calypso, Ladder, Telegraph, ...) are `.caf` files that the
  Companion app has to import **once**: in the app go to Settings, Companion App, Notifications, Sounds, open the
  **System** tab and tap **Import system sounds**, then restart the phone. After that they can be selected here.
- **Your own sounds**: 32-bit float 48 kHz `.wav` files, imported in the same Sounds screen (via iTunes File
  Sharing or a cloud storage app); type the file name including `.wav`.
- Always the full file name with extension. Android uses notification channels instead (change the sound in the
  channel settings of the app).

## Ringing like an alarm

A single notification plays its sound once and is easy to ignore. Tasks that **ring** keep re-triggering the
sound on the phone, like a timer on Alexa, until you **snooze, complete or dismiss** them:

- Turn on **Ring until answered** per task type. Reminders and timers from `task_reminder.remind` ring by
  default (`ring: false` to opt out).
- Every **ring interval** seconds (integration settings, default 12; or per task type) the phone gets the
  reminder again. Set it to about the length of your sound plus a second or two. I cannot read the length of
  a sound that lives on your phone: check the file on your Mac (Finder, Get Info, or QuickTime). iOS plays at
  most 30 seconds of a custom sound.
- A reminder rings for at most **ring for** minutes (default 3); the next regular reminder rings again.
- The first repeat comes exactly one ring interval after the reminder. Every repeat after that waits
  **extra time per repeat** longer (default 1.5 seconds, a rough guess): sending the new notification and removing
  the old one takes a moment, so those sounds would otherwise start too early. Adjust it until the repeats follow the
  sound without a gap or overlap.
- Every reminder and every re-trigger is a **new notification** with a tag of its own, and the previous one is
  removed right after the new one is sent. Both matter on iOS: a notification that replaces one with the same
  tag makes no sound, and neither does a new one while the old one is still on screen. (So the old notification
  can vanish for a moment before the new one has arrived; that is the best that can be done.) Done, snooze and
  dismiss remove the notification.
- Only the phone rings, never Alexa or your other devices.
- **Critical alerts keep working**: when a reminder is a critical alert (the keeps-going stage), its re-triggers
  are critical alerts too, so they get through the silent switch and Focus. iOS cannot replace or group critical
  alerts, so those may pile up in the notification list until you answer.
- The Companion app allows **500 notifications a day per device**. Critical alerts and clear commands do not
  count; the other re-triggers do. Ringing with ordinary notifications stops at 350 pushes for the day, so the
  rest keep working, and a Repairs message says so. Critical ringing is never stopped by this.

## A toast on the TV

Choose the notify service of a TV (for example the LG webOS one) under **TV notify services**. From the
third reminder on, together with the other devices, the TV shows a plain toast with the reminder text. It has
no title, buttons or sound, and a TV that is off is skipped without a warning. The toast disappears by
itself, so a ringing reminder shows it again every time the phone rings again. Put the TV here and not under
**Other devices** (the iPad and Mac belong there: they are Companion apps and take the phone's payload); a TV
listed in both only gets the toast.

## Countdown on the lock screen (iPhone, optional)

Switch on **Countdown on the lock screen** in the settings and a timer (`remind` with a delay), or a task
that is waiting for its due time or for a snooze to end, shows an iOS Live Activity on the lock screen
(and in the Dynamic Island, as far as the Companion app uses it) that counts down to the next reminder.
The phone counts by itself, so one push starts it. It starts when the due time is less than 7 hours away
(iOS ends activities after 8), is updated when you snooze, and ends when the reminder arrives or the task is
done, dismissed or cancelled. Not during silencing, quiet hours (except time-critical reminders) or while
away. Needs the Companion app and Home Assistant versions the
[Companion docs](https://companion.home-assistant.io/docs/notifications/live-activities/) name; with an older
app the push shows as a plain notification, so try it first. Phones only.

## How it escalates

| Notification | Goes to |
| --- | --- |
| 1st | phone |
| 2nd | phone + Alexa |
| 3rd | + other devices |
| from the (snoozes + 1)th | "keeps going": critical alert on the phone, repeat every few minutes |

Choose media players in the integration settings to have whatever is playing on them paused when a
reminder reaches the other devices (the 3rd notification); it resumes when the task ends (done, dismissed or
expired), unless you already resumed it yourself. 

As a last resort you can choose media players (your TV) to **turn off**: once the snoozes are used up and the
second keeps-going reminder is sent, the ones you are watching are turned off, once per task: a TV in the area you
are in (even paused), or a TV that is playing wherever you are. A TV that is on in an area you are not in and not
playing is left alone. If your place is unknown, any TV that is on is turned off. Never while silencing
is active, never for the light ladder, and they are not turned back on afterwards. Dismissable tasks with a fill flag that is off use a lighter
ladder (phone and Alexa only) and never pause media. If no notify service is configured, a Repairs warning says so.

Snoozes are limited (default 10, 5, 3 minutes); after the last one the Snooze
button disappears. Quiet hours hold non time-critical reminders, being away
holds everything after one passive notification, and silencing (with a required
end time) either drops critical alerts or holds everything.

## Task type options

- **Dismissable / time critical / one running at a time**
- **Due** after a duration, at a time of day, or when an entity changes state
- **Start / done** when an entity changes state. Done only counts once the task is due.
  A **done sequence** (e.g. back door, then porch door within 5 minutes) is also possible.
- **Fill flag entity** (e.g. an `input_boolean` "bin has waste"): flag off makes the task
  dismissable with a lighter ladder; completing the task turns the flag off. With
  "quiet heads-up" a flag-off task sends one passive notification and ends.
- **Collection schedule sensor** (afvalbeheer, uses its `Days_until` attribute) with **start N days
  before**: the task is created once per collection date, and "Due at time of day" is the time on the
  start day (e.g. 18:00 the evening before) when the reminders begin. If that moment has already passed
  when the schedule flips, the first reminder comes at once. Until then it waits in the panel's "Coming
  up", and a done trigger does not count yet. **Stop reminding at** (optional, e.g. 08:00) ends the task
  on collection day (`expired`); without it the task ends when the sensor moves on to the next collection.
  To bring the bin back later, make a second type (due 16:00, same done doors) and link it with
  "When done, start" on the first one: it starts when the first is done and needs the doors again.
- **NFC tags**: start and/or done on a scanned tag (pick tags from Settings, Tags). A scan always
  completes the task, even before it is due; the same tag for start and done toggles.
- **Good moments**: binary sensors (e.g. stairwell motion). While a reminder is unanswered, one of them
  turning on brings the next reminder forward (at most every 2 minutes, never during a snooze).
- **When done, start** another type (washer → dryer)

## The Tasks panel

A **Tasks** item appears in the sidebar and shows everything at a glance, live:

- **Needs you**: reminders that went out and wait for you, with how long ago, when the next one comes,
  how far up the escalation ladder they are (phone, Alexa, all devices, keeps going) and Done / Snooze / Dismiss.
- **Snoozed**, **Coming up** (due times with a live countdown, plus the next collections for tasks that follow a
  schedule sensor and when they will start) and **On hold** (quiet hours, away, silent).
- **Quick reminder** (a title and minutes, e.g. an egg timer) and one-tap **Start a task** for your task types.
- **Silence reminders** with a mandatory duration, a banner while it is active, and the last 10 finished tasks.

Times and dates follow your Home Assistant profile (12/24 hour, language, date order and the local or server
time zone), not the browser's defaults. The panel's own labels are English.

The **Settings** button in the panel's header (administrators only) takes you to the Task Reminder integration
with your entry highlighted, so changing a setting or adding a task type or room is one click on *Configure* (or the
entry's menu) away. Home Assistant has no link that opens that dialog directly. Use the browser's back button to
return to the panel.

Tasks that are not due yet have **Cancel**, which drops them without side effects (no chained task, no flag reset).

## Quick reminders and timers (no setup)

- Press **Test reminder** (button on the Task Reminder device) to get a reminder right now:
  the quickest check that notifications, the Done / Snooze / Dismiss buttons and escalation work.
- `task_reminder.remind` starts a reminder or timer without any configured task:

  ```yaml
  action: task_reminder.remind
  data:
    title: Egg timer
    message: The eggs are done
    due_in: "00:07:00"          # or due_at: "2026-10-09 15:00:00"; omit both for "now"
  ```

  It returns the `task_id`. Ad hoc reminders may break quiet hours (`time_critical: false` to opt out)
  and end with **Done**; add `dismissable: true` if you also want a Dismiss button. Several can run at once.
  Complete them with `task_reminder.done` (by `task_id`, or `type: ad_hoc`).

An egg timer for your dashboard (or to expose to Alexa) is just a script with a field:

```yaml
script:
  egg_timer:
    alias: Egg timer
    fields:
      minutes:
        name: Minutes
        default: 7
        selector: {number: {min: 1, max: 120}}
    sequence:
      - action: task_reminder.remind
        data:
          title: Egg timer
          message: The eggs are done
          due_in: {minutes: "{{ minutes }}"}
```

## Actions

`task_reminder.start` (`type`, optional `title`, `message`, `due_in`, `due_at`),
`done`, `snooze`, `dismiss` (by `task_id` or `type`) and `silence` (`mode`, `until`).
Entities: a silencing select, a silencing end-time datetime, an active-tasks sensor.
The `task_reminder_finished` event fires when a task is done or dismissed.

## API access

Everything the UI does can be driven through Home Assistant's own API with a long-lived
access token, since the UI is built on it:

- Actions (`start`, `remind`, `done`, `snooze`, `dismiss`, `silence`):
  `POST /api/services/task_reminder/<action>` (add `?return_response` for the task id).
- Adding or editing a task type: the config entries API that the frontend uses, a multi-step flow:
  `POST /api/config/config_entries/subentries/flow` with `{"handler": ["<entry_id>", "task_type"]}`
  (add `"subentry_id"` to edit), then `POST /api/config/config_entries/subentries/flow/<flow_id>`
  with the form values. Listing, updating and deleting: websocket `config_entries/subentries/list`,
  `update`, `delete`.
- State: the *Active tasks* sensor lists every running task with its status and times.

## License

MIT, see [LICENSE](LICENSE).

## Development

```
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -r requirements_test.txt
.venv/bin/python -m pytest
```
