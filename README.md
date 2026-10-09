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
4. On the integration page, **Add task type** for each kind of task.

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

## Actions

`task_reminder.start` (`type`, optional `title`, `message`, `due_in`, `due_at`),
`done`, `snooze`, `dismiss` (by `task_id` or `type`) and `silence` (`mode`, `until`).
Entities: a silencing select, a silencing end-time datetime, an active-tasks sensor.
The `task_reminder_finished` event fires when a task is done or dismissed.

## License

MIT, see [LICENSE](LICENSE).

## Development

```
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -r requirements_test.txt
.venv/bin/python -m pytest
```
