"""
DiscView — Shows detected optical drives, disc info, and title list.
Static structure (groups, lists, buttons) loaded from data/ui/disc_view.ui.
Python owns only dynamic behaviour: signals, list population, progress updates.
"""

import gi
import os

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw, GLib
from core.makemkv_controller import MakeMKVController
from core.models import DriveInfo, TitleInfo

_UI_FILE = "/usr/share/reel/ui/disc_view.ui"

MARGIN_H = 24
MARGIN_V = 16


# ── Reusable row widgets ───────────────────────────────────────────────── #

class TitleRow(Adw.ExpanderRow):
    """Expands to show an inline output-filename editor."""

    def __init__(self, title: TitleInfo):
        super().__init__(
            title=title.name,
            subtitle=(
                f"{title.duration}  ·  {title.size_str}"
                f"  ·  {title.chapter_count} chapters"
            ),
            show_enable_switch=False,
        )
        self.title_info = title

        self._check = Gtk.CheckButton(active=title.selected)
        self._check.connect("toggled", self._on_toggled)
        self.add_prefix(self._check)

        filename_row = Adw.ActionRow(
            title="Output filename",
            subtitle="Leave blank to use the default from MakeMKV",
        )
        self._filename_entry = Gtk.Entry(
            text=title.output_file_name,
            placeholder_text=f"e.g. {title.name.replace(' ', '_')}.mkv",
            hexpand=True,
            valign=Gtk.Align.CENTER,
        )
        self._filename_entry.set_icon_from_icon_name(
            Gtk.EntryIconPosition.SECONDARY, "edit-clear-symbolic"
        )
        self._filename_entry.set_icon_tooltip_text(
            Gtk.EntryIconPosition.SECONDARY, "Reset to default"
        )
        self._filename_entry.connect("changed",    self._on_filename_changed)
        self._filename_entry.connect("icon-press", self._on_clear_filename)
        filename_row.add_suffix(self._filename_entry)
        filename_row.set_activatable_widget(self._filename_entry)
        self.add_row(filename_row)

    def _on_toggled(self, btn):
        self.title_info.selected = btn.get_active()
        parent = self.get_parent()
        while parent and not isinstance(parent, DiscView):
            parent = parent.get_parent()
        if parent:
            parent._refresh_select_all_btn()

    def _on_filename_changed(self, entry):
        self.title_info.output_file_name = entry.get_text().strip()

    def _on_clear_filename(self, entry, _pos):
        entry.set_text("")
        self.title_info.output_file_name = ""


class DriveRow(Adw.ActionRow):
    """One row per detected optical drive."""

    _LIBRE_STYLE = {
        "enabled":     ("success", "LibreDrive ✓"),
        "possible":    ("warning", "LibreDrive possible"),
        "not support": ("error",   "LibreDrive unsupported"),
    }

    def __init__(self, drive: DriveInfo):
        subtitle = (
            f"{drive.disc_name}  ·  {drive.device_path}"
            if drive.has_disc else drive.device_path
        )
        super().__init__(
            title=drive.drive_name or drive.device_path,
            subtitle=subtitle,
            activatable=True,
        )
        self.drive_info = drive
        self.add_prefix(Gtk.Image.new_from_icon_name(
            "media-optical-dvd" if drive.has_disc else "drive-optical"
        ))
        if drive.libre_drive_status:
            self.add_suffix(self._libre_badge(drive.libre_drive_status))

    def _libre_badge(self, status: str) -> Gtk.Label:
        css, text = "dim-label", f"LibreDrive: {status}"
        for key, (style, short) in self._LIBRE_STYLE.items():
            if key in status.lower():
                css, text = style, short
                break
        return Gtk.Label(
            label=text,
            valign=Gtk.Align.CENTER,
            css_classes=["caption", "pill", css],
            tooltip_text=status,
        )


# ── Main view ─────────────────────────────────────────────────────────── #

