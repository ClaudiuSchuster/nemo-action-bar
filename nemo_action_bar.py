# SPDX-License-Identifier: GPL-2.0-or-later
"""A small, declaratively configured action bar for Nemo.

Nemo's public extension API cannot add buttons to its built-in toolbar.  A
LocationWidgetProvider is therefore used to place a native GTK bar directly
above the directory view.  Buttons activate a small allowlist of Nemo's own
GtkActions (with keyboard accelerators as compatibility fallbacks), so
selection handling, confirmation dialogs and file operations stay inside Nemo.
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
gi.require_version("Atk", "1.0")
gi.require_version("Nemo", "3.0")

from gi.repository import Atk, Gdk, Gio, GLib, GObject, Gtk, Nemo


CONFIG_PATH = Path(
    os.environ.get(
        "NEMO_ACTION_BAR_CONFIG",
        str(Path.home() / ".config" / "nemo-action-bar" / "buttons.json"),
    )
)
DATA_ROOT = Path(
    os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
)
ICON_SEARCH_PATHS = (
    Path(__file__).resolve().parent / "icons",
    DATA_ROOT / "nemo-action-bar" / "icons",
)

# Public, stable identifiers accepted by buttons.json.  The GtkAction names are
# Nemo's internal names, not user-controlled command lines.  Multiple names let
# a single toolbar button follow stateful actions such as Favorite/Unfavorite.
ACTION_DEFINITIONS: dict[str, dict[str, Any]] = {
    "new-folder": {"names": ("New Folder",), "shortcut": "<Control><Shift>n"},
    "cut": {"names": ("Cut",), "shortcut": "<Control>x"},
    "copy": {"names": ("Copy",), "shortcut": "<Control>c"},
    "paste": {"names": ("Paste",), "shortcut": "<Control>v"},
    "duplicate": {"names": ("Duplicate",)},
    "rename": {"names": ("Rename",), "shortcut": "F2"},
    "undo": {"names": ("Undo",), "shortcut": "<Control>z"},
    "redo": {"names": ("Redo",), "shortcut": "<Control>y"},
    "properties": {"names": ("Properties",), "shortcut": "<Alt>Return"},
    "select-all": {"names": ("Select All",), "shortcut": "<Control>a"},
    "show-hidden": {
        "names": ("Show Hidden Files",),
        "shortcut": "<Control>h",
    },
    "trash": {"names": ("Trash",), "shortcut": "Delete"},
    "open-terminal": {
        "names": ("OpenInTerminal",),
        "shortcut": "<Shift>F4",
    },
    "open-admin": {"names": ("OpenAsRoot",)},
    "favorite-toggle": {"names": ("Favorite File", "Unfavorite File")},
    "archive-create": {"names": ("NemoFr::add",), "requires": "nemo-fileroller"},
    "archive-extract": {
        "names": ("NemoFr::extract_here",),
        "requires": "nemo-fileroller",
    },
    "copy-path": {"handler": "copy-path"},
}

DEFAULT_CONFIG: dict[str, Any] = {
    "version": 1,
    "appearance": {
        "alignment": "end",
        "icon-size": 16,
        "show-labels": False,
        "spacing": 2,
    },
    "buttons": [
        {
            "id": "new-folder",
            "label": "Neuer Ordner",
            "icon": "folder-new-symbolic",
            "action": "new-folder",
        },
        {"type": "separator"},
        {
            "id": "cut",
            "label": "Ausschneiden",
            "icon": "edit-cut-symbolic",
            "action": "cut",
        },
        {
            "id": "copy",
            "label": "Kopieren",
            "icon": "edit-copy-symbolic",
            "action": "copy",
        },
        {
            "id": "paste",
            "label": "Einfügen",
            "icon": "edit-paste-symbolic",
            "action": "paste",
        },
        {
            "id": "duplicate",
            "label": "Duplizieren",
            "icon": "nemo-action-bar-duplicate-symbolic",
            "action": "duplicate",
        },
        {
            "id": "rename",
            "label": "Umbenennen",
            "icon": "document-edit-symbolic",
            "action": "rename",
        },
        {"type": "separator"},
        {
            "id": "undo",
            "label": "Rückgängig",
            "icon": "edit-undo-symbolic",
            "action": "undo",
        },
        {
            "id": "redo",
            "label": "Wiederholen",
            "icon": "edit-redo-symbolic",
            "action": "redo",
        },
        {"type": "separator"},
        {
            "id": "properties",
            "label": "Eigenschaften",
            "icon": "document-properties-symbolic",
            "action": "properties",
        },
        {
            "id": "select-all",
            "label": "Alles auswählen",
            "icon": "edit-select-all-symbolic",
            "action": "select-all",
        },
        {
            "id": "show-hidden",
            "label": "Verborgene Dateien umschalten",
            "icon": "view-reveal-symbolic",
            "action": "show-hidden",
        },
        {"type": "separator"},
        {
            "id": "copy-path",
            "label": "Pfade kopieren",
            "icon": "insert-link-symbolic",
            "action": "copy-path",
        },
        {
            "id": "open-terminal",
            "label": "Im Terminal öffnen",
            "icon": "utilities-terminal-symbolic",
            "action": "open-terminal",
        },
        {
            "id": "open-admin",
            "label": "Als Administrator öffnen",
            "icon": "dialog-password-symbolic",
            "action": "open-admin",
        },
        {
            "id": "favorite",
            "label": "Favorit umschalten",
            "icon": "xsi-favorite-symbolic",
            "action": "favorite-toggle",
        },
        {
            "id": "archive-create",
            "label": "Archiv erstellen",
            "icon": "xsi-add-files-to-archive-symbolic",
            "action": "archive-create",
        },
        {
            "id": "archive-extract",
            "label": "Archiv hier entpacken",
            "icon": "xsi-extract-archive-symbolic",
            "action": "archive-extract",
        },
        {"type": "separator"},
        {
            "id": "trash",
            "label": "In den Papierkorb verschieben",
            "icon": "user-trash-symbolic",
            "action": "trash",
        },
    ],
}

MAX_BUTTONS = 32
NEMO_FILE_ACTION_GROUPS = ("DirViewActions",)
# Nemo refreshes these states when its menus are updated. The action callbacks
# still consult the live undo manager, so activating a stale-insensitive proxy
# is safe and more reliable than synthesizing Ctrl+Z/Ctrl+Y.
FORCE_LAZY_ACTIONS = frozenset({"undo", "redo"})
MONITORED_EVENTS = {
    Gio.FileMonitorEvent.CHANGED,
    Gio.FileMonitorEvent.CHANGES_DONE_HINT,
    Gio.FileMonitorEvent.CREATED,
    Gio.FileMonitorEvent.DELETED,
    Gio.FileMonitorEvent.MOVED_IN,
    Gio.FileMonitorEvent.MOVED_OUT,
}


def _prefer_action_groups(
    actions: list[Gtk.Action], group_names: tuple[str, ...]
) -> list[Gtk.Action]:
    """Keep actions from Nemo's requested groups when they are available."""

    if not group_names:
        return actions

    preferred = []
    for action in actions:
        action_group = action.get_property("action-group")
        if action_group is not None and action_group.get_name() in group_names:
            preferred.append(action)
    return preferred or actions


