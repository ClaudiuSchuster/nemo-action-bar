#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

project_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
data_root=${XDG_DATA_HOME:-"$HOME/.local/share"}
config_root=${XDG_CONFIG_HOME:-"$HOME/.config"}
extension_dir="$data_root/nemo-python/extensions"
config_dir="$config_root/nemo-action-bar"
icon_dir="$data_root/nemo-action-bar/icons"

mkdir -p "$extension_dir" "$config_dir" "$icon_dir"
install -m 0644 "$project_dir/nemo_action_bar.py" "$extension_dir/nemo_action_bar.py"
install -m 0644 "$project_dir/icons/nemo-action-bar-duplicate-symbolic.svg" \
    "$icon_dir/nemo-action-bar-duplicate-symbolic.svg"

if [ ! -e "$config_dir/buttons.json" ]; then
    install -m 0644 "$project_dir/buttons.json" "$config_dir/buttons.json"
fi

printf '%s\n' "Nemo Action Bar installed. Restart all Nemo windows to load it."
