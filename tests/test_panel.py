"""The Tasks panel: websocket API and snapshot."""

from pathlib import Path

from custom_components.task_reminder.const import DOMAIN

from .conftest import advance, type_data


async def _snapshot(client):
    await client.send_json_auto_id({"type": "task_reminder/subscribe"})
    assert (await client.receive_json())["success"]
    return (await client.receive_json())["event"]


async def _call(client, **msg):
    await client.send_json_auto_id(msg)
    return await client.receive_json()


async def test_snapshot_describes_running_tasks(hass, hass_ws_client, make_entry):
    await make_entry(type_data("washer", duration_minutes=30), type_data("dryer"))
    await hass.services.async_call(DOMAIN, "start", {"type": "washer"}, blocking=True)
    await hass.services.async_call(DOMAIN, "start", {"type": "dryer"}, blocking=True)
    client = await hass_ws_client(hass)

    snap = await _snapshot(client)
    assert snap["ready"] is True
    assert snap["silence"] == {"mode": "off", "until": None}
    assert {t["key"] for t in snap["types"]} == {"washer", "dryer"}  # not the built-in ad hoc
    by_type = {t["type"]: t for t in snap["tasks"]}
    washer, dryer = by_type["washer"], by_type["dryer"]
    assert washer["status"] == "armed" and washer["due_at"] is not None
    assert dryer["status"] == "notifying" and dryer["level"] == 1
    assert dryer["snooze_next"] == 10 and dryer["snooze_total"] == 3
    assert dryer["dismissable"] is False and dryer["keeps_going"] is False
    assert snap["history"] == []


async def test_snapshot_marks_ringing_tasks(hass, hass_ws_client, make_entry):
    await make_entry(type_data("alarm", ring=True), type_data("quiet"))
    await hass.services.async_call(DOMAIN, "start", {"type": "alarm"}, blocking=True)
    await hass.services.async_call(DOMAIN, "start", {"type": "quiet"}, blocking=True)
    client = await hass_ws_client(hass)
    by_type = {t["type"]: t for t in (await _snapshot(client))["tasks"]}
    assert by_type["alarm"]["ringing"] is True
    assert by_type["quiet"]["ringing"] is False

    await hass.services.async_call(DOMAIN, "snooze", {"type": "alarm"}, blocking=True)
    update = (await client.receive_json())["event"]
    assert {t["type"]: t["ringing"] for t in update["tasks"]}["alarm"] is False


async def test_snapshot_says_which_room_you_are_in(hass, hass_ws_client, make_entry):
    from .conftest import room_data

    hass.states.async_set("binary_sensor.motion_office", "on")
    await make_entry(
        type_data("washer"), room_data("office", ["binary_sensor.motion_office"], "alexa_office")
    )
    client = await hass_ws_client(hass)
    assert (await _snapshot(client))["room"] == "Office"


async def test_snapshot_without_rooms_has_no_room(hass, hass_ws_client, make_entry):
    await make_entry(type_data("washer"))
    client = await hass_ws_client(hass)
    assert (await _snapshot(client))["room"] is None


async def test_subscription_pushes_updates(hass, hass_ws_client, make_entry):
    await make_entry(type_data("washer"))
    client = await hass_ws_client(hass)
    snap = await _snapshot(client)
    assert snap["tasks"] == []

    await hass.services.async_call(DOMAIN, "start", {"type": "washer"}, blocking=True)
    update = (await client.receive_json())["event"]
    assert [t["type"] for t in update["tasks"]] == ["washer"]


async def test_actions_over_websocket(hass, hass_ws_client, notify, make_entry):
    entry = await make_entry(type_data("washer"), type_data("trash", dismissable=True))
    client = await hass_ws_client(hass)
    for t in ("washer", "trash"):
        res = await _call(client, type="task_reminder/start", task_type=t)
        assert res["success"] and res["result"]["task_id"]

    tasks = {t.type_key: t for t in entry.runtime_data.tasks.values()}
    assert (await _call(client, type="task_reminder/snooze", task_id=tasks["washer"].id))["success"]
    assert tasks["washer"].status == "snoozed"

    bad = await _call(client, type="task_reminder/dismiss", task_id=tasks["washer"].id)
    assert bad["success"] is False and "cannot be dismissed" in bad["error"]["message"]
    assert (await _call(client, type="task_reminder/dismiss", task_id=tasks["trash"].id))["success"]
    assert (await _call(client, type="task_reminder/done", task_id=tasks["washer"].id))["success"]
    assert entry.runtime_data.tasks == {}

    missing = await _call(client, type="task_reminder/done", task_id="nope")
    assert missing["success"] is False


