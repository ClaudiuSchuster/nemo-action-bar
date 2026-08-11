#!/usr/bin/env python3
"""Minimal validation smoke test for the shipped configuration."""

import copy
import json
import warnings
from pathlib import Path

import nemo_action_bar
from gi.repository import Gtk


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

# Nemo has multiple GtkActions named Copy. File actions must win over an
# unrelated text/clipboard action even when that proxy is discovered first.
with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    clipboard_group = Gtk.ActionGroup(name="ClipboardActions")
    clipboard_copy = Gtk.Action(
        name="Copy", label="Copy", tooltip=None, stock_id=None
    )
    clipboard_group.add_action(clipboard_copy)
    file_group = Gtk.ActionGroup(name="DirViewActions")
    file_copy = Gtk.Action(name="Copy", label="Copy", tooltip=None, stock_id=None)
    file_group.add_action(file_copy)
assert nemo_action_bar._prefer_action_groups(
    [clipboard_copy, file_copy], nemo_action_bar.NEMO_FILE_ACTION_GROUPS
) == [file_copy]
assert nemo_action_bar._prefer_action_groups(
    [clipboard_copy], nemo_action_bar.NEMO_FILE_ACTION_GROUPS
) == [clipboard_copy]

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    activated = []
    file_copy.set_sensitive(False)
    file_copy.connect("activate", lambda _action: activated.append(True))
    nemo_action_bar._activate_with_current_selection(file_copy)
    assert activated == [True]
    assert not file_copy.get_sensitive()
assert nemo_action_bar.FORCE_LAZY_ACTIONS == {"undo", "redo"}

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
