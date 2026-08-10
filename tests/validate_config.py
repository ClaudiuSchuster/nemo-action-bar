#!/usr/bin/env python3
"""Minimal validation smoke test for the shipped configuration."""

import json
from pathlib import Path

import nemo_action_bar


ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "buttons.json").read_text(encoding="utf-8"))
validated = nemo_action_bar.validate_config(CONFIG)

assert [
    entry.get("id") for entry in validated["buttons"] if entry["type"] == "button"
] == ["cut", "copy", "paste", "rename", "trash"]
assert next(
    entry for entry in validated["buttons"] if entry.get("id") == "rename"
)["shortcut"] == "F2"
