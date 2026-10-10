"""How many of a task's notifications stay in the list: every reminder and every ring is a
new notification (a replaced one makes no sound), the setting decides how many pile up."""

from custom_components.task_reminder.const import DOMAIN
from custom_components.task_reminder.models import Task

from .conftest import advance, on_screen, sent, type_data


async def _start(hass, type_):
    await hass.services.async_call(DOMAIN, "start", {"type": type_}, blocking=True)


def ringer(**kw):
    return type_data("alarm", ring=True, **kw)


async def test_repeated_reminders_get_a_new_tag_so_they_make_sound(
    hass, freezer, notify, make_entry
):
    await make_entry(type_data("washer"))  # no ringing at all
    await _start(hass, "washer")
    await advance(hass, freezer, minutes=5)
    await advance(hass, freezer, minutes=5)
    tags = [c.data["data"]["tag"] for c in sent(notify["phone"])]
    assert len(tags) == 3 and len(set(tags)) == 3  # never the tag of one still on screen
    assert len(on_screen(notify["phone"])) == 1  # default: the previous one is removed


async def test_default_keeps_one(hass, freezer, notify, make_entry):
    await make_entry(ringer())
    await _start(hass, "alarm")
    for _ in range(5):
        await advance(hass, freezer, seconds=12)
    assert len(sent(notify["phone"])) == 6
    assert len(on_screen(notify["phone"])) == 1


async def test_keeping_three_lets_three_pile_up_and_drops_the_oldest(
    hass, freezer, notify, make_entry
):
    await make_entry(ringer(), notifications_kept=3)
    await _start(hass, "alarm")
    for _ in range(5):
        await advance(hass, freezer, seconds=12)
    shown = on_screen(notify["phone"])
    all_tags = [c.data["data"]["tag"] for c in sent(notify["phone"])]
    assert shown == all_tags[-3:]  # the newest three, oldest first


async def test_a_large_number_lets_everything_pile_up(hass, freezer, notify, make_entry):
    await make_entry(ringer(), notifications_kept=100)
    await _start(hass, "alarm")
    for _ in range(5):
        await advance(hass, freezer, seconds=12)
    assert len(on_screen(notify["phone"])) == 6  # nothing was removed
    assert not [c for c in notify["phone"] if c.data["message"] == "clear_notification"]


async def test_done_snooze_and_dismiss_remove_the_whole_pile(hass, freezer, notify, make_entry):
    await make_entry(
        ringer(), type_data("trash", ring=True, dismissable=True), notifications_kept=100
    )
    await _start(hass, "alarm")
    await _start(hass, "trash")
    for _ in range(3):
        await advance(hass, freezer, seconds=12)
    assert len(on_screen(notify["phone"])) == 8

    await hass.services.async_call(DOMAIN, "snooze", {"type": "alarm"}, blocking=True)
    assert len(on_screen(notify["phone"])) == 4  # only the trash pile is left
    await hass.services.async_call(DOMAIN, "dismiss", {"type": "trash"}, blocking=True)
    assert on_screen(notify["phone"]) == []


async def test_done_removes_a_pile_too(hass, freezer, notify, make_entry):
    await make_entry(ringer(), notifications_kept=100)
    await _start(hass, "alarm")
    for _ in range(4):
        await advance(hass, freezer, seconds=12)
    await hass.services.async_call(DOMAIN, "done", {"type": "alarm"}, blocking=True)
    assert on_screen(notify["phone"]) == []


async def test_going_back_to_one_trims_an_existing_pile(hass, freezer, notify, make_entry):
    entry = await make_entry(ringer(), notifications_kept=5)
    await _start(hass, "alarm")
    for _ in range(4):
        await advance(hass, freezer, seconds=12)
    assert len(on_screen(notify["phone"])) == 5

    hass.config_entries.async_update_entry(entry, data={**entry.data, "notifications_kept": 1})
    await hass.async_block_till_done()  # the entry reloads; the running task keeps going
    await advance(hass, freezer, seconds=12)
    assert len(on_screen(notify["phone"])) == 1


async def test_a_pile_survives_a_restart_and_is_still_removed_on_done(
    hass, freezer, notify, make_entry
):
    entry = await make_entry(ringer(), notifications_kept=100)
    await _start(hass, "alarm")
    for _ in range(3):
        await advance(hass, freezer, seconds=12)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    await hass.services.async_call(DOMAIN, "done", {"type": "alarm"}, blocking=True)
    assert on_screen(notify["phone"]) == []


async def test_critical_alerts_pile_up_too(hass, freezer, notify, make_entry):
    await make_entry(ringer(snooze_minutes="1"), notifications_kept=100)
    await _start(hass, "alarm")
    await advance(hass, freezer, minutes=5)  # critical stage
    for _ in range(3):
        await advance(hass, freezer, seconds=12)
    assert len(on_screen(notify["phone"])) >= 5
    await hass.services.async_call(DOMAIN, "done", {"type": "alarm"}, blocking=True)
    assert on_screen(notify["phone"]) == []


async def test_the_away_note_is_removed_when_done(hass, notify, make_entry):
    await make_entry(type_data("washer"))
    hass.states.async_set("person.marijn", "not_home")
    await _start(hass, "washer")
    assert len(on_screen(notify["phone"])) == 1  # the quiet "you're away" note
    await hass.services.async_call(DOMAIN, "done", {"type": "washer"}, blocking=True)
    assert on_screen(notify["phone"]) == []


async def test_the_setting_is_kept_within_sensible_limits(hass, make_entry):
    entry = await make_entry(type_data("washer"), notifications_kept=0)
    assert entry.runtime_data._kept() == 1
    hass.config_entries.async_update_entry(entry, data={**entry.data, "notifications_kept": 5000})
    await hass.async_block_till_done()
    assert entry.runtime_data._kept() == 100


def test_tasks_saved_by_the_previous_version_keep_their_notification_tag():
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
