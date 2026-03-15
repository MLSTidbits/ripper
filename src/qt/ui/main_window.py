"""
MainWindow — QMainWindow with horizontal tab navigation.
"""

import os
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QTabWidget, QToolBar,
    QMessageBox, QStatusBar, QLabel, QMenu,
    QPushButton, QHBoxLayout,
)
from PyQt6.QtGui import QIcon, QAction, QKeySequence
from PyQt6.QtCore import Qt, QSize, pyqtSlot

from core.makemkv_controller import MakeMKVController
from core.version import get_version
from ui.disc_view import DiscView
from ui.backup_view import BackupView
from ui.log_view import LogView
from ui.settings_dialog import SettingsDialog, _load_gui, _save_gui

_ICON_PATH = "/usr/share/icons/hicolor/scalable/apps/reel.svg"


class MainWindow(QMainWindow):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Reel")
        self.setWindowIcon(QIcon(_ICON_PATH))

        self.controller = MakeMKVController(self)
        self._restore_size()
        self._build_ui()
        self._build_toolbar()
        self._build_statusbar()
        self._connect_signals()

        self.controller.emit_binary_missing_if_needed()
        self.controller.scan_drives()

    # ------------------------------------------------------------------ #
    #  Window size persistence                                             #
    # ------------------------------------------------------------------ #

    def _restore_size(self):
        gui = _load_gui()
        w = gui.get("window_width",  1000)
        h = gui.get("window_height", 720)
        self.resize(w, h)

    def closeEvent(self, event):
        gui = _load_gui()
        gui["window_width"]  = self.width()
        gui["window_height"] = self.height()
        _save_gui(gui)
        self.controller.shutdown()
        super().closeEvent(event)

    # ------------------------------------------------------------------ #
    #  Build UI                                                            #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        self._tabs = QTabWidget()
        self._tabs.setTabPosition(QTabWidget.TabPosition.North)
        self._tabs.setDocumentMode(True)
        self.setCentralWidget(self._tabs)

        self.disc_view   = DiscView(self.controller)
        self.backup_view = BackupView(self.controller)
        self.log_view    = LogView(self.controller)

        self._tabs.addTab(self.disc_view,   QIcon.fromTheme("media-optical-dvd"),  "Rip Disc")
        self._tabs.addTab(self.backup_view, QIcon.fromTheme("drive-harddisk"),      "Backup")
        self._tabs.addTab(self.log_view,    QIcon.fromTheme("text-x-script"),       "Logs")

        self._tabs.currentChanged.connect(self._on_tab_changed)

    def _build_toolbar(self):
        tb = QToolBar("Main Toolbar")
        tb.setMovable(False)
        tb.setIconSize(QSize(18, 18))
        self.addToolBar(tb)

        self._refresh_action = QAction(
            QIcon.fromTheme("view-refresh"), "Refresh Drives", self)
        self._refresh_action.setShortcut(QKeySequence("F5"))
        self._refresh_action.triggered.connect(self._on_refresh)
        tb.addAction(self._refresh_action)

        self._eject_action = QAction(
            QIcon.fromTheme("media-eject"), "Eject Disc", self)
        self._eject_action.triggered.connect(self._on_eject)
        tb.addAction(self._eject_action)

        # Log actions — shown only on Logs tab
        tb.addSeparator()
        self._search_action = QAction(
            QIcon.fromTheme("system-search"), "Search Log", self)
        self._search_action.setCheckable(True)
        self._search_action.triggered.connect(
            lambda: self.log_view.toggle_search())
        tb.addAction(self._search_action)

        self._save_log_action = QAction(
            QIcon.fromTheme("document-save"), "Save Log", self)
        self._save_log_action.triggered.connect(self.log_view.save_log)
        tb.addAction(self._save_log_action)

        self._clear_log_action = QAction(
            QIcon.fromTheme("edit-clear"), "Clear Log", self)
        self._clear_log_action.triggered.connect(self.log_view.clear_log)
        tb.addAction(self._clear_log_action)

        # Spacer to push menu button right
        spacer = QWidget()
        spacer.setSizePolicy(
            spacer.sizePolicy().horizontalPolicy(),
            spacer.sizePolicy().verticalPolicy(),
        )
        from PyQt6.QtWidgets import QSizePolicy
        spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)

        # Hamburger menu
        menu_btn = QPushButton()
        menu_btn.setIcon(QIcon.fromTheme("open-menu-symbolic",
                                          QIcon.fromTheme("application-menu")))
        menu_btn.setFlat(True)
        menu_btn.setFixedSize(32, 32)
        menu_btn.clicked.connect(self._show_menu)
        tb.addWidget(menu_btn)
        self._menu_btn = menu_btn

        self._on_tab_changed(0)

    def _build_statusbar(self):
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_label = QLabel("Ready")
        self._status_bar.addWidget(self._status_label)

    # ------------------------------------------------------------------ #
    #  Signals                                                             #
    # ------------------------------------------------------------------ #

    def _connect_signals(self):
        self.controller.drives_updated.connect(self._on_drives_updated)
        self.controller.rip_started.connect(self._on_rip_started)
        self.controller.rip_finished.connect(self._on_rip_finished)
        self.controller.error.connect(self._on_error)
        self.controller.binary_missing.connect(self._on_binary_missing)

    # ------------------------------------------------------------------ #
    #  Tab switching                                                       #
    # ------------------------------------------------------------------ #

    def _on_tab_changed(self, index: int):
        is_log = index == 2
        self._search_action.setVisible(is_log)
        self._save_log_action.setVisible(is_log)
        self._clear_log_action.setVisible(is_log)
        is_rip = index == 0
        self._refresh_action.setVisible(is_rip)
        self._eject_action.setVisible(is_rip)

    # ------------------------------------------------------------------ #
    #  Menu                                                                #
    # ------------------------------------------------------------------ #

    def _show_menu(self):
        menu = QMenu(self)
        menu.addAction("Refresh Drives",  self._on_refresh)
        menu.addAction("Eject Disc",      self._on_eject)
        menu.addSeparator()
        menu.addAction("Preferences…",   self._on_settings)
        menu.addSeparator()
        menu.addAction("About Reel…",     self._on_about)
        menu.exec(self._menu_btn.mapToGlobal(
            self._menu_btn.rect().bottomLeft()))

    # ------------------------------------------------------------------ #
    #  Slots                                                               #
    # ------------------------------------------------------------------ #

    def _on_refresh(self):
        self.disc_view.refresh_drives()
        self._status_label.setText("Scanning for drives…")

    def _on_eject(self):
        self.controller.eject_disc()
        self._status_label.setText("Ejecting disc…")

    def _on_settings(self):
        dlg = SettingsDialog(self)
        dlg.exec()

    def _on_about(self):
        QMessageBox.about(
            self, "About Reel",
            f"<b>Reel</b> v{get_version()}<br><br>"
            "A Qt6 front-end for MakeMKV on Linux.<br><br>"
            "Requirements:<br>"
            "• MakeMKV (makemkvcon binary)<br>"
            "• Python 3.11+<br>"
            "• PyQt6",
        )

    @pyqtSlot(list)
    def _on_drives_updated(self, drives: list):
        if drives:
            names = ", ".join(d.disc_name or d.device_path for d in drives)
            self._status_label.setText(f"Disc detected: {names}")
        else:
            self._status_label.setText("No discs detected")

    @pyqtSlot(str)
    def _on_rip_started(self, disc_name: str):
        self._status_label.setText(f"Ripping: {disc_name}")

    @pyqtSlot(str, bool)
    def _on_rip_finished(self, disc_name: str, success: bool):
        self._status_label.setText(
            f"✓ Rip complete: {disc_name}" if success
            else f"✗ Rip failed: {disc_name}")

    @pyqtSlot(str)
    def _on_error(self, message: str):
        self._status_label.setText(f"Error: {message}")

    @pyqtSlot()
    def _on_binary_missing(self):
        QMessageBox.critical(
            self, "MakeMKV Not Found",
            "The makemkvcon binary could not be found.\n\n"
            "Install MakeMKV:\n"
            "  sudo add-apt-repository ppa:heyarje/makemkv-beta\n"
            "  sudo apt install makemkv-bin makemkv-oss"
        )
