"""
MakeMKVController — QObject wrapping makemkvcon subprocess calls.
Emits Qt signals consumed by UI views.

Signals:
    drives_updated  (list)
    titles_loaded   (str, list)
    progress        (float, str)
    rip_started     (str)
    rip_title       (str, int, int)
    rip_finished    (str, bool)
    backup_progress (float, str)
    backup_finished (object)
    log_line        (str, str)
    error           (str)
    binary_missing  ()
    libre_drive     (str)
"""

import shutil
import subprocess
import threading
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal, QMetaObject, Qt

from core.models import DriveInfo, TitleInfo, BackupJob, RipJob
from core.makemkv_parser import MakeMKVParser
from core.makemkv_config import MakeMKVConfig


class MakeMKVController(QObject):

    # ── Signals ─────────────────────────────────────────────────────── #
    drives_updated  = pyqtSignal(list)
    titles_loaded   = pyqtSignal(str, list)
    progress        = pyqtSignal(float, str)
    rip_started     = pyqtSignal(str)
    rip_title       = pyqtSignal(str, int, int)
    rip_finished    = pyqtSignal(str, bool)
    backup_progress = pyqtSignal(float, str)
    backup_finished = pyqtSignal(object)
    log_line        = pyqtSignal(str, str)
    error           = pyqtSignal(str)
    binary_missing  = pyqtSignal()
    libre_drive     = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
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
        self._active_drive_index: int = 0

    # ------------------------------------------------------------------ #
    #  Thread-safe emit helper                                             #
    # ------------------------------------------------------------------ #

    def _emit(self, signal_name: str, *args):
        """Emit a signal safely from any thread via Qt's queued connection."""
        QMetaObject.invokeMethod(
            self,
            "_emit_slot",
            Qt.ConnectionType.QueuedConnection,
            signal_name,
            *args,
        )

    def _emit_main(self, signal: pyqtSignal, *args):
        """
        Emit a signal on the main thread from a worker thread.
        Uses a lambda queued to the main event loop via invokeMethod.
        """
        QMetaObject.invokeMethod(
            self,
            lambda: signal.emit(*args),
            Qt.ConnectionType.QueuedConnection,
        )

    def _queue(self, fn):
        """Run fn() on the main thread from any thread."""
        QMetaObject.invokeMethod(
            self, fn, Qt.ConnectionType.QueuedConnection
        )

    # ------------------------------------------------------------------ #
    #  Binary detection                                                    #
    # ------------------------------------------------------------------ #

    def emit_binary_missing_if_needed(self):
        if self._binary_missing:
            self._queue(lambda: self.binary_missing.emit())

    def _find_binary(self) -> str:
        path = shutil.which("makemkvcon")
        if path:
            return path
        for p in ("/app/bin/makemkvcon", "/usr/bin/makemkvcon",
                  "/usr/local/bin/makemkvcon"):
            if shutil.os.path.isfile(p):
                return p
        self._binary_missing = True
        return "makemkvcon"

    # ------------------------------------------------------------------ #
    #  Drive scanning                                                      #
    # ------------------------------------------------------------------ #

    def scan_drives(self):
        threading.Thread(target=self._scan_drives_thread, daemon=True).start()

    def _scan_drives_thread(self):
        try:
            result = subprocess.run(
                [self._binary, "-r", "info", "disc:9999"],
                capture_output=True, text=True,
            )
            drives = self._parser.parse_drives(result.stdout)
            self._config.load()
            for i, drive in enumerate(drives):
                if not drive.drive_name:
                    drive.drive_name = self._config.get_drive_name(i)
        except FileNotFoundError:
            drives = []
            self._queue(lambda: self.error.emit(
                "makemkvcon not found. Please install MakeMKV."))
        except Exception as e:
            drives = []
            self._queue(lambda: self.error.emit(str(e)))

        self._drives = drives
        _d = list(drives)
        self._queue(lambda: self.drives_updated.emit(_d))

    # ------------------------------------------------------------------ #
    #  Disc ejecting                                                       #
    # ------------------------------------------------------------------ #

    def eject_disc(self, device_path: str = ""):
        if not device_path:
            device_path = self._drives[0].device_path if self._drives else "/dev/sr0"
        threading.Thread(
            target=self._eject_thread, args=(device_path,), daemon=True
        ).start()

    def _eject_thread(self, device_path: str):
        self._log("INFO", f"Ejecting disc at {device_path}…")
        try:
            result = subprocess.run(
                ["eject", device_path],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                self._log("OK", f"Disc ejected: {device_path}")
            else:
                self._log("WARNING", f"Eject error: {result.stderr.strip()}")
        except FileNotFoundError:
            self._log("ERROR", "'eject' command not found.")
        except subprocess.TimeoutExpired:
            self._log("ERROR", f"Eject timed out for {device_path}")
        except Exception as e:
            self._log("ERROR", str(e))
        self._scan_drives_thread()

    # ------------------------------------------------------------------ #
    #  Disc loading                                                        #
    # ------------------------------------------------------------------ #

    def load_disc(self, drive_index: int):
        threading.Thread(
            target=self._load_disc_thread, args=(drive_index,), daemon=True
        ).start()

    def _load_disc_thread(self, drive_index: int):
        self._log("INFO", f"Reading disc at index {drive_index}…")
        device_path = next(
            (d.device_path for d in self._drives if d.drive_index == drive_index),
            str(drive_index)
        )
        try:
            result = subprocess.run(
                [self._binary, "-r", "info", f"disc:{drive_index}"],
                capture_output=True, text=True,
            )
            titles, disc_type = self._parser.parse_titles(result.stdout)

            for drive in self._drives:
                if drive.drive_index == drive_index:
                    if disc_type:
                        drive.disc_type = disc_type
                    elif not drive.disc_type:
                        total = sum(t.size_bytes for t in titles)
                        drive.disc_type = "Blu-ray" if total > 4_700_000_000 else "DVD"
                    break

            for line in result.stdout.splitlines():
                level, text = self._parser.classify_line(line)
                _l, _t = level, text
                self._queue(lambda l=_l, t=_t: self.log_line.emit(l, t))

            # LibreDrive detection
            for line in result.stdout.splitlines():
                if "Using LibreDrive" in line:
                    msg = line
                    if line.startswith("MSG:"):
                        parts = self._parser._split_fields(line[4:])
                        if len(parts) >= 4:
                            msg = parts[3].strip('"')
                    _msg = msg
                    self._queue(lambda m=_msg: self.libre_drive.emit(m))
                    break

            libre_status = self._parser.parse_libre_drive_status(result.stdout)
            if libre_status:
                for drive in self._drives:
                    if drive.drive_index == drive_index:
                        drive.libre_drive_status = libre_status
                        break
                _d = list(self._drives)
                self._queue(lambda: self.drives_updated.emit(_d))

        except Exception as e:
            titles = []
            _e = str(e)
            self._queue(lambda: self.error.emit(_e))

        self._active_drive_index = drive_index
        self._titles = titles
        _dp, _t = device_path, titles
        self._queue(lambda: self.titles_loaded.emit(_dp, _t))

    # ------------------------------------------------------------------ #
    #  Ripping                                                             #
    # ------------------------------------------------------------------ #

    def start_rip(self):
        selected = [t for t in self._titles if t.selected]
        if not selected:
            self.error.emit("No titles selected.")
            return

        drive = next(
            (d for d in self._drives if d.drive_index == self._active_drive_index),
            self._drives[0] if self._drives else None,
        )
        if not drive:
            self.error.emit("No drive selected.")
            return

        import json, os
        config_path = os.path.expanduser("~/.config/reel/settings.json")
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
                if t.output_file_name.strip()
                and t.output_file_name.strip() != f"title_t{t.index:02d}.mkv"
            },
        )
        self._current_rip = job
        self._rip_cancelled = False
        self._log("INFO",
            f"Ripping disc:{job.drive_index} titles={job.title_indices} dest={job.destination}")
        self.rip_started.emit(job.disc_name)
        threading.Thread(target=self._rip_thread, args=(job,), daemon=True).start()

    def cancel_rip(self):
        self._rip_cancelled = True
        self._kill_active_proc()
        self._log("WARNING", "Rip cancelled by user.")

    def _rip_thread(self, job: RipJob):
        success = True
        for i, title_idx in enumerate(job.title_indices):
            if self._rip_cancelled:
                break
            cmd = [
                self._binary, "-r", "--progress=-same",
                "mkv", f"disc:{job.drive_index}",
                str(title_idx), job.destination,
            ]
            title_name = next(
                (t.name for t in self._titles if t.index == title_idx),
                f"Title {title_idx + 1}",
            )
            self._log("INFO", f"Ripping title {title_idx} → {job.destination}")
            _tn, _i, _tot = title_name, i + 1, len(job.title_indices)
            self._queue(lambda n=_tn, c=_i, t=_tot: self.rip_title.emit(n, c, t))

            title_size = next(
                (t.size_bytes for t in self._titles if t.index == title_idx), 0
            )
            try:
                self._active_proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
                )
                proc = self._active_proc
                for line in proc.stdout:
                    line = line.rstrip()
                    level, text = self._parser.classify_line(line)
                    _l, _t = level, text
                    self._queue(lambda l=_l, t=_t: self.log_line.emit(l, t))
                    fraction, status = self._parser.parse_progress(line, title_size)
                    if fraction is not None:
                        base = i / len(job.title_indices)
                        overall = base + fraction / len(job.title_indices)
                        _f, _s = overall, status
                        self._queue(lambda f=_f, s=_s: self.progress.emit(f, s))
                proc.wait()
                self._active_proc = None
                if proc.returncode != 0:
                    success = False

                if title_idx in job.custom_filenames:
                    import os as _os
                    custom = job.custom_filenames[title_idx].strip()
                    if not custom.endswith(".mkv"):
                        custom += ".mkv"
                    default_name = f"title_t{title_idx:02d}.mkv"
                    src_path = _os.path.join(job.destination, default_name)
                    dst_path = _os.path.join(job.destination, custom)
                    if _os.path.isfile(src_path):
                        _os.rename(src_path, dst_path)
                        self._log("OK", f"Renamed: {default_name} → {custom}")
                    else:
                        self._log("WARNING",
                            f"Rename skipped: {default_name} not found.")
            except Exception as e:
                _e = str(e)
                self._queue(lambda: self.error.emit(_e))
                success = False

        if self._rip_cancelled:
            success = False
        _dn, _ok = job.disc_name, success
        self._queue(lambda: self.rip_finished.emit(_dn, _ok))

    # ------------------------------------------------------------------ #
    #  Backup                                                              #
    # ------------------------------------------------------------------ #

    def start_backup(self, drive_index: int, destination: str,
                     decrypt: bool, verify: bool):
        if drive_index < 0 or drive_index >= len(self._drives):
            self.error.emit("Invalid drive selected.")
            return
        drive = self._drives[drive_index]
        job = BackupJob(
            disc_name=drive.disc_name or drive.device_path,
            source_device=str(drive.drive_index),
            destination=destination,
            status="running",
        )
        self._current_backup = job
        threading.Thread(
            target=self._backup_thread, args=(job, decrypt, verify), daemon=True
        ).start()

    def _backup_thread(self, job: BackupJob, decrypt: bool, verify: bool):
        import os
        out_dir = os.path.join(job.destination, job.disc_name.replace(" ", "_"))
        cmd = [self._binary, "-r", "--progress=-same"]
        if decrypt:
            cmd.append("--decrypt")
        cmd += ["backup", f"disc:{job.source_device}", out_dir]

        self._log("INFO", f"Backup disc:{job.source_device} → {out_dir}")
        success = True
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
            )
            for line in proc.stdout:
                line = line.rstrip()
                level, text = self._parser.classify_line(line)
                _l, _t = level, text
                self._queue(lambda l=_l, t=_t: self.log_line.emit(l, t))
                fraction, status = self._parser.parse_progress(line)
                if fraction is not None:
                    _f, _s = fraction, status
                    self._queue(lambda f=_f, s=_s: self.backup_progress.emit(f, s))
            proc.wait()
            success = proc.returncode == 0
        except Exception as e:
            _e = str(e)
            self._queue(lambda: self.error.emit(_e))
            success = False

        job.status = "done" if success else "failed"
        _j = job
        self._queue(lambda: self.backup_finished.emit(_j))

    # ------------------------------------------------------------------ #
    #  Shutdown                                                            #
    # ------------------------------------------------------------------ #

    def shutdown(self):
        self._kill_active_proc()

    def _kill_active_proc(self):
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
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    def _log(self, level: str, text: str):
        _l, _t = level, text
        self._queue(lambda l=_l, t=_t: self.log_line.emit(l, t))
