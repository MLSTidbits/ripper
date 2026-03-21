"""
SettingsDialog — Tabbed preferences window.
Reads/writes ~/.MakeMKV/settings.conf via MakeMKVConfig
and ~/.config/reel/settings.json for GUI-only prefs.
"""

import json
import os
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QLineEdit, QPushButton, QCheckBox, QComboBox,
    QGroupBox, QFormLayout, QFileDialog, QDialogButtonBox,
    QSpinBox, QScrollArea, QFrame,
)
from PyQt5.QtCore import Qt

from core.makemkv_config import MakeMKVConfig
from core.languages import get_languages, get_system_language_code

GUI_CONFIG_PATH = os.path.expanduser("~/.config/reel/settings.json")


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


class SettingsDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setMinimumSize(640, 520)
        self._config = MakeMKVConfig()
        self._config.load()
        self._gui = _load_gui()
        self._languages = get_languages()
        self._build_ui()
        self._load_values()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        root.addWidget(self._tabs)

        self._tabs.addTab(self._make_general_tab(),  "General")
        self._tabs.addTab(self._make_output_tab(),   "Output")
        self._tabs.addTab(self._make_dvd_tab(),      "DVD")
        self._tabs.addTab(self._make_io_tab(),       "I/O")
        self._tabs.addTab(self._make_tools_tab(),    "Tools")
        self._tabs.addTab(self._make_app_tab(),      "App")

        buttons = QDialogButtonBox(
            QDialogButtonBox.Cancel |
            QDialogButtonBox.Save
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    # ── Tab builders ── #

    def _scrolled(self, widget: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(widget)
        return scroll

    def _make_general_tab(self) -> QScrollArea:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        lang_box = QGroupBox("Language")
        form = QFormLayout(lang_box)
        self._iface_lang = QComboBox()
        self._pref_lang  = QComboBox()
        # Interface language — always has a value
        for display, code in self._languages:
            self._iface_lang.addItem(display, userData=code)

        # Audio/subtitle language — first entry is unset (removes key)
        self._pref_lang.addItem("None", userData="")
        for display, code in self._languages:
            self._pref_lang.addItem(display, userData=code)
        form.addRow("Interface language:", self._iface_lang)
        form.addRow("Audio/subtitle language:", self._pref_lang)
        layout.addWidget(lang_box)

        key_box = QGroupBox("Registration Key")
        key_form = QFormLayout(key_box)
        self._key_edit = QLineEdit()
        self._key_edit.setPlaceholderText("T-XXXXXXXXXXXXXXXXXXXXXXXXXXXX")
        key_form.addRow("License key:", self._key_edit)
        layout.addWidget(key_box)

        layout.addStretch()
        return self._scrolled(w)

    def _make_output_tab(self) -> QScrollArea:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        dest_box = QGroupBox("Destination")
        dest_form = QFormLayout(dest_box)
        dest_row = QHBoxLayout()
        self._dest_edit = QLineEdit()
        self._dest_edit.setPlaceholderText(
            os.path.expanduser("~/Videos/Rips"))
        dest_row.addWidget(self._dest_edit)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._on_browse_dest)
        dest_row.addWidget(browse_btn)
        dest_form.addRow("Output directory:", dest_row)
        layout.addWidget(dest_box)

        profile_box = QGroupBox("Profile")
        profile_form = QFormLayout(profile_box)
        self._profile_edit = QLineEdit()
        profile_form.addRow("Default profile:", self._profile_edit)
        layout.addWidget(profile_box)

        layout.addStretch()
        return self._scrolled(w)

    def _make_dvd_tab(self) -> QScrollArea:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        dvd_box = QGroupBox("DVD Settings")
        form = QFormLayout(dvd_box)
        self._min_title_len = QSpinBox()
        self._min_title_len.setRange(0, 3600)
        self._min_title_len.setSuffix(" sec")
        form.addRow("Minimum title length:", self._min_title_len)
        self._sp_remove = QComboBox()
        self._sp_remove.addItems(["0 — Disabled", "1 — Method 1", "2 — Method 2"])
        form.addRow("Subpicture removal:", self._sp_remove)
        layout.addWidget(dvd_box)
        layout.addStretch()
        return self._scrolled(w)

    def _make_io_tab(self) -> QScrollArea:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        io_box = QGroupBox("I/O Settings")
        form = QFormLayout(io_box)
        self._retry_count = QSpinBox()
        self._retry_count.setRange(0, 20)
        form.addRow("Error retry count:", self._retry_count)
        self._rbuf_size = QSpinBox()
        self._rbuf_size.setRange(0, 512)
        self._rbuf_size.setSuffix(" MB")
        form.addRow("Read buffer size:", self._rbuf_size)
        self._single_drive = QCheckBox("Single drive mode")
        form.addRow("", self._single_drive)
        layout.addWidget(io_box)
        layout.addStretch()
        return self._scrolled(w)

    def _make_tools_tab(self) -> QScrollArea:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        iface_box = QGroupBox("Interface")
        form = QFormLayout(iface_box)
        self._expert_mode = QCheckBox("Enable expert mode")
        form.addRow("", self._expert_mode)
        layout.addWidget(iface_box)

        java_box = QGroupBox("Java")
        java_form = QFormLayout(java_box)
        self._java_edit = QLineEdit()
        self._java_edit.setPlaceholderText("/usr/bin/java")
        java_form.addRow("Java executable:", self._java_edit)
        layout.addWidget(java_box)

        layout.addStretch()
        return self._scrolled(w)

    def _make_app_tab(self) -> QScrollArea:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        win_box = QGroupBox("Window")
        form = QFormLayout(win_box)
        self._remember_size = QCheckBox("Remember window size")
        self._remember_size.setChecked(True)
        form.addRow("", self._remember_size)
        layout.addWidget(win_box)

        debug_box = QGroupBox("Debug")
        debug_form = QFormLayout(debug_box)
        self._show_debug = QCheckBox("Show debug messages in log")
        debug_form.addRow("", self._show_debug)
        self._show_avsync = QCheckBox("Show A/V sync messages")
        debug_form.addRow("", self._show_avsync)
        layout.addWidget(debug_box)

        layout.addStretch()
        return self._scrolled(w)

    # ── Load / Save ── #

    def _lang_index(self, combo: QComboBox, code: str) -> int:
        for i in range(combo.count()):
            if combo.itemData(i) == code:
                return i
        return 0

    def _load_values(self):
        sys_lang = get_system_language_code()

        iface = self._config.get_str("app_InterfaceLanguage", sys_lang)
        self._iface_lang.setCurrentIndex(
            self._lang_index(self._iface_lang, iface))

        # None when key is absent — selects '— Not set —' at index 0
        pref = self._config.get("app_PreferredLanguage")  # None if missing
        self._pref_lang.setCurrentIndex(
            0 if not pref else self._lang_index(self._pref_lang, pref))

        self._key_edit.setText(self._config.get_str("app_Key", ""))
        self._dest_edit.setText(
            self._config.get_str("app_DestinationDir",
                                  self._gui.get("rip_destination", "")))
        self._profile_edit.setText(
            self._config.get_str("app_DefaultProfileName", ""))
        self._min_title_len.setValue(
            self._config.get_int("dvd_MinimumTitleLength", 0))
        self._sp_remove.setCurrentIndex(
            self._config.get_int("dvd_SPRemoveMethod", 0))
        self._retry_count.setValue(
            self._config.get_int("io_ErrorRetryCount", 0))
        self._rbuf_size.setValue(
            self._config.get_int("io_RBufSizeMB", 0))
        self._single_drive.setChecked(
            self._config.get_bool("io_SingleDrive", False))
        self._expert_mode.setChecked(
            self._config.get_bool("app_ExpertMode", False))
        self._java_edit.setText(self._config.get_str("app_Java", ""))
        self._show_debug.setChecked(
            self._config.get_bool("app_ShowDebug", False))
        self._show_avsync.setChecked(
            self._config.get_bool("app_ShowAVSyncMessages", False))
        self._remember_size.setChecked(
            self._gui.get("remember_size", True))

    def _on_browse_dest(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select Output Directory",
            os.path.expanduser("~/Videos"))
        if path:
            self._dest_edit.setText(path)

    def _on_save(self):
        self._config.set_str("app_InterfaceLanguage",
                              self._iface_lang.currentData())
        pref_lang = self._pref_lang.currentData()
        if pref_lang:
            self._config.set_str("app_PreferredLanguage", pref_lang)
        else:
            self._config.remove("app_PreferredLanguage")
        self._config.set_str("app_Key", self._key_edit.text().strip())
        dest = self._dest_edit.text().strip()
        self._config.set_str("app_DestinationDir", dest)
        self._config.set_str("app_DefaultProfileName",
                              self._profile_edit.text().strip())
        self._config.set_int("dvd_MinimumTitleLength",
                              self._min_title_len.value())
        self._config.set_int("dvd_SPRemoveMethod",
                              self._sp_remove.currentIndex())
        self._config.set_int("io_ErrorRetryCount", self._retry_count.value())
        self._config.set_int("io_RBufSizeMB",      self._rbuf_size.value())
        self._config.set_bool("io_SingleDrive",    self._single_drive.isChecked())
        self._config.set_bool("app_ExpertMode",    self._expert_mode.isChecked())
        self._config.set_str("app_Java",           self._java_edit.text().strip())
        self._config.set_bool("app_ShowDebug",     self._show_debug.isChecked())
        self._config.set_bool("app_ShowAVSyncMessages",
                               self._show_avsync.isChecked())
        self._config.save()

        self._gui["rip_destination"] = dest
        self._gui["remember_size"]   = self._remember_size.isChecked()
        _save_gui(self._gui)

        self.accept()
