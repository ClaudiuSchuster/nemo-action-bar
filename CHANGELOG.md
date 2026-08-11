# Changelog

## 1.1.0 — 2026-08-11

- Keep root, favorite and archive actions available but hide them by default.
- Add a real-window README screenshot of the 14-button default layout while
  retaining the complete 18-action examples.
- Fix **Copy paths** incorrectly reporting an empty selection by resolving
  Nemo's current `DirViewActions/Copy` action instead of an unrelated GTK
  clipboard action.
- Traverse Nemo's widget/action tree without dropping submenu branches when
  short-lived Python wrapper IDs are reused.
- Handle Nemo's lazily refreshed action sensitivity while keeping selection
  checks and confirmation dialogs under Nemo's control.

## 1.0.0 — 2026-08-11

- Add a declaratively configured, live-reloading Nemo action bar.
- Provide Cut, Copy, Paste, Rename and Move to Trash defaults.
- Validate all configuration and limit actions to GTK accelerators.
