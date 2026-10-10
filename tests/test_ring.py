"""Ringing: keep re-triggering the sound until the task is answered."""

from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util

from custom_components.task_reminder.const import DOMAIN

from .conftest import advance, type_data


def alarm(**kw):
    return type_data("alarm", ring=True, **kw)


async def _start(hass, type_="alarm", **data):
    await hass.services.async_call(DOMAIN, "start", {"type": type_, **data}, blocking=True)


def reminders(notify):
    return [c for c in notify["phone"] if c.data["message"] != "clear_notification"]


def clears(notify):
    return [
        c.data["data"]["tag"] for c in notify["phone"] if c.data["message"] == "clear_notification"
    ]


def on_screen(notify):
    """Tags that are on the phone right now: sent and not cleared."""
    shown: list[str] = []
    for c in notify["phone"]:
        tag = c.data["data"]["tag"]
        if c.data["message"] == "clear_notification":
            if tag in shown:
                shown.remove(tag)
        elif tag not in shown:
            shown.append(tag)
    return shown


async def test_refresh_style_rings_with_new_notifications_and_a_list_of_one(
    hass, freezer, notify, make_entry
):
    await make_entry(alarm())
    await _start(hass)
    assert len(reminders(notify)) == 1

    for expected in (2, 3, 4):
        await advance(hass, freezer, seconds=12)
        assert len(reminders(notify)) == expected
        assert len(on_screen(notify)) == 1  # the list never grows
    tags = [c.data["data"]["tag"] for c in reminders(notify)]
    assert len(set(tags)) == 4  # a fresh notification each time, so the sound surely plays
    assert all(
        c.data["message"] == "alarm is due" or "Alarm" in c.data["message"]
        for c in reminders(notify)
    )
    assert len({c.data["message"] for c in reminders(notify)}) == 1  # same text every time


async def test_replace_style_reuses_the_same_notification(hass, freezer, notify, make_entry):
    await make_entry(alarm(), ring_style="replace")
    await _start(hass)
    for _ in range(3):
        await advance(hass, freezer, seconds=12)
    tags = {c.data["data"]["tag"] for c in reminders(notify)}
    assert len(reminders(notify)) == 4 and len(tags) == 1
    assert clears(notify) == []  # nothing to clear: iOS replaces it in place


async def test_only_the_phone_rings(hass, freezer, notify, make_entry):
    await make_entry(alarm())
    await _start(hass)
    for _ in range(5):
        await advance(hass, freezer, seconds=12)
    assert notify["alexa"] == []
    # Other devices only ever get the clear commands, never a re-triggered reminder.
    assert reminders({"phone": notify["extra"]}) == []


async def test_snooze_stops_the_ringing_and_clears_the_phone(hass, freezer, notify, make_entry):
    await make_entry(alarm())
    await _start(hass)
    await advance(hass, freezer, seconds=12)
    await hass.services.async_call(DOMAIN, "snooze", {"type": "alarm"}, blocking=True)
    assert on_screen(notify) == []
    count = len(reminders(notify))
    await advance(hass, freezer, seconds=60)
    assert len(reminders(notify)) == count


async def test_done_and_dismiss_stop_the_ringing(hass, freezer, notify, make_entry):
    await make_entry(alarm(), type_data("trash", ring=True, dismissable=True))
    await _start(hass)
    await _start(hass, "trash")
    await advance(hass, freezer, seconds=12)
    await hass.services.async_call(DOMAIN, "done", {"type": "alarm"}, blocking=True)
    await hass.services.async_call(DOMAIN, "dismiss", {"type": "trash"}, blocking=True)
    assert on_screen(notify) == []
    count = len(reminders(notify))
    await advance(hass, freezer, seconds=60)
    assert len(reminders(notify)) == count


async def test_ringing_stops_after_the_window_until_the_next_reminder(
    hass, freezer, notify, make_entry
):
    await make_entry(alarm())  # window 3 minutes, interval 12 s, regular repeat after 5 minutes
    await _start(hass)
    for _ in range(15):  # 3 minutes
        await advance(hass, freezer, seconds=12)
    # The original plus re-triggers at 12, 24, ... 168 s; none at 180 s: the window is over.
    assert len(reminders(notify)) == 15

    for _ in range(9):  # up to 4:48
        await advance(hass, freezer, seconds=12)
    assert len(reminders(notify)) == 15  # quiet between the window and the next reminder

    await advance(hass, freezer, seconds=12)  # 5:00: the regular reminder, which rings again
    assert len(reminders(notify)) == 16
    await advance(hass, freezer, seconds=12)
    assert len(reminders(notify)) == 17