async def test_quick_reminder_over_websocket(hass, hass_ws_client, freezer, notify, make_entry):
    entry = await make_entry()
    client = await hass_ws_client(hass)
    res = await _call(client, type="task_reminder/remind", title="Egg timer", minutes=7)
    assert res["success"]
    task = entry.runtime_data.tasks[res["result"]["task_id"]]
    assert task.title == "Egg timer" and task.status == "armed"

    res = await _call(client, type="task_reminder/remind", title="  Now  ")
    assert res["success"]
    assert entry.runtime_data.tasks[res["result"]["task_id"]].title == "Now"
    assert len(notify["phone"]) == 1  # the immediate one

    await advance(hass, freezer, minutes=7)
    assert task.status == "notifying"

    empty = await _call(client, type="task_reminder/remind", title="")
    assert empty["success"] is False


async def test_cancel_only_before_due_and_without_side_effects(
    hass, hass_ws_client, notify, make_entry
):
    entry = await make_entry(
        type_data("washer", duration_minutes=45, then_start="dryer"), type_data("dryer")
    )
    client = await hass_ws_client(hass)
    first = (await _call(client, type="task_reminder/start", task_type="washer"))["result"][
        "task_id"
    ]

    assert (await _call(client, type="task_reminder/cancel", task_id=first))["success"]
    assert entry.runtime_data.tasks == {}  # and the dryer was NOT started
    assert entry.runtime_data.history[0]["outcome"] == "cancelled"

    due = (await _call(client, type="task_reminder/start", task_type="dryer"))["result"]["task_id"]
    refused = await _call(client, type="task_reminder/cancel", task_id=due)
    assert refused["success"] is False and "already due" in refused["error"]["message"]


async def test_silence_over_websocket(hass, hass_ws_client, make_entry):
    entry = await make_entry()
    client = await hass_ws_client(hass)
    until = "2026-10-09T15:00:00+00:00"
    assert (await _call(client, type="task_reminder/silence", mode="silent", until=until))[
        "success"
    ]
    assert entry.runtime_data.silence.mode == "silent"

    no_end = await _call(client, type="task_reminder/silence", mode="silent")
    assert no_end["success"] is False  # an end time is mandatory

    watcher = await hass_ws_client(hass)
    snap = await _snapshot(watcher)
    assert snap["silence"] == {"mode": "silent", "until": until}

    assert (await _call(client, type="task_reminder/silence", mode="off"))["success"]
    assert entry.runtime_data.silence.mode == "off"


async def test_history_keeps_the_last_finished_and_survives_restart(hass, make_entry):
    entry = await make_entry(type_data("washer"))
    for _ in range(12):
        await hass.services.async_call(DOMAIN, "start", {"type": "washer"}, blocking=True)
        await hass.services.async_call(DOMAIN, "done", {"type": "washer"}, blocking=True)
    assert len(entry.runtime_data.history) == 10
    assert entry.runtime_data.history[0]["outcome"] == "done"

    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert len(entry.runtime_data.history) == 10


async def test_snapshot_lists_upcoming_collections(hass, hass_ws_client, make_entry):
    sensor = "sensor.almere_papier"
    hass.states.async_set(sensor, "Donderdag", {"Sort_date": 20261015, "Days_until": 6})
    await make_entry(type_data("papier", schedule_entity=sensor, due_time="19:00:00"))
    client = await hass_ws_client(hass)
    snap = await _snapshot(client)
    assert snap["upcoming"] == [
        {
            "type": "papier",
            "name": "Papier",
            "collection": "2026-10-15",
            "starts_on": "2026-10-14",  # the day before
            "due_time": "19:00",
        }
    ]
    assert snap["tasks"] == []


async def test_upcoming_hides_collections_that_already_have_a_task(
    hass, hass_ws_client, make_entry
):
    sensor = "sensor.almere_papier"
    hass.states.async_set(sensor, "x", {"Sort_date": 20261013, "Days_until": 1})
    await make_entry(type_data("papier", schedule_entity=sensor))
    client = await hass_ws_client(hass)
    snap = await _snapshot(client)
    assert [t["type"] for t in snap["tasks"]] == ["papier"]  # started by the schedule
    assert snap["upcoming"] == []


async def test_panel_file_is_shipped():
    www = Path(__file__).parent.parent / "custom_components" / "task_reminder" / "www"
    assert (www / "task-reminder-panel.js").read_text().count("task_reminder/subscribe") == 1
