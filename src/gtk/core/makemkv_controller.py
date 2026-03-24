"""
MakeMKVController — GObject that wraps makemkvcon subprocess calls.
Emits GObject signals consumed by UI views.

Signals:
    drives-updated  (list[DriveInfo])
    titles-loaded   (drive_path: str, list[TitleInfo])
    progress        (fraction: float, status: str)
    rip-started     (disc_name: str)
    rip-finished    (disc_name: str, success: bool)
    backup-progress (fraction: float, status: str)
    backup-finished (job: BackupJob)
    log-line        (level: str, text: str)
    error           (message: str)
    libre-drive     (message: str)   — emitted when "Using LibreDrive" found in output
"""

import re
import subprocess
import threading
import shutil
from typing import Optional

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, GObject, Gio

from core.models import DriveInfo, TitleInfo, BackupJob, RipJob
from core.makemkv_parser import MakeMKVParser
from core.makemkv_config import MakeMKVConfig


class MakeMKVController(GObject.Object):

    # ── Signal registration ──────────────────────────────────────────── #
    __gsignals__ = {
        "drives-updated":   (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        "titles-loaded":    (GObject.SignalFlags.RUN_FIRST, None, (str, object)),
        "progress":         (GObject.SignalFlags.RUN_FIRST, None, (float, str)),
        "rip-started":      (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "rip-title":        (GObject.SignalFlags.RUN_FIRST, None, (str, int, int)),
        "rip-finished":     (GObject.SignalFlags.RUN_FIRST, None, (str, bool)),
        "backup-progress":  (GObject.SignalFlags.RUN_FIRST, None, (float, str)),
        "backup-finished":  (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        "log-line":         (GObject.SignalFlags.RUN_FIRST, None, (str, str)),
        "error":            (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "binary-missing":   (GObject.SignalFlags.RUN_FIRST, None, ()),
        "libre-drive":      (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self):
        super().__init__()
        self._binary_missing = False
        self._binary = self._find_binary()
        self._parser = MakeMKVParser()
        self._config = MakeMKVConfig()
        self._current_rip: Optional[RipJob] = None
        self._current_backup: Optional[BackupJob] = None
        self._drives: list[DriveInfo] = []
        self._titles: list[TitleInfo] = []
        self._active_proc: Optional[subprocess.Popen] = None
        self._rip_cancelled: bool = False
        self._active_drive_index: int = 0   # set by load_disc(), used by start_rip()
        # Serialise makemkvcon invocations — only one read operation at a time
        self._op_lock = threading.Lock()
        self._scanning: bool = False
        self._loading: bool = False
        self._setup_volume_monitor()

    def _setup_volume_monitor(self):
        """
        Use Gio.VolumeMonitor to automatically detect disc insertion/removal
        without any polling.  Signals are delivered on the GLib main loop so
        it is safe to emit our own GObject signals from the callbacks.
        """
        self._volume_monitor = Gio.VolumeMonitor.get()

        # drive-changed fires when media is inserted or removed from a drive
        self._volume_monitor.connect("drive-changed",      self._on_drive_changed)

        # drive-connected / drive-disconnected handle USB drives being
        # plugged/unplugged — useful so the drive list stays current
        self._volume_monitor.connect("drive-connected",    self._on_drive_connected)
        self._volume_monitor.connect("drive-disconnected", self._on_drive_disconnected)

    # Volume monitor callbacks — all called on the GTK main thread

    def _on_drive_changed(self, monitor, drive):
        """Fired when media is inserted into or ejected from a drive."""
        self._emit_log("INFO", f"Disc change detected on: {drive.get_name()}")
        # Small delay to allow the kernel to finish reading the disc TOC
        GLib.timeout_add(1500, self._delayed_scan)

    def _on_drive_connected(self, monitor, drive):
        """Fired when a new drive is connected (e.g. USB optical drive)."""
        self._emit_log("INFO", f"Drive connected: {drive.get_name()}")
        GLib.timeout_add(500, self._delayed_scan)

    def _on_drive_disconnected(self, monitor, drive):
        """Fired when a drive is removed."""
        self._emit_log("INFO", f"Drive disconnected: {drive.get_name()}")
        GLib.timeout_add(500, self._delayed_scan)

    def _delayed_scan(self) -> bool:
        """
        Called via GLib.timeout_add — runs scan_drives() then returns False
        so GLib removes the one-shot timer.
        """
        self.scan_drives()
        return False  # do not repeat

    def cancel_rip(self):
        """
        Cancel the currently running rip. Sets a flag so the rip thread
        stops queuing further titles, then kills the active process.
        """
        self._rip_cancelled = True
        self._kill_active_proc()
        self._emit_log("WARNING", "Rip cancelled by user.")

    def shutdown(self):
        """
        Terminate any running makemkvcon process immediately.
        Call this before the application exits.
        """
        self._kill_active_proc()

    def _kill_active_proc(self):
        """SIGTERM then SIGKILL the active subprocess, if any."""
        proc = self._active_proc
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
            except Exception:
                pass
        self._active_proc = None

    # ------------------------------------------------------------------ #
    #  Binary detection                                                    #
    # ------------------------------------------------------------------ #

    def emit_binary_missing_if_needed(self):
        """Call this after the main window is shown to alert the user."""
        if self._binary_missing:
            GLib.idle_add(self.emit, "binary-missing")

    def _find_binary(self) -> str:
        path = shutil.which("makemkvcon")
        if path:
            return path
        # Flatpak / snap fallbacks
        fallbacks = [
            "/app/bin/makemkvcon",
            "/usr/bin/makemkvcon",
            "/usr/local/bin/makemkvcon",
        ]
        for p in fallbacks:
            if shutil.os.path.isfile(p):
                return p
        self._binary_missing = True
        return "makemkvcon"  # subprocess will raise FileNotFoundError

    # ------------------------------------------------------------------ #
    #  Drive scanning                                                      #
    # ------------------------------------------------------------------ #

    def scan_drives(self):
        """Non-blocking drive scan. Skips if a read operation is already running."""
        if self._scanning or self._loading:
            return
        threading.Thread(target=self._scan_drives_thread, daemon=True).start()

    def _scan_drives_thread(self):
        self._scanning = True
        try:
            result = subprocess.run(
                [self._binary, "-r", "info", "disc:9999"],
                capture_output=True, text=True,  # no timeout — scan blocks until all drives respond
            )
            drives = self._parser.parse_drives(result.stdout)
            # Fill in drive_name from settings.conf for any drive where
            # makemkvcon returned a blank name in the DRV: line.
            self._config.load()
            for i, drive in enumerate(drives):
                if not drive.drive_name:
                    drive.drive_name = self._config.get_drive_name(i)
        except FileNotFoundError:
            GLib.idle_add(self.emit, "error", "makemkvcon not found. Please install MakeMKV.")
            drives = []
        except subprocess.TimeoutExpired:
            GLib.idle_add(self.emit, "error", "Drive scan timed out.")
            drives = []
        except Exception as e:
            GLib.idle_add(self.emit, "error", str(e))
            drives = []

        self._drives = drives
        self._scanning = False
        GLib.idle_add(self.emit, "drives-updated", drives)

    # ------------------------------------------------------------------ #
    #  Disc ejecting                                                       #
    # ------------------------------------------------------------------ #

    def eject_disc(self, device_path: str = ""):
        """
        Eject the disc in the given drive (or the first known drive if blank).
        Uses 'eject' system utility — available on all major Linux distros.
        Non-blocking; emits log-line and drives-updated when done.
        """
        if not device_path:
            device_path = self._drives[0].device_path if self._drives else "/dev/sr0"
        threading.Thread(
            target=self._eject_thread, args=(device_path,), daemon=True
        ).start()

    def _eject_thread(self, device_path: str):
        self._emit_log("INFO", f"Ejecting disc at {device_path}…")
        try:
            result = subprocess.run(
                ["eject", device_path],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                self._emit_log("OK", f"Disc ejected: {device_path}")
            else:
                err = result.stderr.strip() or result.stdout.strip()
                self._emit_log("WARNING", f"Eject returned non-zero: {err}")
        except FileNotFoundError:
            self._emit_log("ERROR", "'eject' command not found. Install it with your package manager.")
        except subprocess.TimeoutExpired:
            self._emit_log("ERROR", f"Eject timed out for {device_path}")
        except Exception as e:
            self._emit_log("ERROR", str(e))
        # Re-scan drives so the UI reflects the empty tray
        self._scan_drives_thread()

    # ------------------------------------------------------------------ #
    #  Disc loading (title list)                                           #
    # ------------------------------------------------------------------ #

    def load_disc(self, drive_index: int):
        """Load title list. Skips if a scan or load is already in progress."""
        if self._scanning or self._loading:
            return
        threading.Thread(
            target=self._load_disc_thread, args=(drive_index,), daemon=True
        ).start()

    def _load_disc_thread(self, drive_index: int):
        self._loading = True
        self._emit_log("INFO", f"Reading disc at index {drive_index}…")
        device_path = next((d.device_path for d in self._drives if d.drive_index == drive_index), str(drive_index))
        try:
            result = subprocess.run(
                [self._binary, "-r", "info", f"disc:{drive_index}"],
                capture_output=True, text=True,  # no timeout — disc reads can take several minutes
            )
            titles, disc_type = self._parser.parse_titles(result.stdout)
            # Store disc type on the drive so the rip thread can pick
            # the correct 1x rate for speed calculation.
            for drive in self._drives:
                if drive.drive_index == drive_index:
                    if disc_type:
                        drive.disc_type = disc_type
                    elif not drive.disc_type:
                        # Fallback: infer from total title size
                        total_bytes = sum(t.size_bytes for t in titles)
                        drive.disc_type = "Blu-ray" if total_bytes > 4_700_000_000 else "DVD"
                    break
            for line in result.stdout.splitlines():
                level, text = self._parser.classify_line(line)
                GLib.idle_add(self.emit, "log-line", level, text)

            # Scan output for LibreDrive activity and emit signal for the UI.
            # makemkvcon prints a line containing "Using LibreDrive" when the
            # drive is running in LibreDrive mode.
            import sys
            for line in result.stdout.splitlines():
                low = line.lower()
                if any(k in low for k in ("libre", "firmware", "status", "cinfo:30", "cinfo:31", "cinfo:28")):
                    print(f"[LIBRE-DEBUG] {line}", file=sys.stderr)
                if "Using LibreDrive" in line:
                    # Extract the human-readable portion from MSG lines;
                    # fall back to the raw line if parsing fails.
                    msg = line
                    if line.startswith("MSG:"):
                        parts = self._parser._split_fields(line[4:])
                        if len(parts) >= 4:
                            msg = parts[3].strip('"')
                    GLib.idle_add(self.emit, "libre-drive", msg)
                    break

            # Extract LibreDrive status and store it on the matching drive
            libre_status = self._parser.parse_libre_drive_status(result.stdout)
            if libre_status:
                for drive in self._drives:
                    if drive.drive_index == drive_index:
                        drive.libre_drive_status = libre_status
                        break
                GLib.idle_add(self.emit, "drives-updated", list(self._drives))
        except Exception as e:
            GLib.idle_add(self.emit, "error", str(e))
            titles = []

        self._active_drive_index = drive_index
        self._titles = titles
        self._loading = False
        GLib.idle_add(self.emit, "titles-loaded", device_path, titles)

    # ------------------------------------------------------------------ #
    #  Ripping                                                             #
    # ------------------------------------------------------------------ #

    def start_rip(self):
        """Rip selected titles. Requires load_disc() to have been called."""
        selected = [t for t in self._titles if t.selected]
        if not selected:
            self.emit("error", "No titles selected.")
            return

        drive = next(
            (d for d in self._drives if d.drive_index == self._active_drive_index),
            self._drives[0] if self._drives else None,
        )
        if not drive:
            self.emit("error", "No drive selected.")
            return

        import json, os
        config_path = os.path.expanduser("~/.config/makemkv-gui/settings.json")
        dest = os.path.expanduser("~/Videos/Rips")
        try:
            with open(config_path) as f:
                dest = json.load(f).get("rip_destination", dest)
        except Exception:
            pass

        job = RipJob(
            disc_name=drive.disc_name or drive.device_path,
            drive_index=drive.drive_index,
            destination=dest,
            title_indices=[t.index for t in selected],
            custom_filenames={
                t.index: t.output_file_name.strip()
                for t in selected
                # Only treat as custom if the name differs from the
                # makemkvcon default (title_tNN.mkv).  The parser
                # pre-populates output_file_name with that default, so
                # a plain strip() check would always be True.
                if t.output_file_name.strip()
                and t.output_file_name.strip() != f"title_t{t.index:02d}.mkv"
            },
        )
        self._current_rip = job
        self._rip_cancelled = False
        self._emit_log("INFO",
            f"Ripping disc:{job.drive_index}  "
            f"titles={job.title_indices}  "
            f"dest={job.destination}")
        self.emit("rip-started", job.disc_name)
        threading.Thread(target=self._rip_thread, args=(job,), daemon=True).start()

    def _rip_thread(self, job: RipJob):
        success = True
        for i, title_idx in enumerate(job.title_indices):
            if self._rip_cancelled:
                break
            cmd = [
                self._binary, "-r",
                "--progress=-same",
                "mkv",
                f"disc:{job.drive_index}",
                str(title_idx),
                job.destination,
            ]
            title_name = next(
                (t.name for t in self._titles if t.index == title_idx),
                f"Title {title_idx + 1}",
            )
            self._emit_log("INFO", f"Ripping title {title_idx} → {job.destination}")
            GLib.idle_add(self.emit, "rip-title", title_name, i + 1, len(job.title_indices))
            # Look up the known file size for this title so parse_progress
            # can display it (PRGV total field is not the file size).
            title_size = next(
                (t.size_bytes for t in self._titles if t.index == title_idx), 0
            )
            try:
                self._active_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                proc = self._active_proc
                for line in proc.stdout:
                    line = line.rstrip()
                    level, text = self._parser.classify_line(line)
                    GLib.idle_add(self.emit, "log-line", level, text)
                    fraction, status = self._parser.parse_progress(line, title_size)
                    if fraction is not None:
                        base = i / len(job.title_indices)
                        overall = base + fraction / len(job.title_indices)
                        GLib.idle_add(self.emit, "progress", overall, status)
                proc.wait()
                self._active_proc = None
                if proc.returncode != 0:
                    success = False
                # Rename regardless of returncode — makemkvcon sometimes exits
                # non-zero on minor warnings even after writing the file.
                if title_idx in job.custom_filenames:
                    import os as _os
                    custom = job.custom_filenames[title_idx].strip()
                    if not custom.endswith(".mkv"):
                        custom += ".mkv"
                    # makemkvcon always names output title_tNN.mkv
                    # where NN is the zero-padded title index.
                    default_name = f"title_t{title_idx:02d}.mkv"
                    src_path = _os.path.join(job.destination, default_name)
                    dst_path = _os.path.join(job.destination, custom)
                    if _os.path.isfile(src_path):
                        _os.rename(src_path, dst_path)
                        self._emit_log("OK", f"Renamed: {default_name} → {custom}")
                    else:
                        self._emit_log("WARNING",
                            f"Rename skipped: {default_name} not found in {job.destination}")
            except Exception as e:
                GLib.idle_add(self.emit, "error", str(e))
                success = False

        if self._rip_cancelled:
            success = False
        GLib.idle_add(self.emit, "rip-finished", job.disc_name, success)

    # ------------------------------------------------------------------ #
    #  Backup                                                              #
    # ------------------------------------------------------------------ #

    def start_backup(self, drive_index: int, destination: str, decrypt: bool, verify: bool):
        if drive_index < 0 or drive_index >= len(self._drives):
            self.emit("error", "Invalid drive selected.")
            return
        drive = self._drives[drive_index]
        job = BackupJob(
            disc_name=drive.disc_name or drive.device_path,
            source_device=str(drive.drive_index),
            destination=destination,
            status="running",
        )
        self._current_backup = job
        threading.Thread(target=self._backup_thread, args=(job, decrypt, verify), daemon=True).start()

    def _backup_thread(self, job: BackupJob, decrypt: bool, verify: bool):
        import os
        out_dir = os.path.join(job.destination, job.disc_name.replace(" ", "_"))
        cmd = [self._binary, "-r", "--progress=-same"]
        if decrypt:
            cmd.append("--decrypt")
        cmd += ["backup", f"disc:{job.source_device}", out_dir]

        self._emit_log("INFO", f"Backup disc:{job.source_device} → {out_dir}")
        success = True
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in proc.stdout:
                line = line.rstrip()
                level, text = self._parser.classify_line(line)
                GLib.idle_add(self.emit, "log-line", level, text)
                fraction, status = self._parser.parse_progress(line)
                if fraction is not None:
                    GLib.idle_add(self.emit, "backup-progress", fraction, status)
            proc.wait()
            success = proc.returncode == 0
        except Exception as e:
            GLib.idle_add(self.emit, "error", str(e))
            success = False

        job.status = "done" if success else "failed"
        GLib.idle_add(self.emit, "backup-finished", job)

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    def _emit_log(self, level: str, text: str):
        GLib.idle_add(self.emit, "log-line", level, text)
