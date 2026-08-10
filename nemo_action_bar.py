# SPDX-License-Identifier: GPL-2.0-or-later
"""A small, declaratively configured action bar for Nemo.

Nemo's public extension API cannot add buttons to its built-in toolbar.  A
LocationWidgetProvider is therefore used to place a native GTK bar directly
above the directory view.  Buttons activate Nemo's own keyboard accelerators,
so selection handling, confirmation dialogs and file operations stay inside
Nemo.
"""

from __future__ import annotations

import copy
import json
import os
import sys
import weakref
from pathlib import Path
from typing import Any

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Nemo", "3.0")

from gi.repository import Gdk, Gio, GLib, GObject, Gtk, Nemo


CONFIG_PATH = Path(
    os.environ.get(
        "NEMO_ACTION_BAR_CONFIG",
        str(Path.home() / ".config" / "nemo-action-bar" / "buttons.json"),
    )
)

DEFAULT_CONFIG: dict[str, Any] = {
    "version": 1,
    "appearance": {
        "alignment": "end",
        "icon-size": 20,
        "show-labels": False,
        "spacing": 2,
    },
    "buttons": [
        {
            "id": "cut",
            "label": "Ausschneiden",
            "icon": "edit-cut-symbolic",
            "shortcut": "<Control>x",
        },
        {
            "id": "copy",
            "label": "Kopieren",
            "icon": "edit-copy-symbolic",
            "shortcut": "<Control>c",
        },
        {
            "id": "paste",
            "label": "Einfügen",
            "icon": "edit-paste-symbolic",
            "shortcut": "<Control>v",
        },
        {
            "id": "rename",
            "label": "Umbenennen",
            "icon": "document-edit-symbolic",
            "shortcut": "F2",
        },
        {"type": "separator"},
        {
            "id": "trash",
            "label": "In den Papierkorb verschieben",
            "icon": "user-trash-symbolic",
            "shortcut": "Delete",
        },
    ],
}

MAX_BUTTONS = 32
MONITORED_EVENTS = {
    Gio.FileMonitorEvent.CHANGED,
    Gio.FileMonitorEvent.CHANGES_DONE_HINT,
    Gio.FileMonitorEvent.CREATED,
    Gio.FileMonitorEvent.DELETED,
    Gio.FileMonitorEvent.MOVED_IN,
    Gio.FileMonitorEvent.MOVED_OUT,
}


def _fail(message: str) -> None:
    raise ValueError(message)


