"""
LogView — Colour-coded makemkvcon output log.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit,
    QPushButton, QLineEdit, QFrame, QFileDialog,
)
from PyQt6.QtGui import QTextCharFormat, QColor, QFont, QTextCursor
from PyQt6.QtCore import Qt, pyqtSlot

from core.makemkv_controller import MakeMKVController

_LEVEL_COLORS = {
    "OK":      "#2ecc71",
    "WARNING": "#f39c12",
    "ERROR":   "#e74c3c",
    "DEBUG":   "#7f8c8d",
    "INFO":    "",   # default text color
}


class LogView(QWidget):
    """Colour-coded scrolling log output with search."""

    def __init__(self, controller: MakeMKVController, parent=None):
        super().__init__(parent)
        self.controller = controller
        self._build_ui()
        self._connect_signals()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Search bar
        self._search_bar = QWidget()
        search_layout = QHBoxLayout(self._search_bar)
        search_layout.setContentsMargins(8, 4, 8, 4)
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search log…")
        self._search_edit.textChanged.connect(self._on_search)
        search_layout.addWidget(self._search_edit)
        close_btn = QPushButton("✕")
        close_btn.setFixedWidth(28)
        close_btn.setFlat(True)
        close_btn.clicked.connect(lambda: self._toggle_search(False))
        search_layout.addWidget(close_btn)
        self._search_bar.setVisible(False)
        root.addWidget(self._search_bar)

        # Log output
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(QFont("monospace", 10))
        self._log.setMaximumBlockCount(5000)
        root.addWidget(self._log)

    def _connect_signals(self):
        self.controller.log_line.connect(self._on_log_line)

    # ── Public API (called from MainWindow header buttons) ── #

    def toggle_search(self):
        self._toggle_search(not self._search_bar.isVisible())

    def save_log(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Log", "reel.log", "Text files (*.log *.txt);;All files (*)")
        if path:
            with open(path, "w") as f:
                f.write(self._log.toPlainText())

    def clear_log(self):
        self._log.clear()

    # ── Slots ── #

    @pyqtSlot(str, str)
    def _on_log_line(self, level: str, text: str):
        fmt = QTextCharFormat()
        color = _LEVEL_COLORS.get(level, "")
        if color:
            fmt.setForeground(QColor(color))
        if level in ("ERROR", "WARNING"):
            fmt.setFontWeight(QFont.Weight.Bold)
        cursor = self._log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(f"[{level}] {text}\n", fmt)
        self._log.setTextCursor(cursor)
        self._log.ensureCursorVisible()

    def _toggle_search(self, visible: bool):
        self._search_bar.setVisible(visible)
        if visible:
            self._search_edit.setFocus()
        else:
            self._search_edit.clear()

    def _on_search(self, text: str):
        if not text:
            return
        self._log.find(text)
