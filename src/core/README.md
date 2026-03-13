# Ripper

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

> **Note:** `makemkv-bin` and `makemkv-oss` are not in the official repos.
> Install via the MakeMKV PPA:
> ```bash
> sudo add-apt-repository ppa:heyarje/makemkv-beta
> sudo apt update
> sudo apt install makemkv-bin makemkv-oss
> ```
> Or download directly from [makemkv.com](https://www.makemkv.com/download/).

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
# Python modules  (/usr/lib — application code)
sudo mkdir -p /usr/lib/makemkv-gtk
sudo cp src/main.py   /usr/lib/makemkv-gtk/
sudo cp -r src/core   /usr/lib/makemkv-gtk/
sudo cp -r src/ui     /usr/lib/makemkv-gtk/

# GtkBuilder UI files  (/usr/share — architecture-independent data)
sudo mkdir -p /usr/share/makemkv-gtk/ui
sudo cp data/ui/*.ui  /usr/share/makemkv-gtk/ui/

# Documentation
sudo mkdir -p /usr/share/doc/makemkv-gtk
sudo cp doc/version   /usr/share/doc/makemkv-gtk/
sudo cp README.md     /usr/share/doc/makemkv-gtk/

# Launcher
sudo cp src/makemkv-gtk /usr/bin/makemkv-gtk
sudo chmod +x /usr/bin/makemkv-gtk

# Desktop integration
sudo cp data/makemkv-gtk.desktop /usr/share/applications/
sudo cp data/icons/ripper.svg \
    /usr/share/icons/hicolor/scalable/apps/ripper.svg
sudo update-desktop-database /usr/share/applications/
sudo gtk-update-icon-cache /usr/share/icons/hicolor/
```

### Expected installed layout

```
/usr/lib/makemkv-gtk/        ← application code
├── main.py
├── core/
│   ├── languages.py
│   ├── makemkv_config.py
│   ├── makemkv_controller.py
│   ├── makemkv_parser.py
│   ├── models.py
│   ├── paths.py             ← resolves all data paths
│   └── version.py
└── ui/
    ├── backup_view.py
    ├── disc_view.py
    ├── log_view.py
    ├── main_window.py
    └── settings_dialog.py

/usr/share/makemkv-gtk/      ← architecture-independent data
└── ui/
    ├── backup_view.ui
    ├── disc_view.ui
    ├── log_view.ui
    ├── main_window.ui
    └── settings_dialog.ui

/usr/share/doc/makemkv-gtk/  ← documentation
├── version
├── README.md
└── <additional docs added later>

/usr/share/applications/
└── makemkv-gtk.desktop

/usr/share/icons/hicolor/scalable/apps/
└── ripper.svg
```

`src/core/paths.py` resolves all data paths automatically — installed paths
under `/usr/share/makemkv-gtk/` take priority; the source tree is used
automatically during development with no configuration required.

---

## Project Structure

```
makemkv-gui/
├── run.sh                      # Dev launcher
├── pyproject.toml              # Build config
├── doc/
│   └── version                 # Application version string (plain text)
├── src/
│   ├── main.py                 # Adw.Application entry point
│   ├── ui/
│   │   ├── main_window.py      # AdwApplicationWindow + navigation
│   │   ├── disc_view.py        # Drive picker, title list, rip controls
│   │   ├── backup_view.py      # Backup job setup and history
│   │   ├── log_view.py         # Colour-coded log output
│   │   └── settings_dialog.py  # Adw.PreferencesDialog (6 pages)
│   └── core/
│       ├── models.py           # DriveInfo, TitleInfo, BackupJob, RipJob
│       ├── makemkv_controller.py  # GObject + subprocess orchestration
│       ├── makemkv_parser.py   # makemkvcon -r output parser
│       ├── makemkv_config.py   # ~/.MakeMKV/settings.conf reader/writer
│       ├── paths.py            # Runtime path resolution (installed vs dev)
│       └── version.py          # Reads version from doc/version
├── data/
│   ├── ui/
│   │   ├── main_window.ui      # Window chrome, about dialog, menu
│   │   ├── disc_view.ui        # Rip view layout
│   │   ├── backup_view.ui      # Backup view layout
│   │   ├── log_view.ui         # Log view layout
│   │   └── settings_dialog.ui  # Preferences dialog layout
│   └── makemkv-gui.desktop     # XDG desktop entry
└── tests/
    └── test_parser.py
```

---

## Architecture

```
┌─────────────────────────────────────────┐
│          Adw.ApplicationWindow           │
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
