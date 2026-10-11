"""Starting from an afvalbeheer-style schedule sensor."""

from custom_components.task_reminder.const import DOMAIN

from .conftest import advance, type_data

SENSOR = "sensor.almere_papier"


def _set(hass, days, date="20261013", state="Dinsdag, 13-10-2026"):
    hass.states.async_set(
        SENSOR,
        state,
        {"Wastecollector": "almere", "Sort_date": int(date), "Days_until": days},
    )


def _papier(**overrides):
    return type_data("papier", schedule_entity=SENSOR, due_time="19:00:00", **overrides)


async def test_starts_the_day_before_and_is_due_in_the_evening(hass, freezer, notify, make_entry):
    entry = await make_entry(_papier())
    _set(hass, 3)
    await hass.async_block_till_done()
    assert entry.runtime_data.tasks == {}

    _set(hass, 2)
    await hass.async_block_till_done()
    assert entry.runtime_data.tasks == {}

    _set(hass, 1)  # midnight flip, simulated at 12:00
    await hass.async_block_till_done()
    (task,) = entry.runtime_data.tasks.values()
    assert task.status == "armed" and task.extra["collection"] == "20261013"

    await advance(hass, freezer, hours=7)  # 19:00
    assert len(notify["phone"]) == 1


async def test_started_once_per_collection(hass, make_entry):
    entry = await make_entry(_papier())
    _set(hass, 1)
    await hass.async_block_till_done()
    await hass.services.async_call(DOMAIN, "done", {"type": "papier"}, blocking=True)

    _set(hass, 1)  # attribute-only updates must not restart a finished task
    hass.states.async_set(
        SENSOR, "Dinsdag, 13-10-2026", {"Sort_date": 20261013, "Days_until": 1, "x": 1}
    )
    await hass.async_block_till_done()
    assert entry.runtime_data.tasks == {}


async def test_missed_start_is_due_immediately_after_restart(hass, notify, make_entry):
    entry = await make_entry(_papier())
    _set(hass, 0)  # collection day, nothing was started (HA was down)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert len(entry.runtime_data.tasks) == 1
    assert len(notify["phone"]) == 1  # not "at 19:00": that is too late


async def test_restart_does_not_repeat_a_finished_task(hass, make_entry):
    entry = await make_entry(_papier())
    _set(hass, 1)
    await hass.async_block_till_done()
    await hass.services.async_call(DOMAIN, "done", {"type": "papier"}, blocking=True)

    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.tasks == {}


async def test_unfinished_task_expires_when_collection_passes(hass, notify, make_entry):
    entry = await make_entry(_papier())
    events = []
    hass.bus.async_listen("task_reminder_finished", events.append)
    _set(hass, 0)
    await hass.async_block_till_done()
    assert len(entry.runtime_data.tasks) == 1

    _set(hass, 14, date="20261027", state="Dinsdag, 27-10-2026")  # next collection
    await hass.async_block_till_done()
    assert entry.runtime_data.tasks == {}
    assert events[-1].data["outcome"] == "expired"

    _set(hass, 1, date="20261027", state="Dinsdag, 27-10-2026")  # and the next cycle starts
    await hass.async_block_till_done()
    assert len(entry.runtime_data.tasks) == 1


async def test_manual_tasks_do_not_expire(hass, make_entry):
    entry = await make_entry(_papier())
    await hass.services.async_call(DOMAIN, "start", {"type": "papier"}, blocking=True)
    _set(hass, 14)
    await hass.async_block_till_done()
    assert len(entry.runtime_data.tasks) == 1


async def test_unusable_sensor_is_ignored(hass, make_entry):
    entry = await make_entry(_papier())
    hass.states.async_set(SENSOR, "unavailable")
    hass.states.async_set(SENSOR, "weird", {"Days_until": "n/a"})
    await hass.async_block_till_done()
    assert entry.runtime_data.tasks == {}


async def test_a_late_flip_after_the_due_time_is_due_at_once(hass, freezer, notify, make_entry):
    entry = await make_entry(_papier())
    await advance(hass, freezer, hours=8)  # 20:00, the 19:00 due time of the start day has passed
    _set(hass, 1)
    await hass.async_block_till_done()
    assert len(entry.runtime_data.tasks) == 1
    assert len(notify["phone"]) == 1  # now, not tomorrow evening


async def test_due_time_belongs_to_the_start_day_not_to_tomorrow(hass, freezer, notify, make_entry):
    entry = await make_entry(type_data("papier", schedule_entity=SENSOR, due_time="18:00:00"))
    _set(hass, 1)  # collection is tomorrow (10-10): the first reminder is today at 18:00
    await hass.async_block_till_done()
    (task,) = entry.runtime_data.tasks.values()
    assert task.status == "armed" and task.due_at.isoformat() == "2026-10-09T18:00:00+00:00"
    await advance(hass, freezer, hours=5, minutes=59)
    assert notify["phone"] == []
    await advance(hass, freezer, minutes=1)
    assert len(notify["phone"]) == 1


async def test_collection_day_ends_at_the_end_time(hass, freezer, notify, make_entry):
    entry = await make_entry(_papier(collection_end_time="08:00:00"))
    events = []
    hass.bus.async_listen("task_reminder_finished", events.append)
    _set(hass, 1)
    await hass.async_block_till_done()
    await advance(hass, freezer, hours=12)  # midnight: the sensor flips to collection day
    _set(hass, 0)
    await hass.async_block_till_done()
    assert len(entry.runtime_data.tasks) == 1
    await advance(hass, freezer, hours=7, minutes=59)
    assert len(entry.runtime_data.tasks) == 1  # 07:59, the bins are still coming
    await advance(hass, freezer, minutes=1)  # 08:00
    assert entry.runtime_data.tasks == {}
    assert events[-1].data["outcome"] == "expired"


async def test_nothing_starts_after_the_end_time(hass, make_entry):
    entry = await make_entry(_papier(collection_end_time="08:00:00"))
    _set(hass, 0)  # collection day, but it is 12:00: too late to bring the bin out
    await hass.async_block_till_done()
    assert entry.runtime_data.tasks == {}
