#!/bin/bash -p
set -euo pipefail

# Privileged Bash mode ignores startup files and imported shell functions. The
# fixed env/python paths then start the actual installer with only the values
# required for the user's desktop session and documented proxy support.
actual_home=$(/usr/bin/getent passwd "$(/usr/bin/id -u)" | /usr/bin/cut -d: -f6)
[[ -n "$actual_home" && "$actual_home" == /* ]] || { echo 'Could not determine the desktop home directory.' >&2; exit 1; }
exec /usr/bin/env -i \
    HOME="$actual_home" \
    PATH=/usr/bin:/bin \
    LANG=C LC_ALL=C \
    XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$actual_home/.config}" \
    XDG_DATA_HOME="${XDG_DATA_HOME:-$actual_home/.local/share}" \
    XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-}" \
    DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-}" \
    DISPLAY="${DISPLAY:-}" \
    HYPRLAND_INSTANCE_SIGNATURE="${HYPRLAND_INSTANCE_SIGNATURE:-}" \
    WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-}" \
    XAUTHORITY="${XAUTHORITY:-}" \
    HTTP_PROXY="${HTTP_PROXY:-}" HTTPS_PROXY="${HTTPS_PROXY:-}" NO_PROXY="${NO_PROXY:-}" \
    /usr/bin/python3 -I "$(cd -- "${BASH_SOURCE[0]%/*}/.." && pwd -P)/scripts/install.py" "$@"
