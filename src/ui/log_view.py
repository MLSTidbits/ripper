"""
LogView — Scrollable, colour-coded log output from MakeMKV.
Static structure loaded from data/ui/log_view.ui.
Python owns only dynamic behaviour: text tags, appending lines, search, save.
"""

import gi
import os
import datetime

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw, GLib, Pango
from core.makemkv_controller import MakeMKVController

_UI_FILE = "/usr/share/reel/ui/log_view.ui"

# Maps controller log level → (CSS tag name, line prefix)
_LEVEL_STYLE = {
    "INFO":    ("",        ""),
    "OK":      ("success", "✓ "),
    "WARNING": ("warning", "⚠ "),
    "ERROR":   ("error",   "✗ "),
    "DEBUG":   ("dim",     "[DBG] "),
}

# TextBuffer tag name → property dict
_TEXT_TAGS = {
    "success": {"foreground": "#57e389"},
    "warning": {"foreground": "#f8e45c"},
    "error":   {"foreground": "#ff7b63", "weight": Pango.Weight.BOLD},
    "dim":     {"foreground": "#9a9996"},
    "accent":  {"foreground": "#78aeed"},
    "ts":      {"foreground": "#9a9996", "scale": 0.85},
}


class LogView(Gtk.Box):
    """Full-width log output page with search and export."""

    def __init__(self, controller: MakeMKVController):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.controller = controller
        self._log_lines: list[tuple[str, str]] = []   # (level, text)
        self._load_ui()
        self._build_layout()
        self._connect_signals()

    # ------------------------------------------------------------------ #
    #  Load XML                                                            #
    # ------------------------------------------------------------------ #

    def _load_ui(self):
        b = Gtk.Builder()
        b.add_from_file(_UI_FILE)

        # Static objects from log_view.ui
        self._search_bar       = b.get_object("search_bar")
        self._search_entry     = b.get_object("search_entry")
        self._text_view        = b.get_object("text_view")
        self._line_count_label = b.get_object("line_count_label")

        # Connect search bar to its entry (GtkSearchBar API requires this)
        self._search_bar.connect_entry(self._search_entry)
        self._search_entry.connect("search-changed", self._on_search_changed)

    # ------------------------------------------------------------------ #
    #  Assemble layout                                                     #
    # ------------------------------------------------------------------ #

    def _build_layout(self):
        # Search bar (defined in XML) sits at the top
        self.append(self._search_bar)

        # Scrolled text view — text_view defined in XML, scroll container here
        scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        scroll.set_child(self._text_view)
        self.append(scroll)

        # Build TextBuffer tags (colour values — not static string content)
        self._buffer = self._text_view.get_buffer()
        tag_table = self._buffer.get_tag_table()
        for name, props in _TEXT_TAGS.items():
            tag = Gtk.TextTag(name=name)
            for k, v in props.items():
                tag.set_property(k, v)
            tag_table.add(tag)

        # Status bar with line counter (defined in XML)
        status_bar = Gtk.ActionBar()
        status_bar.pack_start(self._line_count_label)
        self.append(status_bar)

    # ------------------------------------------------------------------ #
    #  Signal connections                                                  #
    # ------------------------------------------------------------------ #

    def _connect_signals(self):
        self.controller.connect("log-line", self._on_log_line)

    # ------------------------------------------------------------------ #
    #  Public API (called from MainWindow header buttons)                  #
    # ------------------------------------------------------------------ #

    def append_line(self, level: str, text: str):
        self._log_lines.append((level, text))
        self._render_line(level, text)
        self._line_count_label.set_text(f"{len(self._log_lines)} lines")
        self._scroll_to_end()

    def _on_save_log(self, _btn):
        dialog = Gtk.FileDialog(title="Save Log File", initial_name="makemkv.log")
        dialog.save(
            parent=self.get_root(),
            cancellable=None,
            callback=self._on_save_chosen,
        )

    def _on_clear(self, _btn):
        self._buffer.set_text("")
        self._log_lines.clear()
        self._line_count_label.set_text("0 lines")

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _render_line(self, level: str, text: str):
        tag_name, prefix = _LEVEL_STYLE.get(level, ("", ""))
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        end = self._buffer.get_end_iter()
        self._buffer.insert_with_tags_by_name(end, f"[{ts}] ", "ts")
        msg = f"{prefix}{text}\n"
        if tag_name:
            self._buffer.insert_with_tags_by_name(end, msg, tag_name)
        else:
            self._buffer.insert(end, msg)

    def _scroll_to_end(self):
        end = self._buffer.get_end_iter()
        mark = self._buffer.create_mark(None, end, False)
        self._text_view.scroll_to_mark(mark, 0.0, True, 0.0, 1.0)

    # ------------------------------------------------------------------ #
    #  Callbacks                                                           #
    # ------------------------------------------------------------------ #

    def _on_log_line(self, _ctrl, level: str, text: str):
        GLib.idle_add(self.append_line, level, text)

    def _on_search_changed(self, entry):
        pass  # TODO: highlight matching lines

    def _on_save_chosen(self, dialog, result):
        try:
            f = dialog.save_finish(result)
            if f:
                content = "\n".join(
                    f"[{lvl}] {txt}" for lvl, txt in self._log_lines
                )
                with open(f.get_path(), "w") as fh:
                    fh.write(content)
        except Exception:
            pass
