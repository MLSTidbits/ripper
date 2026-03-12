#!/usr/bin/env bash
# run.sh — Launch MakeMKV GUI from the source tree (development helper)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="${SCRIPT_DIR}/src"

# Ensure PyGObject is available
python3 -c "import gi" 2>/dev/null || {
    echo "ERROR: PyGObject (python3-gi) is not installed."
    echo "  Ubuntu/Debian:  sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1"
    echo "  Fedora:         sudo dnf install python3-gobject gtk4 libadwaita"
    echo "  Arch:           sudo pacman -S python-gobject gtk4 libadwaita"
    exit 1
}

export PYTHONPATH="${SRC}${PYTHONPATH:+:$PYTHONPATH}"
exec python3 "${SRC}/main.py" "$@"
