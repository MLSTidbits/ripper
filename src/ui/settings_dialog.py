"""
SettingsDialog — Preferences window with top tab bar and Save / Cancel header buttons.
Static structure (all 6 tab pages, groups, rows) loaded from settings_dialog.ui.
Python owns only dynamic behaviour: loading values, saving, browse buttons,
dest-sensitivity logic, SpinRow sizing.

Writes to:
  • ~/.MakeMKV/settings.conf             (native MakeMKV keys)
  • ~/.config/makemkv-gui/settings.json  (GUI-only prefs)
"""

import gi
import os
import json

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw
from core.makemkv_config import MakeMKVConfig
from core.languages import get_languages, get_system_language_code
_UI_FILE = "/usr/share/reel/ui/settings_dialog.ui"

GUI_CONFIG_PATH = os.path.expanduser("~/.config/reel/settings.json")

# ── app_DestinationType ──────────────────────────────────────────────── #
DEST_TYPE_OPTIONS = ["None", "Auto", "Semi-Auto", "Custom"]

def _dest_type_to_index(raw) -> int:
    if raw is None:
        return 1
    return {0: 0, 2: 2, 3: 3}.get(int(raw), 1)

def _index_to_dest_type(idx: int):
    return {0: 0, 1: None, 2: 2, 3: 3}.get(idx, None)

def _dest_enables_path(idx: int) -> bool:
    return idx in (2, 3)

# ── app_DefaultProfileName ──────────────────────────────────────────── #
PROFILE_LABELS = ["Default", "AAC-stereo", "FLAC", "WDTV"]
PROFILE_VALUES = [None,      "AAC-stereo", "FLAC", "WDTV"]

def _profile_to_index(raw) -> int:
    if not raw:
        return 0
    try:
        return PROFILE_VALUES.index(raw)
    except ValueError:
        return 0

def _index_to_profile(idx: int):
    return PROFILE_VALUES[idx] if 0 <= idx < len(PROFILE_VALUES) else None

# ── dvd_SPRemoveMethod ───────────────────────────────────────────────── #
SP_REMOVE_OPTIONS = ["Auto", "CellWalk", "CellTrim", "CellFull"]

# ── io_RBufSizeMB ────────────────────────────────────────────────────── #
RBUF_LABELS = ["Auto", "64 MB", "256 MB", "512 MB", "786 MB", "1024 MB"]
RBUF_VALUES = [None,   64,      256,       512,      786,      1024]

def _rbuf_to_index(raw) -> int:
    if raw is None:
        return 0
    try:
        return RBUF_VALUES.index(int(raw))
    except (ValueError, TypeError):
        return 0

def _index_to_rbuf(idx: int):
    return RBUF_VALUES[idx] if 0 <= idx < len(RBUF_VALUES) else None

# ── GUI JSON helpers ─────────────────────────────────────────────────── #

def _load_gui() -> dict:
    try:
        with open(GUI_CONFIG_PATH) as f:
            return json.load(f)
    except Exception:
        return {}

def _save_gui(data: dict):
    os.makedirs(os.path.dirname(GUI_CONFIG_PATH), exist_ok=True)
    with open(GUI_CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)


# ── SettingsDialog ───────────────────────────────────────────────────── #