class DiscView(Gtk.Box):
    """Drive picker → title list → rip controls."""

    def __init__(self, controller: MakeMKVController):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.controller = controller
        self._load_ui()
        self._build_layout()
        self._connect_signals()

    # ------------------------------------------------------------------ #
    #  Load XML                                                            #
    # ------------------------------------------------------------------ #

    def _load_ui(self):
        b = Gtk.Builder()
        b.add_from_file(_UI_FILE)

        # Named objects from disc_view.ui
        self._drives_group   = b.get_object("drives_group")
        self._drives_list    = b.get_object("drives_list")
        self._disc_info_bar  = b.get_object("disc_info_bar")
        self._titles_group   = b.get_object("titles_group")
        self._titles_list    = b.get_object("titles_list")
        self._select_all_btn = b.get_object("select_all_btn")
        self._progress_group = b.get_object("progress_group")
        self._rip_btn        = b.get_object("rip_btn")
        self._rip_title_label    = b.get_object("rip_title_label")

        # Wire signals to XML-defined objects
        self._drives_list.connect("row-activated", self._on_drive_selected)
        self._select_all_btn.connect("clicked",    self._on_select_all)

        # Track which clicked handler is active so _set_ripping can swap them
        self._rip_handler_id    = None
        self._cancel_handler_id = None
        self._set_ripping(False)   # wires _on_rip_clicked as the initial handler

    # ------------------------------------------------------------------ #
    #  Assemble layout (only dynamic/container widgets built here)         #
    # ------------------------------------------------------------------ #

    def _build_layout(self):
        scroll = Gtk.ScrolledWindow(
            vexpand=True,
            hscrollbar_policy=Gtk.PolicyType.NEVER,
        )
        self.append(scroll)

        clamp = Adw.Clamp(maximum_size=860, tightening_threshold=600)
        scroll.set_child(clamp)

        content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=MARGIN_V,
            margin_start=MARGIN_H, margin_end=MARGIN_H,
            margin_top=MARGIN_V,   margin_bottom=MARGIN_V,
        )
        clamp.set_child(content)

        # "Select All" is defined in XML; attach as header suffix now it's parented
        self._titles_group.set_header_suffix(self._select_all_btn)

        content.append(self._drives_group)

        # LibreDrive status label — hidden until "Using LibreDrive" seen in output
        self._libre_label = Gtk.Label(
            label="",
            halign=Gtk.Align.START,
            margin_start=4,
            visible=False,
        )
        self._libre_label.add_css_class("success")
        self._libre_label.add_css_class("caption")
        content.append(self._libre_label)

        content.append(self._disc_info_bar)
        content.append(self._titles_group)

        # Progress widgets (purely dynamic — not in XML)
        progress_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=4,
            margin_top=4, margin_bottom=8,
            margin_start=4, margin_end=4,
        )
        self._scale = Gtk.Scale(
            orientation=Gtk.Orientation.HORIZONTAL,
            draw_value=True,
            value_pos=Gtk.PositionType.RIGHT,
            hexpand=True,
            sensitive=False,
        )
        self._scale.set_range(0, 100)
        self._scale.set_value(0)
        self._scale.set_format_value_func(lambda _s, v: f"{v:.0f}%")
        progress_box.append(self._rip_title_label)
        progress_box.append(self._scale)

        self._status_label = Gtk.Label(
            label="",
            css_classes=["dim-label", "caption"],
            halign=Gtk.Align.START,
        )
        progress_box.append(self._status_label)
        self._progress_group.add(progress_box)
        content.append(self._progress_group)

        # Footer action bar — rip_btn defined in XML, placed here
        footer = Gtk.ActionBar()
        footer.set_center_widget(self._rip_btn)
        self.append(footer)

    # ------------------------------------------------------------------ #
    #  Signal connections                                                  #
    # ------------------------------------------------------------------ #

    def _connect_signals(self):
        self.controller.connect("drives-updated", self._on_drives_updated)
        self.controller.connect("titles-loaded",  self._on_titles_loaded)
        self.controller.connect("progress",       self._on_progress)
        self.controller.connect("rip-finished",   self._on_rip_finished)
        self.controller.connect("rip-title",      self._on_rip_title)
        self.controller.connect("libre-drive",    self._on_libre_drive)

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def refresh_drives(self):
        self.controller.scan_drives()

    def clear(self):
        """Reset to empty state (called on disc eject)."""
        self._clear_list(self._titles_list)
        self._disc_info_bar.set_title(
            "Select a drive above to load disc information"
        )
        self._progress_group.set_visible(False)
        self._scale.set_value(0)
        self._status_label.set_text("")
        self._rip_title_label.set_text("")
        self._rip_title_label.set_visible(False)
        self._set_ripping(False)
        self._rip_btn.set_sensitive(False)

    # ------------------------------------------------------------------ #
    #  Callbacks                                                           #
    # ------------------------------------------------------------------ #

    def _on_libre_drive(self, _ctrl, message: str):
        """Show the LibreDrive status message below the drives list."""
        self._libre_label.set_label(message)
        self._libre_label.set_visible(True)

    def _on_drives_updated(self, _ctrl, drives: list):
        self._libre_label.set_visible(False)
        self._libre_label.set_label("")
        self._clear_list(self._drives_list)
        if drives:
            for drive in drives:
                self._drives_list.append(DriveRow(drive))
        else:
            self._drives_list.append(
                Adw.ActionRow(title="No optical drives detected")
            )
            self.clear()

    def _on_drive_selected(self, _lb, row):
        if not isinstance(row, DriveRow) or not row.drive_info.has_disc:
            return
        self._disc_info_bar.set_title(
            f"Loading disc {row.drive_info.drive_index}…"
        )
        self.controller.load_disc(row.drive_info.drive_index)

    def _on_titles_loaded(self, _ctrl, drive_path: str, titles: list):
        self._clear_list(self._titles_list)
        disc_name = titles[0].disc_name if titles else drive_path
        self._disc_info_bar.set_title(
            f"Disc: {disc_name}  ·  {len(titles)} titles found"
        )
        for title in titles:
            self._titles_list.append(TitleRow(title))
        self._rip_btn.set_sensitive(bool(titles))
        self._refresh_select_all_btn()

    def _all_selected(self) -> bool:
        row = self._titles_list.get_first_child()
        found_any = False
        while row:
            if isinstance(row, TitleRow):
                found_any = True
                if not row._check.get_active():
                    return False
            row = row.get_next_sibling()
        return found_any

    def _refresh_select_all_btn(self):
        if self._all_selected():
            self._select_all_btn.set_label("Deselect All")
        else:
            self._select_all_btn.set_label("Select All")

    def _on_select_all(self, _btn):
        deselect = self._all_selected()
        row = self._titles_list.get_first_child()
        while row:
            if isinstance(row, TitleRow):
                row.title_info.selected = not deselect
                row._check.set_active(not deselect)
            row = row.get_next_sibling()
        self._refresh_select_all_btn()

    def _on_rip_title(self, _ctrl, title_name: str, current: int, total: int):
        if total > 1:
            self._rip_title_label.set_text(f"Ripping: {title_name}  ({current} of {total})")
        else:
            self._rip_title_label.set_text(f"Ripping: {title_name}")
        self._rip_title_label.set_visible(True)

    def _on_rip_clicked(self, _btn):
        self._set_ripping(True)
        self._progress_group.set_visible(True)
        self._scale.set_value(0)
        self._status_label.set_text("")
        self._rip_title_label.set_text("")
        self._rip_title_label.set_visible(True)
        self.controller.start_rip()

    def _on_cancel_clicked(self, _btn):
        self.controller.cancel_rip()
        self._set_ripping(False)
        self._status_label.set_text("Cancelling…")

    def _on_progress(self, _ctrl, fraction: float, status_text: str):
        self._scale.set_value(fraction * 100)
        self._status_label.set_text(status_text)

    def _on_rip_finished(self, _ctrl, disc_name: str, success: bool):
        self._scale.set_value(100 if success else self._scale.get_value())
        self._set_ripping(False)
        self._rip_title_label.set_visible(False)
        self._status_label.set_text(
            "✓ Rip complete." if success else "✗ Rip failed."
        )

    def _set_ripping(self, ripping: bool):
        """Toggle the footer button between Start Ripping and Cancel Ripping."""
        btn = self._rip_btn
        # Disconnect whichever handler is currently active
        for attr in ("_rip_handler_id", "_cancel_handler_id"):
            hid = getattr(self, attr, None)
            if hid is not None:
                try:
                    btn.disconnect(hid)
                except Exception:
                    pass
        if ripping:
            btn.set_label("Cancel Ripping")
            btn.remove_css_class("suggested-action")
            btn.add_css_class("destructive-action")
            self._cancel_handler_id = btn.connect("clicked", self._on_cancel_clicked)
            self._rip_handler_id = None
            btn.set_sensitive(True)
        else:
            btn.set_label("Start Ripping")
            btn.remove_css_class("destructive-action")
            btn.add_css_class("suggested-action")
            self._rip_handler_id = btn.connect("clicked", self._on_rip_clicked)
            self._cancel_handler_id = None
            # Keep sensitive only if titles are loaded
            has_titles = self._titles_list.get_first_child() is not None
            btn.set_sensitive(has_titles)

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _clear_list(listbox: Gtk.ListBox):
        child = listbox.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            listbox.remove(child)
            child = nxt
