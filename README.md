# Reel — MakeMKV GUI for Linux

A full-featured GTK4 + libadwaita front-end for [MakeMKV](https://www.makemkv.com/) on Linux.
Built with Python 3.11+ and PyGObject, following the GNOME Human Interface Guidelines.

Copyright © 2026 MLS Tidbits — GPL-3.0-or-later

---

## Features

- **Disc Ripping** — detect drives, browse titles, select what to rip, track progress with title name display
- **Select / Deselect All** — button toggles between "Select All" and "Deselect All" as titles are checked
- **Backup** — full disc backup with optional decryption and integrity verification
- **Log Viewer** — colour-coded, searchable, saveable output from `makemkvcon`
- **Preferences** — persistent settings written to `~/.MakeMKV/settings.conf` and `~/.config/ripper/settings.json`
  - Expert Mode toggle reveals the Default Profile selector (Default, AAC-stereo, FLAC, WDTV)
- Native GNOME look via `libadwaita` — respects dark/light mode and accent colours
- Missing `makemkvcon` binary detected at launch with an actionable alert dialog

---

## Requirements

### Debian / Ubuntu

```bash
sudo apt install \
  python3 \
  python3-gi \
  python3-gi-cairo \
  gir1.2-gtk-4.0 \
  gir1.2-adw-1 \
  makemkv-bin \
  makemkv-oss
```

**Note:** `makemkv-bin` and `makemkv-oss` are not in the official repos.
Install via the MakeMKV PPA:
>
```bash
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/MLSTidbits.gpg] https://archive.mlstidbits.com/ stable main" | sudo tee /etc/apt/sources.list.d/MLSTidbits.list
wget -qO - https://archive.mlstidbits.com/key/MLSTidbits.gpg | sudo dd of=/usr/share/keyrings/MLSTidbits.gpg

sudo apt update
sudo apt install makemkv-bin ripper-gtk
```


### Fedora

```bash
sudo dnf install python3-gobject gtk4 libadwaita
```

### Arch Linux

```bash
sudo pacman -S python-gobject gtk4 libadwaita
```

---

## Running (development)

```bash
git clone https://github.com/your-org/makemkv-gui
cd makemkv-gui
chmod +x run.sh
./run.sh
```

---

## Installation

Copy Python modules and data files to the expected locations:

```bash
# Python modules
sudo mkdir -p /usr/lib/ripper
sudo cp -r src/ui   /usr/lib/ripper/ui
sudo cp -r src/core /usr/lib/ripper/core

# UI and data files
sudo mkdir -p /usr/share/ripper/ui
sudo cp data/ui/*.ui /usr/share/ripper/ui/
sudo mkdir -p /usr/share/doc/ripper
sudo cp doc/version  /usr/share/doc/ripper/version
sudo cp README.md    /usr/share/doc/ripper/

# Launcher script
sudo cp src/main.py /usr/bin/ripper
sudo chmod +x /usr/bin/ripper

# Desktop entry
sudo cp data/makemkv-gui.desktop /usr/share/applications/
sudo update-desktop-database /usr/share/applications/
```

## Architecture

```text
┌─────────────────────────────────────────┐
│          Adw.ApplicationWindow          │
│  ┌──────────────┐  ┌───────────────────┐│
│  │ Sidebar nav  │  │  Content stack    ││
│  │              │  │  ┌─────────────┐  ││
│  │ • Rip Disc   │  │  │  DiscView   │  ││
│  │ • Backup     │  │  │  BackupView │  ││
│  │ • Logs       │  │  │  LogView    │  ││
│  └──────────────┘  │  └─────────────┘  ││
│                    └───────────────────┘│
└─────────────────────────────────────────┘
              │ GObject signals
              ▼
   MakeMKVController  (GObject)
              │ subprocess + threads
              ▼
     makemkvcon  (system binary)
```

- All subprocess calls run on daemon threads
- Results marshalled back to the GTK main thread via `GLib.idle_add()`
- All static UI structure (labels, icons, layout) lives in `.ui` XML files
- Python handles only dynamic behaviour: signals, state, subprocess management
- `GtkBuilder` XML loaded at runtime — all app strings editable without touching Python

---

## UI File Conventions

All view classes load their layout from a corresponding `.ui` file via `Gtk.Builder`.
Static text (labels, tooltips, page titles, menu items) lives exclusively in the XML.
Python only wires signals and updates dynamic content (drive names, progress, log lines).

The window title, default size, about dialog strings, and copyright notice are all
set in `data/ui/main_window.ui` — no hardcoded strings in Python.

---

## License

GPL-3.0-or-later — see `LICENSE`.
MakeMKV is © 2007–2024 GuinpinSoft inc. This project is an independent front-end
and is not affiliated with or endorsed by GuinpinSoft inc.
