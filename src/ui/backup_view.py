"""
BackupView — Set up and review backup jobs.
Static structure loaded from data/ui/backup_view.ui.
Python owns only dynamic behaviour: drive list population, progress, history.
"""

import gi
import os

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw, GLib
from core.makemkv_controller import MakeMKVController
from core.models import BackupJob

_UI_FILE = "/usr/share/reel/ui/backup_view.ui"


class BackupJobRow(Adw.ActionRow):
    """Displays a single completed or in-progress backup job."""

    _STATUS_ICONS = {
        "done":    ("emblem-ok-symbolic",            ["success"]),
        "running": ("emblem-synchronizing-symbolic", ["accent"]),
        "failed":  ("dialog-error-symbolic",         ["error"]),
        "queued":  ("content-loading-symbolic",      []),
    }

    def __init__(self, job: BackupJob):
        super().__init__(
            title=job.disc_name,
            subtitle=f"{job.destination}  ·  {job.size_str}  ·  {job.timestamp}",
        )
        self.job = job
        icon_name, css = self._STATUS_ICONS.get(job.status, ("help-symbolic", []))
        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_css_classes(css)
        self.add_suffix(icon)


class BackupView(Gtk.Box):
    """Page for setting up and reviewing backup jobs."""

    def __init__(self, controller: MakeMKVController):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.controller = controller
        self._dest_path: str = os.path.expanduser("~/Videos/Backups")
        self._load_ui()
        self._build_layout()
        self._connect_signals()

    # ------------------------------------------------------------------ #
    #  Load XML                                                            #
    # ------------------------------------------------------------------ #

    def _load_ui(self):
        b = Gtk.Builder()
        b.add_from_file(_UI_FILE)

        # Static objects from backup_view.ui
        self._config_group    = b.get_object("config_group")
        self._source_row      = b.get_object("source_row")
        self._dest_row        = b.get_object("dest_row")
        self._dest_browse_btn = b.get_object("dest_browse_btn")
        self._opts_group      = b.get_object("opts_group")
        self._decrypt_row     = b.get_object("decrypt_row")
        self._verify_row      = b.get_object("verify_row")
        self._progress_group  = b.get_object("progress_group")
        self._history_group   = b.get_object("history_group")
        self._history_list    = b.get_object("history_list")
        self._empty_label     = b.get_object("empty_label")
        self._backup_btn      = b.get_object("backup_btn")

        # Attach drive string model to the source combo
        self._source_model = Gtk.StringList()
        self._source_row.set_model(self._source_model)

        # Populate the dynamic subtitle (dest path)
        self._dest_row.set_subtitle(self._dest_path)

        # Wire signals to XML-defined objects
        self._dest_row.connect("activated",         self._on_choose_destination)
        self._dest_browse_btn.connect("clicked",    self._on_choose_destination)
        self._backup_btn.connect("clicked",         self._on_backup_clicked)

    # ------------------------------------------------------------------ #
    #  Assemble layout                                                     #
    # ------------------------------------------------------------------ #

    def _build_layout(self):
        scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        self.append(scroll)

        clamp = Adw.Clamp(maximum_size=700)
        scroll.set_child(clamp)

        page_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=24,
            margin_top=18, margin_bottom=18,
        )
        clamp.set_child(page_box)

        # Dynamic progress widgets (not in XML — their values change constantly)
        self._progress_bar = Gtk.ProgressBar(show_text=True, margin_top=4, margin_bottom=4)
        self._progress_group.add(self._progress_bar)

        self._progress_label = Gtk.Label(
            label="",
            halign=Gtk.Align.START,
            css_classes=["dim-label", "caption"],
            margin_bottom=8,
        )
        self._progress_group.add(self._progress_label)

        # XML-defined groups in scroll content
        page_box.append(self._config_group)
        page_box.append(self._opts_group)
        page_box.append(self._progress_group)
        page_box.append(self._history_group)

        # Footer — backup_btn defined in XML, placed in ActionBar here
        footer = Gtk.ActionBar()
        footer.set_center_widget(self._backup_btn)
        self.append(footer)

    # ------------------------------------------------------------------ #
    #  Signal connections                                                  #
    # ------------------------------------------------------------------ #

    def _connect_signals(self):
        self.controller.connect("drives-updated",  self._on_drives_updated)
        self.controller.connect("backup-progress", self._on_backup_progress)
        self.controller.connect("backup-finished", self._on_backup_finished)

    # ------------------------------------------------------------------ #
    #  Callbacks                                                           #
    # ------------------------------------------------------------------ #

    def _on_drives_updated(self, _ctrl, drives):
        while self._source_model.get_n_items() > 0:
            self._source_model.remove(0)
        for drive in drives:
            label = (
                f"{drive.device_path} — "
                f"{drive.disc_name if drive.has_disc else 'Empty'}"
            )
            self._source_model.append(label)
        self._backup_btn.set_sensitive(bool(drives))

    def _on_choose_destination(self, *_):
        dialog = Gtk.FileDialog(title="Choose Backup Destination")
        dialog.select_folder(
            parent=self.get_root(),
            cancellable=None,
            callback=self._on_folder_chosen,
        )

    def _on_folder_chosen(self, dialog, result):
        try:
            folder = dialog.select_folder_finish(result)
            if folder:
                self._dest_path = folder.get_path()
                self._dest_row.set_subtitle(self._dest_path)
        except Exception:
            pass

    def _on_backup_clicked(self, _btn):
        self.controller.start_backup(
            drive_index=self._source_row.get_selected(),
            destination=self._dest_path,
            decrypt=self._decrypt_row.get_active(),
            verify=self._verify_row.get_active(),
        )
        self._progress_group.set_visible(True)
        self._backup_btn.set_sensitive(False)

    def _on_backup_progress(self, _ctrl, fraction: float, status: str):
        self._progress_bar.set_fraction(fraction)
        self._progress_label.set_text(status)

    def _on_backup_finished(self, _ctrl, job: BackupJob):
        self._progress_group.set_visible(False)
        self._backup_btn.set_sensitive(True)
        # Remove placeholder label on first real entry
        if self._empty_label.get_parent():
            self._history_list.remove(self._empty_label)
        self._history_list.prepend(BackupJobRow(job))
