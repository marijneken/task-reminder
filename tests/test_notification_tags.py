"""Every reminder is a new notification; only the newest stays on the phone.

On iOS a notification that replaces one with the same tag makes no sound, and neither does a new
one while the old one is still on screen. So each gets a tag of its own and the previous one is
removed right after the new one is sent."""

from custom_components.task_reminder.const import DOMAIN
from custom_components.task_reminder.models import Task

from .conftest import advance, on_screen, sent, type_data


async def _start(hass, type_):
    await hass.services.async_call(DOMAIN, "start", {"type": type_}, blocking=True)


async def test_repeated_reminders_get_a_new_tag_each_time(hass, freezer, notify, make_entry):
    await make_entry(type_data("washer"))  # no ringing at all
    await _start(hass, "washer")
    await advance(hass, freezer, minutes=5)
    await advance(hass, freezer, minutes=5)
    tags = [c.data["data"]["tag"] for c in sent(notify["phone"])]
    assert len(tags) == 3 and len(set(tags)) == 3  # never the tag of one still on screen
    assert len(on_screen(notify["phone"])) == 1  # only the newest stays


async def test_ringing_keeps_one_notification_on_the_phone(hass, freezer, notify, make_entry):
    await make_entry(type_data("alarm", ring=True))
    await _start(hass, "alarm")
    for _ in range(5):
        await advance(hass, freezer, seconds=12)
    assert len(sent(notify["phone"])) == 6
    assert len(on_screen(notify["phone"])) == 1


async def test_done_snooze_and_dismiss_remove_the_notification(hass, freezer, notify, make_entry):
    await make_entry(type_data("alarm", ring=True), type_data("trash", ring=True, dismissable=True))
    await _start(hass, "alarm")
    await _start(hass, "trash")
    for _ in range(3):
        await advance(hass, freezer, seconds=12)
    assert len(on_screen(notify["phone"])) == 2  # one per task

    await hass.services.async_call(DOMAIN, "snooze", {"type": "alarm"}, blocking=True)
    assert len(on_screen(notify["phone"])) == 1
    await hass.services.async_call(DOMAIN, "dismiss", {"type": "trash"}, blocking=True)
    assert on_screen(notify["phone"]) == []


async def test_the_notification_is_still_removed_after_a_restart(hass, freezer, notify, make_entry):
    entry = await make_entry(type_data("alarm", ring=True))
    await _start(hass, "alarm")
    for _ in range(3):
        await advance(hass, freezer, seconds=12)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    await hass.services.async_call(DOMAIN, "done", {"type": "alarm"}, blocking=True)
    assert on_screen(notify["phone"]) == []


async def test_critical_alerts_are_replaced_the_same_way(hass, freezer, notify, make_entry):
    await make_entry(type_data("alarm", ring=True, snooze_minutes="1"))
    await _start(hass, "alarm")
    await advance(hass, freezer, minutes=5)  # critical stage
    for _ in range(3):
        await advance(hass, freezer, seconds=12)
    assert len(on_screen(notify["phone"])) == 1


async def test_the_away_note_is_removed_when_done(hass, notify, make_entry):
    await make_entry(type_data("washer"))
    hass.states.async_set("person.marijn", "not_home")
    await _start(hass, "washer")
    assert len(on_screen(notify["phone"])) == 1  # the quiet "you're away" note
    await hass.services.async_call(DOMAIN, "done", {"type": "washer"}, blocking=True)
    assert on_screen(notify["phone"]) == []


async def test_a_pile_left_by_version_0_14_is_cleaned_up_at_the_next_reminder(
    hass, freezer, notify, make_entry
):
    entry = await make_entry(type_data("alarm", ring=True))
    await _start(hass, "alarm")
    (task,) = entry.runtime_data.tasks.values()
    task.tags = ["old_1", "old_2", *task.tags]  # as if several had piled up
    await advance(hass, freezer, seconds=12)
    assert len(task.tags) == 1  # only the newest is remembered, the rest were cleared
    cleared = [
        c.data["data"]["tag"] for c in notify["phone"] if c.data["message"] == "clear_notification"
    ]
    assert {"old_1", "old_2"} <= set(cleared)


def test_tasks_saved_by_older_versions_keep_their_notification_tag():
    task = Task.from_dict(
        {
            "id": "abc",
            "type_key": "washer",
            "title": "Washer",
            "created_at": "2026-10-10T12:00:00+00:00",
            "status": "notifying",
            "ring_tag": "task_reminder_abc_r3",
        }
    )
    assert task.tags == ["task_reminder_abc_r3"]
