#!/usr/bin/env python3
"""
Reel — Qt5 frontend for MakeMKV
Entry point.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon
from ui.main_window import MainWindow

APP_ID = "com.MLSTidbits.Reel"


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Reel")
    app.setApplicationDisplayName("Reel")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("Reel")
    app.setDesktopFileName(APP_ID)
    app.setWindowIcon(QIcon("/usr/share/icons/hicolor/scalable/apps/reel.svg"))

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
