#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

data_root=${XDG_DATA_HOME:-"$HOME/.local/share"}
extension_file="$data_root/nemo-python/extensions/nemo_action_bar.py"

rm -f -- "$extension_file"
printf '%s\n' "Nemo Action Bar removed. Restart Nemo; user configuration was retained."
