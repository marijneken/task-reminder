"""Things hassfest checks that unit tests would otherwise not notice."""

import json
from pathlib import Path

COMPONENT = Path(__file__).parent.parent / "custom_components" / "task_reminder"


def test_manifest_keys_are_sorted_the_way_hassfest_wants():
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    keys = list(manifest)
    assert keys[:2] == ["domain", "name"]
    assert keys[2:] == sorted(keys[2:])


def test_manifest_lists_are_sorted():
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    for key in ("dependencies", "after_dependencies", "codeowners", "requirements"):
        assert manifest.get(key, []) == sorted(manifest.get(key, []))


def test_translations_have_no_html_characters():
    for name in ("translations/en.json", "services.yaml"):
        text = (COMPONENT / name).read_text()
        assert "<" not in text and ">" not in text, f"{name} must not contain < or >"
