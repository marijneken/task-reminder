"""The panel must format dates and times the way the user's Home Assistant profile says,
not the way the browser defaults (a US browser must not force "11:05 PM")."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

PANEL = (
    Path(__file__).parent.parent
    / "custom_components"
    / "task_reminder"
    / "www"
    / "task-reminder-panel.js"
)

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

SCRIPT = r"""
const vm = require("vm"), fs = require("fs");
const NOW = Date.parse("2026-10-09T12:00:00Z");
class FixedDate extends Date {
  constructor(...a) { a.length ? super(...a) : super(NOW); }
  static now() { return NOW; }
}
const ctx = vm.createContext({
  Date: FixedDate, Intl, JSON, Object, Math, Number, String, RegExp, console,
  HTMLElement: class {}, customElements: { get: () => true, define() {} },
  setInterval() {}, clearInterval() {}, setTimeout() {}, clearTimeout() {},
});
vm.runInContext(fs.readFileSync(process.argv[1], "utf8") + "\n;globalThis.__make = makeFormatters;", ctx);
const cases = JSON.parse(process.argv[2]);
const out = cases.map((c) => {
  const f = ctx.__make({ locale: c.locale, language: c.locale.language, config: { time_zone: c.server_tz } });
  return { time: f.time(c.iso), day: f.day(c.day), tod: f.timeOfDay(c.tod) };
});
console.log(JSON.stringify(out));
"""

EVENING = "2026-10-09T21:05:00Z"  # 23:05 in Amsterdam (CEST), 17:05 in New York (EDT)
NEXT_MORNING = "2026-10-10T05:00:00Z"  # 07:00 the next day in Amsterdam


def run(cases, tz="America/New_York"):
    result = subprocess.run(
        ["node", "-e", SCRIPT, str(PANEL), json.dumps(cases)],
        capture_output=True,
        text=True,
        env={"TZ": tz, "PATH": "/usr/bin:/bin:/usr/local/bin"},
        check=True,
    )
    return json.loads(result.stdout)


def case(**kw):
    locale = {
        "language": "en",
        "time_format": "language",
        "time_zone": "server",
        "date_format": "language",
    }
    locale.update(kw.pop("locale", {}))
    return {
        "locale": locale,
        "server_tz": "Europe/Amsterdam",
        "iso": EVENING,
        "day": "2026-10-15",
        "tod": "19:00",
        **kw,
    }


def test_twelve_and_twenty_four_hour_follow_the_profile_not_the_browser():
    us, h24 = run([case(locale={"time_format": "12"}), case(locale={"time_format": "24"})])
    assert us["time"] == "11:05 PM" and us["tod"] == "7:00 PM"
    assert h24["time"] == "23:05" and h24["tod"] == "19:00"


def test_language_decides_when_the_profile_says_language():
    en_us, en_gb, nl = run(
        [
            case(locale={"language": "en-US"}),
            case(locale={"language": "en-GB"}),
            case(locale={"language": "nl"}),
        ]
    )
    assert en_us["time"] == "11:05 PM"
    assert en_gb["time"] == "23:05"
    assert nl["time"] == "23:05"


def test_time_zone_local_versus_server():
    local, server = run(
        [
            case(locale={"time_format": "24", "time_zone": "local"}),
            case(locale={"time_format": "24"}),
        ]
    )
    assert local["time"] == "17:05"  # the browser's zone (New York)
    assert server["time"] == "23:05"  # the Home Assistant server's zone (Amsterdam)


def test_other_days_are_named_and_tomorrow_is_a_word():
    (item,) = run([case(locale={"time_format": "24"}, iso=NEXT_MORNING)])
    assert item["time"] == "tomorrow 07:00"


def test_date_order_follows_the_date_format_setting():
    dmy, mdy, nl = run(
        [
            case(locale={"date_format": "DMY"}),
            case(locale={"date_format": "MDY"}),
            case(locale={"language": "nl"}),
        ]
    )
    assert dmy["day"] == "Thu 15 Oct"
    assert mdy["day"] == "Thu, Oct 15"
    assert nl["day"] == "do 15 okt"  # weekday and month names follow the language


def test_dates_without_a_time_do_not_shift_with_the_time_zone():
    for tz in ("Pacific/Auckland", "America/Los_Angeles"):
        (item,) = run([case(locale={"time_zone": "local", "date_format": "DMY"})], tz=tz)
        assert item["day"] == "Thu 15 Oct"