def _bounded_int(value: Any, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(f"{name} muss eine ganze Zahl sein")
    if not minimum <= value <= maximum:
        _fail(f"{name} muss zwischen {minimum} und {maximum} liegen")
    return value


def validate_config(raw: Any) -> dict[str, Any]:
    """Validate and normalize a version-1 action-bar configuration."""

    if not isinstance(raw, dict):
        _fail("Die oberste JSON-Struktur muss ein Objekt sein")
    if raw.get("version", 1) != 1:
        _fail("Nur Konfigurationsversion 1 wird unterstützt")

    appearance_raw = raw.get("appearance", {})
    if not isinstance(appearance_raw, dict):
        _fail("appearance muss ein Objekt sein")

    defaults = DEFAULT_CONFIG["appearance"]
    alignment = appearance_raw.get("alignment", defaults["alignment"])
    if alignment not in {"start", "center", "end"}:
        _fail("appearance.alignment muss start, center oder end sein")

    appearance = {
        "alignment": alignment,
        "icon-size": _bounded_int(
            appearance_raw.get("icon-size", defaults["icon-size"]),
            "appearance.icon-size",
            12,
            64,
        ),
        "show-labels": appearance_raw.get(
            "show-labels", defaults["show-labels"]
        ),
        "spacing": _bounded_int(
            appearance_raw.get("spacing", defaults["spacing"]),
            "appearance.spacing",
            0,
            24,
        ),
    }
    if not isinstance(appearance["show-labels"], bool):
        _fail("appearance.show-labels muss true oder false sein")

    buttons_raw = raw.get("buttons", DEFAULT_CONFIG["buttons"])
    if not isinstance(buttons_raw, list):
        _fail("buttons muss eine Liste sein")
    if len(buttons_raw) > MAX_BUTTONS:
        _fail(f"Es sind höchstens {MAX_BUTTONS} Einträge erlaubt")

    buttons: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(buttons_raw):
        if not isinstance(item, dict):
            _fail(f"buttons[{index}] muss ein Objekt sein")
        item_type = item.get("type", "button")
        if item_type == "separator":
            buttons.append({"type": "separator"})
            continue
        if item_type != "button":
            _fail(f"buttons[{index}].type muss button oder separator sein")

        button_id = item.get("id")
        label = item.get("label")
        icon = item.get("icon")
        shortcut = item.get("shortcut")
        enabled = item.get("enabled", True)

        for field_name, value, maximum in (
            ("id", button_id, 64),
            ("label", label, 120),
            ("icon", icon, 160),
            ("shortcut", shortcut, 80),
        ):
            if not isinstance(value, str) or not value.strip():
                _fail(f"buttons[{index}].{field_name} muss Text enthalten")
            if len(value) > maximum:
                _fail(f"buttons[{index}].{field_name} ist zu lang")
        if not isinstance(enabled, bool):
            _fail(f"buttons[{index}].enabled muss true oder false sein")
        if button_id in seen_ids:
            _fail(f"Doppelte Button-ID: {button_id}")
        seen_ids.add(button_id)

        buttons.append(
            {
                "type": "button",
                "id": button_id,
                "label": label,
                "icon": icon,
                "shortcut": shortcut,
                "enabled": enabled,
            }
        )

    return {"version": 1, "appearance": appearance, "buttons": buttons}


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    if not path.exists():
        return validate_config(copy.deepcopy(DEFAULT_CONFIG))
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Konfiguration kann nicht gelesen werden: {error}") from error
    return validate_config(raw)


class ActionBar(Gtk.Box):
    def __init__(self, window: Gtk.Window, config: dict[str, Any]) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self._window = window
        self.set_hexpand(True)
        self.get_style_context().add_class(Gtk.STYLE_CLASS_TOOLBAR)
        self.rebuild(config)

    def rebuild(self, config: dict[str, Any]) -> None:
        for child in self.get_children():
            self.remove(child)
            child.destroy()

        appearance = config["appearance"]
        controls = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=appearance["spacing"],
        )
        controls.set_margin_start(4)
        controls.set_margin_end(4)
        controls.set_margin_top(2)
        controls.set_margin_bottom(2)

        alignment = appearance["alignment"]
        if alignment == "start":
            self.pack_start(controls, False, False, 0)
        elif alignment == "center":
            self.pack_start(Gtk.Box(), True, True, 0)
            self.pack_start(controls, False, False, 0)
            self.pack_start(Gtk.Box(), True, True, 0)
        else:
            self.pack_end(controls, False, False, 0)

        for spec in config["buttons"]:
            if spec["type"] == "separator":
                separator = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
                separator.set_margin_start(3)
                separator.set_margin_end(3)
                controls.pack_start(separator, False, False, 0)
                continue
            if not spec["enabled"]:
                continue
            button = self._make_button(spec, appearance)
            controls.pack_start(button, False, False, 0)

        self.show_all()

    def _make_button(
        self, spec: dict[str, Any], appearance: dict[str, Any]
    ) -> Gtk.Button:
        button = Gtk.Button()
        button.set_relief(Gtk.ReliefStyle.NONE)
        button.set_can_focus(False)
        button.set_focus_on_click(False)
        button.get_style_context().add_class(Gtk.STYLE_CLASS_FLAT)

        image = Gtk.Image.new_from_icon_name(spec["icon"], Gtk.IconSize.BUTTON)
        image.set_pixel_size(appearance["icon-size"])
        if appearance["show-labels"]:
            content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
            content.pack_start(image, False, False, 0)
            content.pack_start(Gtk.Label(label=spec["label"]), False, False, 0)
            button.add(content)
        else:
            button.add(image)

        keyval, modifiers = Gtk.accelerator_parse(spec["shortcut"])
        if not keyval or not Gtk.accelerator_valid(keyval, modifiers):
            button.set_sensitive(False)
            button.set_tooltip_text(
                f"{spec['label']} – ungültiges Kürzel: {spec['shortcut']}"
            )
            return button

        shortcut_label = Gtk.accelerator_get_label(keyval, modifiers)
        button.set_tooltip_text(f"{spec['label']}  ({shortcut_label})")
        button.connect("clicked", self._queue_shortcut, keyval, modifiers)
        return button

    def _queue_shortcut(
        self,
        _button: Gtk.Button,
        keyval: int,
        modifiers: Gdk.ModifierType,
    ) -> None:
        GLib.idle_add(self._activate_shortcut, keyval, modifiers)

    def _activate_shortcut(
        self, keyval: int, modifiers: Gdk.ModifierType
    ) -> bool:
        if not self._window or not self._window.get_realized():
            return GLib.SOURCE_REMOVE

        activated = Gtk.accel_groups_activate(self._window, keyval, modifiers)
        if not activated:
            # Some Nemo shortcuts are GTK key bindings rather than entries in
            # an accelerator group. Gtk.Window.activate_key() requires the
            # concrete EventKey wrapper, not a generic Gdk.Event instance.
            event = Gdk.EventKey()
            event.type = Gdk.EventType.KEY_PRESS
            event.window = self._window.get_window()
            event.send_event = True
            event.time = Gtk.get_current_event_time()
            event.state = modifiers
            event.keyval = keyval
            event.hardware_keycode = 0
            event.group = 0
            self._window.activate_key(event)
        return GLib.SOURCE_REMOVE


