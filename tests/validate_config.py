#!/usr/bin/env python3
"""Minimal validation smoke test for the shipped configuration."""

import copy
import json
from pathlib import Path

import nemo_action_bar


ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "buttons.json").read_text(encoding="utf-8"))
validated = nemo_action_bar.validate_config(CONFIG)
assert validated == nemo_action_bar.validate_config(
    copy.deepcopy(nemo_action_bar.DEFAULT_CONFIG)
)

assert [
    entry.get("id") for entry in validated["buttons"] if entry["type"] == "button"
] == [
    "new-folder",
    "cut",
    "copy",
    "paste",
    "duplicate",
    "rename",
    "undo",
    "redo",
    "properties",
    "select-all",
    "show-hidden",
    "copy-path",
    "open-terminal",
    "open-admin",
    "favorite",
    "archive-create",
    "archive-extract",
    "trash",
]
assert next(
    entry for entry in validated["buttons"] if entry.get("id") == "rename"
)["action"] == "rename"

# Existing shortcut-only user configurations remain valid.
legacy = copy.deepcopy(CONFIG)
legacy["buttons"] = [
    {
        "id": "legacy-copy",
        "label": "Copy",
        "icon": "edit-copy-symbolic",
        "shortcut": "<Control>c",
    }
]
assert nemo_action_bar.validate_config(legacy)["buttons"][0]["action"] is None

invalid = copy.deepcopy(legacy)
invalid["buttons"][0].pop("shortcut")
try:
    nemo_action_bar.validate_config(invalid)
except ValueError:
    pass
else:
    raise AssertionError("button without action or shortcut was accepted")

invalid = copy.deepcopy(legacy)
invalid["buttons"][0]["action"] = "run-arbitrary-command"
try:
    nemo_action_bar.validate_config(invalid)
except ValueError:
    pass
else:
    raise AssertionError("unsupported action was accepted")
