#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
stage_dir="$(mktemp -d)"
trap 'rm -rf -- "$stage_dir"' EXIT
install -m 644 "$project_dir/manifest.json" "$project_dir/BarWidget.qml" "$stage_dir/"
omarchy plugin validate "$stage_dir"
echo "Omarchy-Manifest gültig."