def _activate_with_current_selection(action: Gtk.Action) -> None:
    """Activate a Nemo view action even when its lazy menu state is stale."""

    was_sensitive = action.get_sensitive()
    if not was_sensitive:
        action.set_sensitive(True)
    try:
        action.activate()
    finally:
        if not was_sensitive:
            action.set_sensitive(False)


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
        action = item.get("action")
        shortcut = item.get("shortcut")
        enabled = item.get("enabled", True)

        for field_name, value, maximum in (
            ("id", button_id, 64),
            ("label", label, 120),
            ("icon", icon, 160),
        ):
            if not isinstance(value, str) or not value.strip():
                _fail(f"buttons[{index}].{field_name} muss Text enthalten")
            if len(value) > maximum:
                _fail(f"buttons[{index}].{field_name} ist zu lang")
        if action is not None:
            if not isinstance(action, str) or action not in ACTION_DEFINITIONS:
                _fail(
                    f"buttons[{index}].action ist nicht unterstützt: {action!r}"
                )
        if shortcut is not None:
            if not isinstance(shortcut, str) or not shortcut.strip():
                _fail(f"buttons[{index}].shortcut muss Text enthalten")
            if len(shortcut) > 80:
                _fail(f"buttons[{index}].shortcut ist zu lang")
        if action is None and shortcut is None:
            _fail(f"buttons[{index}] benötigt action oder shortcut")
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
                "action": action,
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
        self._register_custom_icons()
        self.set_hexpand(True)
        self.get_style_context().add_class(Gtk.STYLE_CLASS_TOOLBAR)
        self.rebuild(config)

    @staticmethod
    def _register_custom_icons() -> None:
        theme = Gtk.IconTheme.get_default()
        if theme is None:
            return
        known_paths = set(theme.get_search_path())
        for path in ICON_SEARCH_PATHS:
            path_text = str(path)
            if path.is_dir() and path_text not in known_paths:
                theme.append_search_path(path_text)
                known_paths.add(path_text)

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
        controls.set_margin_top(1)
        controls.set_margin_bottom(1)

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
        button.get_accessible().set_name(spec["label"])

        image = Gtk.Image.new_from_icon_name(spec["icon"], Gtk.IconSize.BUTTON)
        image.set_pixel_size(appearance["icon-size"])
        if appearance["show-labels"]:
            content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
            content.pack_start(image, False, False, 0)
            content.pack_start(Gtk.Label(label=spec["label"]), False, False, 0)
            button.add(content)
        else:
            button.add(image)

        action_id = spec.get("action")
        definition = ACTION_DEFINITIONS.get(action_id, {})
        shortcut = spec.get("shortcut") or definition.get("shortcut")
        keyval = modifiers = None
        if shortcut:
            keyval, modifiers = Gtk.accelerator_parse(shortcut)
            if not keyval or not Gtk.accelerator_valid(keyval, modifiers):
                button.set_sensitive(False)
                button.set_tooltip_text(
                    f"{spec['label']} – ungültiges Kürzel: {shortcut}"
                )
                return button

        tooltip = spec["label"]
        if keyval:
            tooltip += f"  ({Gtk.accelerator_get_label(keyval, modifiers)})"
        if definition.get("requires"):
            tooltip += f"  [{definition['requires']}]"
        button.set_tooltip_text(tooltip)
        button.connect(
            "clicked",
            self._queue_activation,
            action_id,
            keyval,
            modifiers,
        )
        return button

    def _queue_activation(
        self,
        _button: Gtk.Button,
        action_id: str | None,
        keyval: int | None,
        modifiers: Gdk.ModifierType | None,
    ) -> None:
        GLib.idle_add(self._activate, action_id, keyval, modifiers)

    def _activate(
        self,
        action_id: str | None,
        keyval: int | None,
        modifiers: Gdk.ModifierType | None,
    ) -> bool:
        if action_id:
            definition = ACTION_DEFINITIONS[action_id]
            if definition.get("handler") == "copy-path":
                self._copy_selected_paths()
                return GLib.SOURCE_REMOVE

            action = self._find_nemo_action(
                definition["names"], NEMO_FILE_ACTION_GROUPS
            )
            if action is not None:
                if action.get_sensitive():
                    action.activate()
                    return GLib.SOURCE_REMOVE
                if action_id in FORCE_LAZY_ACTIONS:
                    _activate_with_current_selection(action)
                    return GLib.SOURCE_REMOVE
                if not keyval:
                    if (
                        action_id != "open-admin"
                        and self._focused_selection_count() == 0
                    ):
                        self._show_unavailable(
                            "Bitte zuerst mindestens eine Datei auswählen."
                        )
                        return GLib.SOURCE_REMOVE
                    _activate_with_current_selection(action)
                    return GLib.SOURCE_REMOVE

        if keyval and modifiers is not None:
            return self._activate_shortcut(keyval, modifiers)

        dependency = ACTION_DEFINITIONS.get(action_id, {}).get("requires")
        detail = f"Benötigtes Paket: {dependency}" if dependency else None
        self._show_unavailable("Diese Nemo-Aktion ist gerade nicht verfügbar.", detail)
        return GLib.SOURCE_REMOVE

    def _find_nemo_action(
        self,
        names: tuple[str, ...],
        preferred_groups: tuple[str, ...] = (),
    ) -> Gtk.Action | None:
        matches: dict[str, list[Gtk.Action]] = {name: [] for name in names}
        action_groups: list[Gtk.ActionGroup] = []
        for widget in self._walk_widgets(self._window):
            if not isinstance(widget, Gtk.Activatable):
                continue
            action = widget.get_related_action()
            if action is None:
                continue
            action_group = action.get_property("action-group")
            if action_group is not None and action_group not in action_groups:
                action_groups.append(action_group)
            name = action.get_name()
            if name in matches and action not in matches[name]:
                matches[name].append(action)

        # Several useful Nemo actions only have context-menu proxies.  Once any
        # proxy from their GtkActionGroup is known, query the group directly so
        # hidden menu preferences do not disable the toolbar button.
        for action_group in action_groups:
            for name in names:
                action = action_group.get_action(name)
                if action is not None and action not in matches[name]:
                    matches[name].append(action)

        ordered = [action for name in names for action in matches[name]]
        ordered = _prefer_action_groups(ordered, preferred_groups)
        for action in ordered:
            if action.get_visible() and action.get_sensitive():
                return action
        for action in ordered:
            if action.get_visible():
                return action
        return ordered[0] if ordered else None

    @staticmethod
    def _walk_widgets(root: Gtk.Widget):
        stack = [root]
        seen: set[Gtk.Widget] = set()
        while stack:
            widget = stack.pop()
            if widget in seen:
                continue
            seen.add(widget)
            yield widget

            if isinstance(widget, Gtk.MenuItem):
                submenu = widget.get_submenu()
                if submenu is not None:
                    stack.append(submenu)
            if isinstance(widget, Gtk.Container):
                stack.extend(widget.get_children())
            try:
                stack.extend(Gtk.Menu.get_for_attach_widget(widget))
            except (TypeError, RuntimeError):
                pass

    def _copy_selected_paths(self) -> None:
        if self._focused_selection_count() == 0:
            self._show_unavailable("Bitte zuerst mindestens eine Datei auswählen.")
            return

        action = self._find_nemo_action(("Copy",), NEMO_FILE_ACTION_GROUPS)
        if action is not None:
            # Nemo updates GtkAction sensitivity lazily with its Edit/context
            # menu. Its callback reads the live selection from NemoView.
            _activate_with_current_selection(action)
        else:
            # Some Nemo builds do not expose DirViewActions through their menu
            # proxies. The native Ctrl+C binding reaches the focused view and
            # produces the same URI clipboard payload.
            keyval, modifiers = Gtk.accelerator_parse(
                ACTION_DEFINITIONS["copy"]["shortcut"]
            )
            self._activate_shortcut(keyval, modifiers)

        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        uris = clipboard.wait_for_uris() or []
        if not uris:
            self._show_unavailable("Die ausgewählten Pfade konnten nicht gelesen werden.")
            return

        paths = []
        for uri in uris:
            file = Gio.File.new_for_uri(uri)
            paths.append(file.get_path() or file.get_parse_name())
        text = "\n".join(paths)
        clipboard.set_text(text, -1)
        clipboard.store()

    def _focused_selection_count(self) -> int | None:
        """Return the active file view's ATK selection count when available."""

        widget = self._window.get_focus()
        seen: set[Gtk.Widget] = set()
        while isinstance(widget, Gtk.Widget) and widget not in seen:
            seen.add(widget)
            accessible = widget.get_accessible()
            if isinstance(accessible, Atk.Selection):
                return accessible.get_selection_count()
            if widget is self._window:
                break
            widget = widget.get_parent()
        return None

    def _show_unavailable(self, message: str, detail: str | None = None) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self._window,
            modal=False,
            destroy_with_parent=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.CLOSE,
            text=message,
        )
        if detail:
            dialog.format_secondary_text(detail)
        dialog.connect("response", lambda current, _response: current.destroy())
        dialog.show()

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