class NemoActionBarProvider(GObject.GObject, Nemo.LocationWidgetProvider):
    def __init__(self) -> None:
        super().__init__()
        self._bars: list[weakref.ReferenceType[ActionBar]] = []
        self._reload_source = 0
        self._config = self._load_or_default()
        self._monitor = self._create_monitor()

    def get_widget(self, _uri: str, window: Gtk.Window) -> Gtk.Widget:
        bar = ActionBar(window, self._config)
        self._bars.append(weakref.ref(bar))
        return bar

    def _load_or_default(self) -> dict[str, Any]:
        try:
            return load_config()
        except ValueError as error:
            print(f"Nemo Action Bar: {error}; Standard wird verwendet", file=sys.stderr)
            return validate_config(copy.deepcopy(DEFAULT_CONFIG))

    def _create_monitor(self):
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            monitor = Gio.File.new_for_path(str(CONFIG_PATH.parent)).monitor_directory(
                Gio.FileMonitorFlags.NONE, None
            )
            monitor.connect("changed", self._on_config_changed)
            return monitor
        except GLib.Error as error:
            print(f"Nemo Action Bar: Live-Neuladen nicht verfügbar: {error}", file=sys.stderr)
            return None

    def _on_config_changed(
        self,
        _monitor,
        file: Gio.File,
        other_file: Gio.File | None,
        event_type: Gio.FileMonitorEvent,
    ) -> None:
        if event_type not in MONITORED_EVENTS:
            return
        names = {candidate.get_basename() for candidate in (file, other_file) if candidate}
        if CONFIG_PATH.name not in names:
            return
        if self._reload_source:
            GLib.source_remove(self._reload_source)
        self._reload_source = GLib.timeout_add(150, self._reload_config)

    def _reload_config(self) -> bool:
        self._reload_source = 0
        try:
            new_config = load_config()
        except ValueError as error:
            print(
                f"Nemo Action Bar: Änderung ignoriert, letzte gültige "
                f"Konfiguration bleibt aktiv: {error}",
                file=sys.stderr,
            )
            return GLib.SOURCE_REMOVE

        self._config = new_config
        live_bars: list[weakref.ReferenceType[ActionBar]] = []
        for reference in self._bars:
            bar = reference()
            if bar is not None:
                bar.rebuild(new_config)
                live_bars.append(reference)
        self._bars = live_bars
        return GLib.SOURCE_REMOVE
