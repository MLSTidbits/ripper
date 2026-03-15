"""
BackupView — Disc backup job setup and history.
"""

import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QCheckBox, QLineEdit, QFileDialog, QScrollArea,
    QFrame, QTableWidget, QTableWidgetItem, QHeaderView,
    QProgressBar, QAbstractItemView, QComboBox,
)
from PyQt5.QtCore import Qt, pyqtSlot

from core.makemkv_controller import MakeMKVController
from core.models import BackupJob


class BackupView(QWidget):
    """Backup job setup and history."""

    def __init__(self, controller: MakeMKVController, parent=None):
        super().__init__(parent)
        self.controller = controller
        self._jobs: list[BackupJob] = []
        self._build_ui()
        self._connect_signals()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

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

        # ── Drive selector ── #
        drive_box = QGroupBox("Source Drive")
        drive_layout = QVBoxLayout(drive_box)
        self._drive_combo = QComboBox()
        drive_layout.addWidget(self._drive_combo)
        layout.addWidget(drive_box)

        # ── Destination ── #
        dest_box = QGroupBox("Destination")
        dest_layout = QHBoxLayout(dest_box)
        self._dest_edit = QLineEdit()
        self._dest_edit.setPlaceholderText("Select output folder…")
        dest_layout.addWidget(self._dest_edit)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._on_browse)
        dest_layout.addWidget(browse_btn)
        layout.addWidget(dest_box)

        # ── Options ── #
        opts_box = QGroupBox("Options")
        opts_layout = QVBoxLayout(opts_box)
        self._decrypt_check = QCheckBox("Decrypt disc content")
        self._decrypt_check.setChecked(True)
        opts_layout.addWidget(self._decrypt_check)
        self._verify_check = QCheckBox("Verify after backup")
        opts_layout.addWidget(self._verify_check)
        layout.addWidget(opts_box)

        # ── Progress ── #
        self._progress_box = QGroupBox("Progress")
        prog_layout = QVBoxLayout(self._progress_box)
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 1000)
        prog_layout.addWidget(self._progress_bar)
        self._progress_status = QLabel()
        self._progress_status.setStyleSheet(
            "color: palette(mid); font-size: 12px;")
        prog_layout.addWidget(self._progress_status)
        self._progress_box.setVisible(False)
        layout.addWidget(self._progress_box)

        # ── History ── #
        hist_box = QGroupBox("Backup History")
        hist_layout = QVBoxLayout(hist_box)
        self._history_table = QTableWidget(0, 4)
        self._history_table.setHorizontalHeaderLabels(
            ["Disc", "Destination", "Status", "Date"])
        self._history_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        self._history_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch)
        self._history_table.setEditTriggers(
            QAbstractItemView.NoEditTriggers)
        self._history_table.setAlternatingRowColors(True)
        self._history_table.setSelectionBehavior(
            QAbstractItemView.SelectRows)
        hist_layout.addWidget(self._history_table)
        layout.addWidget(hist_box)
        layout.addStretch()

        # ── Footer ── #
        footer = QFrame()
        footer.setFrameShape(QFrame.StyledPanel)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(12, 6, 12, 6)
        footer_layout.addStretch()
        self._backup_btn = QPushButton("Start Backup")
        self._backup_btn.setFixedWidth(160)
        self._backup_btn.setEnabled(False)
        self._backup_btn.clicked.connect(self._on_backup_clicked)
        footer_layout.addWidget(self._backup_btn)
        footer_layout.addStretch()
        root.addWidget(footer)

    def _connect_signals(self):
        self.controller.drives_updated.connect(self._on_drives_updated)
        self.controller.backup_progress.connect(self._on_backup_progress)
        self.controller.backup_finished.connect(self._on_backup_finished)

    @pyqtSlot(list)
    def _on_drives_updated(self, drives: list):
        self._drive_combo.clear()
        for drive in drives:
            label = (f"{drive.drive_name or drive.device_path}"
                     f"  ·  {drive.disc_name}" if drive.has_disc
                     else drive.drive_name or drive.device_path)
            self._drive_combo.addItem(label, userData=drive)
        self._backup_btn.setEnabled(bool(drives))

    def _on_browse(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select Backup Destination",
            os.path.expanduser("~/Videos"))
        if path:
            self._dest_edit.setText(path)

    def _on_backup_clicked(self):
        drive = self._drive_combo.currentData()
        if not drive:
            return
        dest = self._dest_edit.text().strip()
        if not dest:
            dest = os.path.expanduser("~/Videos/Backups")
        self._progress_box.setVisible(True)
        self._progress_bar.setValue(0)
        self.controller.start_backup(
            drive.drive_index, dest,
            self._decrypt_check.isChecked(),
            self._verify_check.isChecked(),
        )

    @pyqtSlot(float, str)
    def _on_backup_progress(self, fraction: float, status: str):
        self._progress_bar.setValue(int(fraction * 1000))
        self._progress_bar.setFormat(f"{fraction * 100:.0f}%")
        self._progress_status.setText(status)

    @pyqtSlot(object)
    def _on_backup_finished(self, job: BackupJob):
        self._progress_bar.setValue(1000 if job.status == "done" else
                                    self._progress_bar.value())
        self._progress_status.setText(
            "✓ Backup complete." if job.status == "done" else "✗ Backup failed.")
        self._jobs.append(job)
        row = self._history_table.rowCount()
        self._history_table.insertRow(row)
        self._history_table.setItem(row, 0, QTableWidgetItem(job.disc_name))
        self._history_table.setItem(row, 1, QTableWidgetItem(job.destination))
        self._history_table.setItem(row, 2, QTableWidgetItem(job.status))
        self._history_table.setItem(row, 3, QTableWidgetItem(job.timestamp))
