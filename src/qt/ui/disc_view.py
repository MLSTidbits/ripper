"""
DiscView — Drive picker, title list, and rip controls.
"""

import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QProgressBar, QGroupBox,
    QScrollArea, QCheckBox, QLineEdit, QSizePolicy, QFrame,
    QTreeWidget, QTreeWidgetItem, QAbstractItemView, QHeaderView,
)
from PyQt5.QtCore import Qt, pyqtSlot
from PyQt5.QtGui import QIcon, QColor

from core.makemkv_controller import MakeMKVController
from core.models import DriveInfo, TitleInfo


class DiscView(QWidget):
    """Drive picker → title list → rip controls."""

    def __init__(self, controller: MakeMKVController, parent=None):
        super().__init__(parent)
        self.controller = controller
        self._titles: list[TitleInfo] = []
        self._ripping = False
        self._build_ui()
        self._connect_signals()

    # ------------------------------------------------------------------ #
    #  Build UI                                                            #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Scrollable content area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        root.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(16)

        # ── Drives group ── #
        drives_box = QGroupBox("Optical Drives")
        drives_layout = QVBoxLayout(drives_box)
        self._drives_list = QListWidget()
        self._drives_list.setAlternatingRowColors(True)
        self._drives_list.itemDoubleClicked.connect(self._on_drive_activated)
        drives_layout.addWidget(self._drives_list)
        layout.addWidget(drives_box)

        # LibreDrive label
        self._libre_label = QLabel()
        self._libre_label.setStyleSheet("color: #2ecc71; font-size: 12px;")
        self._libre_label.setVisible(False)
        layout.addWidget(self._libre_label)

        # ── Disc info bar ── #
        self._disc_info_label = QLabel("Select a drive to load disc information")
        self._disc_info_label.setStyleSheet("color: palette(mid); font-style: italic;")
        layout.addWidget(self._disc_info_label)

        # ── Titles group ── #
        titles_box = QGroupBox("Titles")
        titles_layout = QVBoxLayout(titles_box)

        # Select All / Deselect All button
        title_header = QHBoxLayout()
        title_header.addStretch()
        self._select_all_btn = QPushButton("Select All")
        self._select_all_btn.setFlat(True)
        self._select_all_btn.clicked.connect(self._on_select_all)
        title_header.addWidget(self._select_all_btn)
        titles_layout.addLayout(title_header)

        self._titles_tree = QTreeWidget()
        self._titles_tree.setColumnCount(5)
        self._titles_tree.setHeaderLabels(["", "Title", "Duration", "Size", "Chapters"])
        self._titles_tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self._titles_tree.header().setSectionResizeMode(0, QHeaderView.Fixed)
        self._titles_tree.header().resizeSection(0, 28)
        self._titles_tree.setIndentation(0)
        self._titles_tree.setRootIsDecorated(False)
        self._titles_tree.setAlternatingRowColors(True)
        self._titles_tree.setEditTriggers(QAbstractItemView.DoubleClicked)
        titles_layout.addWidget(self._titles_tree)
        layout.addWidget(titles_box)

        # ── Progress group ── #
        self._progress_box = QGroupBox("Progress")
        progress_layout = QVBoxLayout(self._progress_box)
        self._rip_title_label = QLabel()
        self._rip_title_label.setVisible(False)
        progress_layout.addWidget(self._rip_title_label)
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 1000)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        progress_layout.addWidget(self._progress_bar)
        self._status_label = QLabel()
        self._status_label.setStyleSheet("color: palette(mid); font-size: 12px;")
        progress_layout.addWidget(self._status_label)
        self._progress_box.setVisible(False)
        layout.addWidget(self._progress_box)

        layout.addStretch()

        # ── Footer action bar ── #
        footer = QFrame()
        footer.setFrameShape(QFrame.StyledPanel)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(12, 6, 12, 6)
        footer_layout.addStretch()
        self._rip_btn = QPushButton("Start Ripping")
        self._rip_btn.setFixedWidth(160)
        self._rip_btn.setEnabled(False)
        self._rip_btn.clicked.connect(self._on_rip_clicked)
        footer_layout.addWidget(self._rip_btn)
        footer_layout.addStretch()
        root.addWidget(footer)

    # ------------------------------------------------------------------ #
    #  Signals                                                             #
    # ------------------------------------------------------------------ #

    def _connect_signals(self):
        self.controller.drives_updated.connect(self._on_drives_updated)
        self.controller.titles_loaded.connect(self._on_titles_loaded)
        self.controller.progress.connect(self._on_progress)
        self.controller.rip_title.connect(self._on_rip_title)
        self.controller.rip_finished.connect(self._on_rip_finished)
        self.controller.libre_drive.connect(self._on_libre_drive)

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def refresh_drives(self):
        self.controller.scan_drives()

    # ------------------------------------------------------------------ #
    #  Slots                                                               #
    # ------------------------------------------------------------------ #

    @pyqtSlot(list)
    def _on_drives_updated(self, drives: list):
        self._libre_label.setVisible(False)
        self._drives_list.clear()
        if drives:
            for drive in drives:
                text = drive.drive_name or drive.device_path
                if drive.has_disc:
                    text += f"  ·  {drive.disc_name}  [{drive.device_path}]"
                else:
                    text += f"  [{drive.device_path}]"
                item = QListWidgetItem(text)
                item.setData(Qt.UserRole, drive)
                self._drives_list.addItem(item)
        else:
            self._drives_list.addItem("No optical drives detected")

    @pyqtSlot(QListWidgetItem)
    def _on_drive_activated(self, item: QListWidgetItem):
        drive: DriveInfo = item.data(Qt.UserRole)
        if drive and drive.has_disc:
            self._disc_info_label.setText(
                f"Loading disc {drive.drive_index}…")
            self.controller.load_disc(drive.drive_index)

    @pyqtSlot(str, list)
    def _on_titles_loaded(self, drive_path: str, titles: list):
        self._titles = titles
        self._titles_tree.clear()
        disc_name = titles[0].disc_name if titles else drive_path
        self._disc_info_label.setText(
            f"Disc: {disc_name}  ·  {len(titles)} titles found")
        for title in titles:
            item = QTreeWidgetItem()
            item.setData(0, Qt.UserRole, title)
            item.setCheckState(0, Qt.Checked if title.selected
                               else Qt.Unchecked)
            item.setText(1, title.name)
            item.setText(2, title.duration)
            item.setText(3, title.size_str)
            item.setText(4, str(title.chapter_count))
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            self._titles_tree.addTopLevelItem(item)
        self._titles_tree.itemChanged.connect(self._on_title_item_changed)
        self._rip_btn.setEnabled(bool(titles))
        self._refresh_select_all_btn()

    @pyqtSlot(QTreeWidgetItem, int)
    def _on_title_item_changed(self, item: QTreeWidgetItem, col: int):
        title: TitleInfo = item.data(0, Qt.UserRole)
        if not title:
            return
        if col == 0:
            title.selected = item.checkState(0) == Qt.Checked
            self._refresh_select_all_btn()
        elif col == 1:
            title.output_file_name = item.text(1)

    def _all_selected(self) -> bool:
        for i in range(self._titles_tree.topLevelItemCount()):
            item = self._titles_tree.topLevelItem(i)
            if item.checkState(0) != Qt.Checked:
                return False
        return self._titles_tree.topLevelItemCount() > 0

    def _refresh_select_all_btn(self):
        self._select_all_btn.setText(
            "Deselect All" if self._all_selected() else "Select All"
        )

    def _on_select_all(self):
        deselect = self._all_selected()
        state = Qt.Unchecked if deselect else Qt.Checked
        for i in range(self._titles_tree.topLevelItemCount()):
            item = self._titles_tree.topLevelItem(i)
            item.setCheckState(0, state)
        self._refresh_select_all_btn()

    @pyqtSlot(str, int, int)
    def _on_rip_title(self, title_name: str, current: int, total: int):
        if total > 1:
            self._rip_title_label.setText(
                f"Ripping: {title_name}  ({current} of {total})")
        else:
            self._rip_title_label.setText(f"Ripping: {title_name}")
        self._rip_title_label.setVisible(True)

    def _on_rip_clicked(self):
        if self._ripping:
            self.controller.cancel_rip()
            self._set_ripping(False)
            self._status_label.setText("Cancelling…")
        else:
            self._set_ripping(True)
            self._progress_box.setVisible(True)
            self._progress_bar.setValue(0)
            self._status_label.setText("")
            self.controller.start_rip()

    @pyqtSlot(float, str)
    def _on_progress(self, fraction: float, status: str):
        self._progress_bar.setValue(int(fraction * 1000))
        self._progress_bar.setFormat(f"{fraction * 100:.0f}%")
        self._status_label.setText(status)

    @pyqtSlot(str, bool)
    def _on_rip_finished(self, disc_name: str, success: bool):
        if success:
            self._progress_bar.setValue(1000)
        self._set_ripping(False)
        self._rip_title_label.setVisible(False)
        self._status_label.setText(
            "✓ Rip complete." if success else "✗ Rip failed.")

    @pyqtSlot(str)
    def _on_libre_drive(self, message: str):
        self._libre_label.setText(f"LibreDrive: {message}")
        self._libre_label.setVisible(True)

    def _set_ripping(self, ripping: bool):
        self._ripping = ripping
        if ripping:
            self._rip_btn.setText("Cancel Ripping")
            self._rip_btn.setStyleSheet(
                "background-color: #c0392b; color: white;")
        else:
            self._rip_btn.setText("Start Ripping")
            self._rip_btn.setStyleSheet("")
            self._rip_btn.setEnabled(
                self._titles_tree.topLevelItemCount() > 0)