class SettingsDialog:
    """
    Wraps an AdwWindow containing a GtkNotebook with icon+label tabs.
    Call .present(parent) to show; the window is modal over parent.
    """

    # Tab definitions: (title, icon-name, scroll-widget-id)
    _TABS = [
        ("General", "preferences-system-symbolic",      "scroll_general"),
        ("Output",  "folder-symbolic",                  "scroll_output"),
        ("DVD",     "media-optical-dvd",                "scroll_dvd"),
        ("I/O",     "drive-optical-symbolic",           "scroll_io"),
        ("Tools",   "applications-engineering-symbolic","scroll_tools"),
        ("App",     "preferences-desktop-symbolic",     "scroll_app"),
    ]

    def __init__(self):
        self._mkv = MakeMKVConfig()
        self._gui = _load_gui()
        self._load_ui()
        self._populate_tabs()
        self._build_general()
        self._build_output()
        self._build_dvd()
        self._build_io()
        self._build_tools()
        self._build_app()

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def present(self, parent: Gtk.Window):
        self._win.set_transient_for(parent)
        self._win.present()

    # ------------------------------------------------------------------ #
    #  Load XML                                                            #
    # ------------------------------------------------------------------ #

    def _load_ui(self):
        b = Gtk.Builder()
        b.add_from_file(_UI_FILE)
        self._b = b

        self._win       = b.get_object("settings_window")
        self._notebook  = b.get_object("notebook")
        self._save_btn  = b.get_object("save_btn")
        self._cancel_btn = b.get_object("cancel_btn")

        # ── General ──
        self._key_row        = b.get_object("key_row")
        self._iface_lang_row = b.get_object("iface_lang_row")
        self._pref_lang_row  = b.get_object("pref_lang_row")
        self._proxy_row      = b.get_object("proxy_row")
        self._expert_row     = b.get_object("expert_row")
        self._profile_row    = b.get_object("profile_row")

        # ── Output ──
        self._dest_dir_row       = b.get_object("dest_dir_row")
        self._dest_type_row      = b.get_object("dest_type_row")
        self._backup_decrypt_row = b.get_object("backup_decrypt_row")
        self._use_title_row      = b.get_object("use_title_row")

        # ── DVD ──
        self._min_length_row = b.get_object("min_length_row")
        self._sp_remove_row  = b.get_object("sp_remove_row")

        # ── I/O ──
        self._retry_row    = b.get_object("retry_row")
        self._rbuf_row     = b.get_object("rbuf_row")
        self._sdf_stop_row = b.get_object("sdf_stop_row")

        # ── Tools ──
        self._ccextractor_row = b.get_object("ccextractor_row")
        self._java_row        = b.get_object("java_row")

        # ── App ──
        self._binary_row   = b.get_object("binary_row")
        self._auto_rip_row = b.get_object("auto_rip_row")
        self._eject_row    = b.get_object("eject_row")
        self._notify_row   = b.get_object("notify_row")

        # ── Scroll containers ──
        self._scrolls = {
            name: b.get_object(name)
            for _, _, name in self._TABS
        }

        # Header button signals
        self._save_btn.connect("clicked",   self._on_save)
        self._cancel_btn.connect("clicked", lambda _: self._win.close())


    # ------------------------------------------------------------------ #
    #  Build tab pages                                                     #
    # ------------------------------------------------------------------ #

    def _populate_tabs(self):
        """Append each scroll page to the notebook with an icon+label tab widget."""
        for title, icon_name, scroll_id in self._TABS:
            scroll = self._scrolls[scroll_id]

            # Tab label widget: horizontal box with icon and text label
            tab_box = Gtk.Box(
                orientation=Gtk.Orientation.HORIZONTAL,
                spacing=6,
            )
            tab_box.append(Gtk.Image.new_from_icon_name(icon_name))
            tab_box.append(Gtk.Label(label=title))

            self._notebook.append_page(scroll, tab_box)

    # ------------------------------------------------------------------ #
    #  Page builders                                                       #
    # ------------------------------------------------------------------ #

    def _build_general(self):
        # Profile combo model
        profile_model = Gtk.StringList()
        for opt in PROFILE_LABELS:
            profile_model.append(opt)
        self._profile_row.set_model(profile_model)

        # Populate values
        self._key_row.set_text(self._mkv.get_str("app_Key", ""))

        # Build language dropdowns from system ISO 639-2 data
        self._lang_list = get_languages()   # [(display_name, code), ...]
        lang_model = Gtk.StringList()
        for display_name, _ in self._lang_list:
            lang_model.append(display_name)
        # Both rows share the same model (read-only StringList is safe to reuse)
        self._iface_lang_row.set_model(lang_model)
        self._pref_lang_row.set_model(lang_model)

        sys_code = get_system_language_code()
        iface_code = self._mkv.get_str("app_InterfaceLanguage", sys_code)
        pref_code  = self._mkv.get_str("app_PreferredLanguage",  sys_code)
        self._iface_lang_row.set_selected(self._lang_index(iface_code, sys_code))
        self._pref_lang_row.set_selected(self._lang_index(pref_code,  sys_code))
        self._proxy_row.set_text(self._mkv.get_str("app_Proxy", ""))
        self._expert_row.set_active(self._mkv.get_bool("app_ExpertMode", False))
        self._profile_row.set_selected(
            _profile_to_index(self._mkv.get_str("app_DefaultProfileName", ""))
        )
        self._update_profile_visibility(self._expert_row.get_active())
        self._expert_row.connect(
            "notify::active",
            lambda w, _: self._update_profile_visibility(w.get_active()),
        )

    def _build_output(self):
        dest_model = Gtk.StringList()
        for opt in DEST_TYPE_OPTIONS:
            dest_model.append(opt)
        self._dest_type_row.set_model(dest_model)
        self._dest_dir_row.add_suffix(self._folder_btn(self._dest_dir_row))

        self._dest_dir_row.set_text(
            self._mkv.get_str("app_DestinationDir")
            or self._gui.get("rip_destination", os.path.expanduser("~/Videos/Rips"))
        )
        self._dest_type_row.set_selected(
            _dest_type_to_index(self._mkv.get("app_DestinationType"))
        )
        self._update_dest_sensitivity(self._dest_type_row.get_selected())
        self._dest_type_row.connect(
            "notify::selected",
            lambda w, _: self._update_dest_sensitivity(w.get_selected()),
        )
        self._backup_decrypt_row.set_active(
            self._mkv.get_bool("app_BackupDecrypted", True)
        )
        self._use_title_row.set_active(self._gui.get("use_title_name", True))

    def _build_dvd(self):
        sp_model = Gtk.StringList()
        for opt in SP_REMOVE_OPTIONS:
            sp_model.append(opt)
        self._sp_remove_row.set_model(sp_model)
        self._min_length_row.set_value(
            float(self._mkv.get_int("dvd_MinimumTitleLength", 120))
        )
        self._sp_remove_row.set_selected(self._mkv.get_int("dvd_SPRemoveMethod", 0))

    def _build_io(self):
        rbuf_model = Gtk.StringList()
        for opt in RBUF_LABELS:
            rbuf_model.append(opt)
        self._rbuf_row.set_model(rbuf_model)
        self._retry_row.set_value(float(self._mkv.get_int("io_ErrorRetryCount", 4)))
        self._rbuf_row.set_selected(_rbuf_to_index(self._mkv.get("io_RBufSizeMB")))
        self._sdf_stop_row.set_active(self._mkv.get_bool("sdf_Stop", False))

    def _build_tools(self):
        self._ccextractor_row.add_suffix(self._file_btn(self._ccextractor_row))
        self._java_row.add_suffix(self._file_btn(self._java_row))
        self._ccextractor_row.set_text(self._mkv.get_str("app_ccextractor", ""))
        self._java_row.set_text(self._mkv.get_str("app_Java", ""))

    def _build_app(self):
        self._binary_row.set_text(self._gui.get("binary_path", "makemkvcon"))
        self._auto_rip_row.set_active(self._gui.get("auto_rip", False))
        self._eject_row.set_active(self._gui.get("eject_after_rip", True))
        self._notify_row.set_active(self._gui.get("notifications", True))

    # ------------------------------------------------------------------ #
    #  Helper widgets                                                      #
    # ------------------------------------------------------------------ #

    def _lang_index(self, code: str, fallback: str) -> int:
        """Return the combo index for an ISO 639-2 code, or fallback code index."""
        code = code.strip().lower()
        for i, (_, c) in enumerate(self._lang_list):
            if c == code:
                return i
        fallback = fallback.strip().lower()
        for i, (_, c) in enumerate(self._lang_list):
            if c == fallback:
                return i
        return 0

    def _lang_code(self, row) -> str:
        """Return the ISO 639-2 code for the currently selected combo index."""
        idx = row.get_selected()
        if 0 <= idx < len(self._lang_list):
            return self._lang_list[idx][1]
        return "eng"

    def _update_profile_visibility(self, expert_on: bool):
        self._profile_row.set_visible(expert_on)

    def _update_dest_sensitivity(self, idx: int):
        self._dest_dir_row.set_sensitive(_dest_enables_path(idx))

    def _folder_btn(self, row: Adw.EntryRow) -> Gtk.Button:
        btn = Gtk.Button(
            icon_name="folder-open-symbolic",
            valign=Gtk.Align.CENTER,
            css_classes=["flat"],
        )
        btn.connect("clicked", lambda _: self._browse_folder(row))
        return btn

    def _file_btn(self, row: Adw.EntryRow) -> Gtk.Button:
        btn = Gtk.Button(
            icon_name="document-open-symbolic",
            valign=Gtk.Align.CENTER,
            css_classes=["flat"],
        )
        btn.connect("clicked", lambda _: self._browse_file(row))
        return btn

    def _browse_folder(self, row: Adw.EntryRow):
        Gtk.FileDialog(title="Choose Folder").select_folder(
            parent=self._win, cancellable=None,
            callback=lambda d, r: self._finish_folder(d, r, row),
        )

    def _finish_folder(self, dialog, result, row):
        try:
            folder = dialog.select_folder_finish(result)
            if folder:
                row.set_text(folder.get_path())
        except Exception:
            pass

    def _browse_file(self, row: Adw.EntryRow):
        Gtk.FileDialog(title="Choose File").open(
            parent=self._win, cancellable=None,
            callback=lambda d, r: self._finish_file(d, r, row),
        )

    def _finish_file(self, dialog, result, row):
        try:
            f = dialog.open_finish(result)
            if f:
                row.set_text(f.get_path())
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    #  Save                                                                #
    # ------------------------------------------------------------------ #

    def _on_save(self, _btn):
        # ── settings.conf ──
        self._mkv.set_str("app_Key",               self._key_row.get_text())
        self._mkv.set_str("app_InterfaceLanguage", self._lang_code(self._iface_lang_row))
        self._mkv.set_str("app_PreferredLanguage", self._lang_code(self._pref_lang_row))
        self._mkv.set_str("app_Proxy",             self._proxy_row.get_text())
        self._mkv.set_bool("app_ExpertMode",        self._expert_row.get_active())

        profile_val = _index_to_profile(self._profile_row.get_selected())
        if profile_val:
            self._mkv.set_str("app_DefaultProfileName", profile_val)
        else:
            self._mkv.remove("app_DefaultProfileName")

        self._mkv.set_str("app_DestinationDir", self._dest_dir_row.get_text())

        dt_val = _index_to_dest_type(self._dest_type_row.get_selected())
        if dt_val is None:
            self._mkv.remove("app_DestinationType")
        else:
            self._mkv.set_int("app_DestinationType", dt_val)

        self._mkv.set_bool("app_BackupDecrypted",   self._backup_decrypt_row.get_active())
        self._mkv.set_int("dvd_MinimumTitleLength", int(self._min_length_row.get_value()))
        self._mkv.set_int("dvd_SPRemoveMethod",     self._sp_remove_row.get_selected())
        self._mkv.set_int("io_ErrorRetryCount",     int(self._retry_row.get_value()))

        rbuf_val = _index_to_rbuf(self._rbuf_row.get_selected())
        if rbuf_val is None:
            self._mkv.remove("io_RBufSizeMB")
        else:
            self._mkv.set_int("io_RBufSizeMB", rbuf_val)

        self._mkv.set_bool("sdf_Stop",       self._sdf_stop_row.get_active())
        self._mkv.set_str("app_ccextractor", self._ccextractor_row.get_text())
        self._mkv.set_str("app_Java",        self._java_row.get_text())
        self._mkv.save()

        # ── GUI JSON ──
        self._gui.update({
            "binary_path":     self._binary_row.get_text(),
            "auto_rip":        self._auto_rip_row.get_active(),
            "eject_after_rip": self._eject_row.get_active(),
            "notifications":   self._notify_row.get_active(),
            "rip_destination": self._dest_dir_row.get_text(),
            "use_title_name":  self._use_title_row.get_active(),
        })
        _save_gui(self._gui)
        self._win.close()
