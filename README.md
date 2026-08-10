# Nemo Action Bar

A small, configurable action bar above Nemo's file view. The default layout
provides **Cut**, **Copy**, **Paste**, **Rename** and **Move to Trash** buttons.

![Nemo Action Bar with Cut, Copy, Paste, Rename and Trash buttons](docs/nemo-action-bar.png)

Nemo does not expose a public hook for third-party buttons in its built-in
toolbar. This extension therefore uses Nemo's supported Python
`LocationWidgetProvider` interface and places a native GTK bar immediately
above the directory view. Each button activates one of Nemo's own keyboard
shortcuts, so file selection, confirmation dialogs and file operations remain
under Nemo's control. No configurable shell commands are executed.

## Requirements and installation

- Nemo 5 or newer
- `nemo-python`
- GTK 3 Python introspection bindings

```bash
git clone https://github.com/ClaudiuSchuster/nemo-action-bar.git
cd nemo-action-bar
./install.sh
```

Then close every Nemo window and start Nemo again. Existing user configuration
is preserved during updates. To install a later version, run `git pull` in the
checkout followed by `./install.sh` again.

## Configuration

The default configuration is installed only when
`~/.config/nemo-action-bar/buttons.json` does not yet exist. Valid changes are
picked up live by open Nemo windows. A button consists of an ID, a label, an
installed GTK icon name and a valid GTK accelerator:

```json
{
  "id": "paste",
  "label": "Paste",
  "icon": "edit-paste-symbolic",
  "shortcut": "<Control>v"
}
```

Useful Nemo shortcuts include `<Control><Shift>n` for a new folder and
`<Control>z` for undo. Use `{ "type": "separator" }` for a separator or
`"enabled": false` to hide an entry temporarily.

## Uninstall

Run `./uninstall.sh`. The user configuration is deliberately retained and can
be removed separately if it is no longer needed. Restart Nemo afterwards.

## Cinnamon Spices status

This project is a Nemo Python UI extension, not a Cinnamon desktop extension
and not a declarative Nemo context-menu Action. It therefore does not fit the
Cinnamon Extensions or Cinnamon Actions download categories in their current
form. Community distribution can use this repository, a distro package, or an
upstream proposal to Nemo/nemo-extensions.

Licensed under GPL-2.0-or-later. See `LICENSE`.
