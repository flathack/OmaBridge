#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
data_dir="${XDG_DATA_HOME:-$HOME/.local/share}/omabridge"
config_dir="${XDG_CONFIG_HOME:-$HOME/.config}"
bin_dir="$HOME/.local/bin"
plugin_dir="$config_dir/omarchy/plugins/io.github.flathack.omabridge"

command -v python3 >/dev/null || { echo "Python 3.11+ is required." >&2; exit 1; }
command -v omarchy >/dev/null || { echo "The Omarchy Shell is required." >&2; exit 1; }
stage_dir="$(mktemp -d)"
trap 'rm -rf -- "$stage_dir"' EXIT
install -m 644 "$project_dir/manifest.json" "$project_dir/BarWidget.qml" "$stage_dir/"
omarchy plugin validate "$stage_dir"
mkdir -p "$data_dir" "$bin_dir" "$plugin_dir" "${XDG_DATA_HOME:-$HOME/.local/share}/applications" "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"
python3 -m venv "$data_dir/venv"
"$data_dir/venv/bin/python" -m pip install "$project_dir"
# Write a properly quoted launcher without putting credentials into argv.
"$data_dir/venv/bin/python" - "$data_dir" "$bin_dir" <<'PY'
import pathlib, shlex, sys
data, binary = map(pathlib.Path, sys.argv[1:])
launcher = binary / "omabridge"
launcher.write_text("#!/bin/sh\nexec " + shlex.quote(str(data / "venv/bin/omabridge")) + ' "$@"\n')
launcher.chmod(0o755)
PY
install -m 644 "$project_dir/manifest.json" "$project_dir/BarWidget.qml" "$plugin_dir/"
install -m 644 "$project_dir/src/omabridge/assets/omabridge.svg" "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps/omabridge.svg"
"$data_dir/venv/bin/python" - "$bin_dir/omabridge" "${XDG_DATA_HOME:-$HOME/.local/share}/applications/omabridge.desktop" <<'PY'
import pathlib, sys
executable = sys.argv[1].replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%')
pathlib.Path(sys.argv[2]).write_text('[Desktop Entry]\nType=Application\nName=OmaBridge\nComment=Citrix sites for Omarchy\nComment[de]=Citrix-Sites für Omarchy\nExec="' + executable + '"\nIcon=omabridge\nTerminal=false\nCategories=Network;RemoteAccess;\nStartupWMClass=omabridge\n')
PY
if [ -f "$config_dir/omarchy/shell.json" ]; then
    cp -p "$config_dir/omarchy/shell.json" "$data_dir/shell.json.backup.$(date +%Y%m%d-%H%M%S)"
fi
"$data_dir/venv/bin/python" "$project_dir/scripts/migrate-plugin.py" "$config_dir" "$data_dir"
omarchy-shell shell rescanPlugins
# Plugin discovery is asynchronous after rescanPlugins.
for attempt in {1..25}; do
    if enable_result=$(omarchy plugin enable io.github.flathack.omabridge 2>&1); then
        echo "$enable_result"
        break
    fi
    if [[ $enable_result != *"is not known"* || $attempt == 25 ]]; then
        echo "$enable_result" >&2
        exit 1
    fi
    sleep 0.2
done
echo "OmaBridge installed. Click Citrix in the bar to add a site."