async def test_critical_alerts_are_not_used_while_ringing(hass, freezer, notify, make_entry):
    await make_entry(alarm(snooze_minutes="1"))  # keeps-going (critical) after one reminder
    await _start(hass)
    for _ in range(40):
        await advance(hass, freezer, seconds=15)
    pushes = [c.data["data"].get("push", {}) for c in reminders(notify)]
    assert pushes and not any(
        isinstance(p.get("sound"), dict) and p["sound"].get("critical") for p in pushes
    )


async def test_the_regular_reminder_replaces_a_leftover_ring_notification(
    hass, freezer, notify, make_entry
):
    await make_entry(alarm())
    await _start(hass)
    for _ in range(25):  # past the ring window and up to the regular reminder at 5:00
        await advance(hass, freezer, seconds=12)
    assert len(on_screen(notify)) == 1


async def test_per_type_interval_and_the_minimum(hass, freezer, notify, make_entry):
    await make_entry(
        type_data("slow", ring=True, ring_seconds=30), type_data("fast", ring=True, ring_seconds=1)
    )
    await _start(hass, "slow")
    await advance(hass, freezer, seconds=29)
    assert len(reminders(notify)) == 1
    await advance(hass, freezer, seconds=1)
    assert len(reminders(notify)) == 2

    await _start(hass, "fast")  # 1 s is raised to the 5 s minimum
    before = len(reminders(notify))
    await advance(hass, freezer, seconds=4)
    assert len(reminders(notify)) == before
    await advance(hass, freezer, seconds=1)
    assert len(reminders(notify)) == before + 1


async def test_hub_interval_is_the_default(hass, freezer, notify, make_entry):
    await make_entry(alarm(), ring_seconds=20)
    await _start(hass)
    await advance(hass, freezer, seconds=19)
    assert len(reminders(notify)) == 1
    await advance(hass, freezer, seconds=1)
    assert len(reminders(notify)) == 2


async def test_types_do_not_ring_unless_asked(hass, freezer, notify, make_entry):
    await make_entry(type_data("washer"))
    await _start(hass, "washer")
    await advance(hass, freezer, minutes=2)
    assert len(reminders(notify)) == 1


async def test_timers_ring_by_default_and_can_opt_out(hass, freezer, notify, make_entry):
    await make_entry()
    await hass.services.async_call(DOMAIN, "remind", {"title": "Egg timer"}, blocking=True)
    await advance(hass, freezer, seconds=12)
    assert len(reminders(notify)) == 2

    await hass.services.async_call(
        DOMAIN, "remind", {"title": "Quiet one", "ring": False}, blocking=True
    )
    before = len(reminders(notify))
    await advance(hass, freezer, seconds=12)
    quiet_rings = [c for c in reminders(notify)[before:] if "Quiet" in c.data["message"]]
    assert quiet_rings == []


async def test_daily_push_budget_stops_ringing_and_says_so(hass, freezer, notify, make_entry):
    entry = await make_entry(alarm())
    today = dt_util.utcnow().date().isoformat()
    entry.runtime_data.pushes = {"day": today, "n": 349}
    await _start(hass)  # this push is the 350th
    await advance(hass, freezer, seconds=12)
    assert len(reminders(notify)) == 1  # no ring: the budget is used
    issue = ir.async_get(hass).async_get_issue(DOMAIN, "ring_budget")
    assert issue is not None and issue.translation_placeholders == {"count": "350"}
    # Regular reminders still go out.
    await advance(hass, freezer, minutes=5)
    assert len(reminders(notify)) == 2


async def test_pushes_are_counted_but_clears_and_critical_are_not(
    hass, freezer, notify, make_entry
):
    entry = await make_entry(alarm())
    await _start(hass)
    assert entry.runtime_data.pushes_today() == 1
    await advance(hass, freezer, seconds=12)  # new notification (+1), previous one cleared (free)
    assert entry.runtime_data.pushes_today() == 2
    await hass.services.async_call(DOMAIN, "done", {"type": "alarm"}, blocking=True)
    assert entry.runtime_data.pushes_today() == 2


async def test_the_count_starts_again_each_utc_day(hass, freezer, notify, make_entry):
    entry = await make_entry(type_data("washer"))
    entry.runtime_data.pushes = {"day": "2026-10-08", "n": 400}
    assert entry.runtime_data.pushes_today() == 0
    await _start(hass, "washer")
    assert entry.runtime_data.pushes == {"day": "2026-10-09", "n": 1}


async def test_ringing_survives_a_restart(hass, freezer, notify, make_entry):
    entry = await make_entry(alarm())
    await _start(hass)
    await advance(hass, freezer, seconds=12)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    before = len(reminders(notify))
    await advance(hass, freezer, seconds=12)
    assert len(reminders(notify)) > before
