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

## How it escalates

| Notification | Goes to |
| --- | --- |
| 1st | phone |
| 2nd | phone + Alexa |
| 3rd | + other devices |
| from the (snoozes + 1)th | "keeps going": critical alert on the phone, repeat every few minutes |

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
- **When done, start** another type (washer → dryer)

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

  It returns the `task_id`. Ad hoc reminders may break quiet hours and can be dismissed
  (turn off with `time_critical: false` / `dismissable: false`); several can run at once.
  Complete or stop them with `task_reminder.done` / `dismiss` (by `task_id`, or `task: ad_hoc`).

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
