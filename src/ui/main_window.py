"""
MainWindow — loads static structure from data/ui/main_window.ui via Gtk.Builder.
All labels, icons, tooltips, menu items and the about dialog live in the XML.
Python only handles dynamic behaviour: signals, stack switching, toasts.
"""

import gi
import os

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw, Gio
from ui.disc_view import DiscView
from ui.backup_view import BackupView
from ui.log_view import LogView
from ui.settings_dialog import SettingsDialog, GUI_CONFIG_PATH, _load_gui, _save_gui
from core.version import get_version
from core.makemkv_controller import MakeMKVController

# Resolve the .ui path relative to this file so it works regardless of cwd
_UI_FILE = "/usr/share/makemkv-gtk/ui/main_window.ui"


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.controller = MakeMKVController()
        self._load_ui()
        # Use saved window size if available, otherwise fall back to XML defaults
        _gui = _load_gui()
        w = _gui.get("window_width",  self._default_width)
        h = _gui.get("window_height", self._default_height)
        self.set_default_size(w, h)
        self._build_chrome()
        self._setup_actions()
        self._setup_views()
        self.connect("destroy",       self._on_destroy)
        self.connect("close-request", self._on_close_request)
        self.connect("map",           self._on_map)

    def _on_map(self, *_):
        self.controller.emit_binary_missing_if_needed()

    def _on_binary_missing(self, *_):
        dialog = Adw.AlertDialog(
            heading="MakeMKV Not Found",
            body=(
                "The makemkvcon binary could not be found on your system.\n\n"
                "Install MakeMKV to use Ripper:\n"
                "  sudo add-apt-repository ppa:heyarje/makemkv-beta\n"
                "  sudo apt install makemkv-bin makemkv-oss"
            ),
        )
        dialog.add_response("close", "Close")
        dialog.add_response("website", "MakeMKV Website")
        dialog.set_response_appearance(
            "website", Adw.ResponseAppearance.SUGGESTED
        )
        dialog.set_default_response("website")
        dialog.connect("response", self._on_binary_missing_response)
        dialog.present(self)

    def _on_binary_missing_response(self, _dialog, response: str):
        if response == "website":
            import subprocess as _sp
            _sp.Popen(["xdg-open", "https://www.makemkv.com/download/"])

    def _on_close_request(self, *_):
        """Fires before the window is unmapped — safe to read current size."""
        w, h = self.get_width(), self.get_height()
        if w > 0 and h > 0:
            _gui = _load_gui()
            _gui["window_width"]  = w
            _gui["window_height"] = h
            _save_gui(_gui)
        return False  # allow the close to proceed

    def _on_destroy(self, *_):
        self.controller.shutdown()

    # ------------------------------------------------------------------ #
    #  Load XML                                                            #
    # ------------------------------------------------------------------ #

    def _load_ui(self):
        self._builder = Gtk.Builder()
        self._builder.add_from_file(_UI_FILE)

        # Window geometry (defined in XML)
        _geom = self._builder.get_object("window_geometry")
        self._default_width  = _geom.get_default_size()[0] if _geom else 1000
        self._default_height = _geom.get_default_size()[1] if _geom else 720

        # Window title widget (defined in XML)
        self._win_title = self._builder.get_object("win_title")

        # Header action button groups (defined in XML, hidden until needed)
        self._header_actions = {
            "rip":    self._builder.get_object("rip_actions"),
            "logs":   self._builder.get_object("log_actions"),
            "backup": self._builder.get_object("backup_actions"),
        }

        # Individual buttons we need to wire signals to
        self._refresh_btn    = self._builder.get_object("refresh_btn")
        self._eject_btn      = self._builder.get_object("eject_btn")
        self._search_toggle  = self._builder.get_object("search_toggle")
        self._save_log_btn   = self._builder.get_object("save_log_btn")
        self._clear_log_btn  = self._builder.get_object("clear_log_btn")


    # ------------------------------------------------------------------ #
    #  Build chrome (header bar + vertical-tab notebook)                   #
    # ------------------------------------------------------------------ #

    def _build_chrome(self):
        self.toast_overlay = Adw.ToastOverlay()
        self.set_content(self.toast_overlay)

        root_toolbar = Adw.ToolbarView()
        self.toast_overlay.set_child(root_toolbar)

        # ── Header bar ───────────────────────────────────────────────── #
        self._header = Adw.HeaderBar()
        self._header.set_title_widget(self._win_title)

        menu_btn = Gtk.MenuButton(
            icon_name="open-menu-symbolic",
            tooltip_text="Main Menu",
            menu_model=self._builder.get_object("app_menu"),
        )
        self._header.pack_end(menu_btn)

        for widget in self._header_actions.values():
            self._header.pack_end(widget)

        self._refresh_btn.connect("clicked", lambda _: self._on_refresh_drives(None, None))
        self._eject_btn.connect("clicked",   lambda _: self._on_eject_disc(None, None))

        root_toolbar.add_top_bar(self._header)

        # ── Vertical-tab notebook (tabs on left) ──────────────────────── #
        self._notebook = Gtk.Notebook(
            tab_pos=Gtk.PositionType.TOP,
            show_border=False,
            vexpand=True,
            hexpand=True,
        )
        self._notebook.connect("switch-page", self._on_page_switched)
        root_toolbar.set_content(self._notebook)

    # ------------------------------------------------------------------ #
    #  Actions & Views                                                     #
    # ------------------------------------------------------------------ #

    def _setup_actions(self):
        for name, cb in [
            ("settings",       self._on_settings),
            ("about",          self._on_about),
            ("refresh-drives", self._on_refresh_drives),
            ("eject-disc",     self._on_eject_disc),
        ]:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", cb)
            self.add_action(action)

    def _setup_views(self):
        self.disc_view   = DiscView(controller=self.controller)
        self.backup_view = BackupView(controller=self.controller)
        self.log_view    = LogView(controller=self.controller)

        # Wire log header buttons to LogView methods
        self._save_log_btn.connect("clicked",  self.log_view._on_save_log)
        self._clear_log_btn.connect("clicked", self.log_view._on_clear)
        self._search_toggle.bind_property(
            "active",
            self.log_view._search_bar, "search-mode-enabled",
            0,
        )

        # (name, view widget, icon-name, label, header-actions-key)
        self._views = [
            ("rip",    self.disc_view,   "media-optical-dvd",       "Rip Disc", "rip"),
            ("backup", self.backup_view, "drive-harddisk-symbolic",  "Backup",  "backup"),
            ("logs",   self.log_view,    "text-x-script-symbolic",   "Logs",    "logs"),
        ]

        for _name, widget, icon_name, label, _key in self._views:
            tab_box = Gtk.Box(
                orientation=Gtk.Orientation.HORIZONTAL,
                spacing=6,
                margin_top=4,
                margin_bottom=4,
                margin_start=6,
                margin_end=6,
            )
            tab_box.append(Gtk.Image.new_from_icon_name(icon_name))
            tab_box.append(Gtk.Label(label=label))
            self._notebook.append_page(widget, tab_box)

        # Switch to first page → triggers switch-page → shows rip actions
        self._notebook.set_current_page(0)
        self._on_page_switched(self._notebook, self.disc_view, 0)

        self.controller.connect("drives-updated",  self._on_drives_updated)
        self.controller.connect("rip-started",     self._on_rip_started)
        self.controller.connect("rip-finished",    self._on_rip_finished)
        self.controller.connect("error",           self._on_controller_error)
        self.controller.connect("binary-missing", self._on_binary_missing)

        self.controller.scan_drives()

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    def show_toast(self, message: str, timeout: int = 3):
        toast = Adw.Toast.new(message)
        toast.set_timeout(timeout)
        self.toast_overlay.add_toast(toast)

    # ------------------------------------------------------------------ #
    #  Callbacks                                                           #
    # ------------------------------------------------------------------ #

    def _on_page_switched(self, _notebook, _page, page_num: int):
        if not (0 <= page_num < len(self._views)):
            return
        _name, _widget, _icon, _label, actions_key = self._views[page_num]
        for key, widget in self._header_actions.items():
            widget.set_visible(key == actions_key)

    def _on_settings(self, action, param):
        SettingsDialog().present(self)

    @staticmethod
    def _centre_about_labels(dialog):
        """Walk the about dialog widget tree and centre every GtkLabel."""
        from gi.repository import Gtk
        def walk(widget):
            if isinstance(widget, Gtk.Label):
                widget.set_justify(Gtk.Justification.CENTER)
                widget.set_halign(Gtk.Align.CENTER)
            child = widget.get_first_child() if hasattr(widget, "get_first_child") else None
            while child:
                walk(child)
                child = child.get_next_sibling()
        walk(dialog)

    def _on_about(self, action, param):
        dialog = self._builder.get_object("about_dialog")
        dialog.set_version(get_version())

        # Populate Details and Legal only once — the dialog object is reused
        if not getattr(dialog, "_about_populated", False):
            dialog._about_populated = True

            try:
                dialog.set_debug_info(
                    "MakeMKV GUI\n"
                    "A GTK4 + libadwaita front-end for the MakeMKV disc-ripping engine.\n"
                    "\n"
                    "Requirements:\n"
                    "  \u2022 MakeMKV (makemkvcon binary)\n"
                    "  \u2022 Python 3.11+\n"
                    "  \u2022 GTK 4.0 + libadwaita 1.0\n"
                    "  \u2022 python3-gi (PyGObject)"
                )
            except Exception:
                pass


        dialog.connect("map", self._centre_about_labels)
        dialog.present(self)

    def _on_refresh_drives(self, action, param):
        self.disc_view.refresh_drives()
        self.show_toast("Scanning for drives…")

    def _on_eject_disc(self, action, param):
        self.controller.eject_disc()
        self.show_toast("Ejecting disc…", timeout=2)

    def _on_drives_updated(self, controller, drives):
        if drives:
            names = ", ".join(d.disc_name or d.device_path for d in drives)
            self.show_toast(f"Disc detected: {names}", timeout=3)

    def _on_rip_started(self, controller, disc_name: str):
        self.show_toast(f"Ripping started: {disc_name}", timeout=2)

    def _on_rip_finished(self, controller, disc_name: str, success: bool):
        msg = f"✓ Rip complete: {disc_name}" if success else f"✗ Rip failed: {disc_name}"
        self.show_toast(msg, timeout=5)

    def _on_controller_error(self, controller, message: str):
        self.show_toast(f"Error: {message}", timeout=6)
