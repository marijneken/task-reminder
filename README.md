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
   person entity and the notify services per tier (phone, Alexa, other devices).
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

## Rooms and Alexa

Add **rooms** on the integration page (**Add room**): a name, the presence or motion sensors in it, and the
Alexa notify service of the speaker there. The 2nd reminder is announced only by the speaker in the room you
are in: the room that shows presence now (or, if several, the one seen most recently), else the room that
showed presence in the last 10 minutes. From the 3rd reminder every speaker is used, and when no room is known
(or the room has no speaker) all speakers are used, as before. Room speakers do not need to be listed in the
integration settings too. The Tasks panel shows the current room in its header.

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
- Each re-trigger is a **new notification**, so the sound surely plays (a notification replaced by one with the
  same tag makes no sound on iOS). The previous one is removed **two seconds after** the new one was sent, so
  it never disappears before the new one has arrived, and the list stays at one.
- Only the phone rings, never Alexa or your other devices.
- **Critical alerts keep working**: when a reminder is a critical alert (the keeps-going stage), its re-triggers
  are critical alerts too, so they get through the silent switch and Focus. iOS cannot replace or group critical
  alerts, so those may pile up in the notification list until you answer.
- The Companion app allows **500 notifications a day per device**. Critical alerts and clear commands do not
  count; the other re-triggers do. Ringing with ordinary notifications stops at 350 pushes for the day, so the
  rest keep working, and a Repairs message says so. Critical ringing is never stopped by this.

## How it escalates

| Notification | Goes to |
| --- | --- |
| 1st | phone |
| 2nd | phone + Alexa |
| 3rd | + other devices |
| from the (snoozes + 1)th | "keeps going": critical alert on the phone, repeat every few minutes |

Choose media players in the integration settings to have whatever is playing on them paused when a
reminder reaches the other devices (the 3rd notification); it resumes when the task ends (done, dismissed or
expired), unless you already resumed it yourself. As a last resort you can choose media players (your TV) to **turn off**: once the snoozes are used up and the
second keeps-going reminder is sent, those that are still on are turned off, once per task. Never while silencing
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
- **Collection schedule sensor** (afvalbeheer, uses its `Days_until` and `Sort_date`
  attributes) with **start N days before**: the task starts once per collection date,
  immediately if that moment was missed, and ends as `expired` once the collection has
  passed. Combine with "Due at time of day" (e.g. 19:00 the evening before).
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
