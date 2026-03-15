"""
MakeMKVConfig — Read and write ~/.MakeMKV/settings.conf

Real file format (from MakeMKV itself):
    #
    # MakeMKV settings file, written by MakeMKV v1.18.3 linux(x64-release)
    #
    <blank line>
    key = "value"
    key = "value"

ALL values are double-quoted strings — integers, booleans, empty strings alike.
Keys are written in a fixed canonical order required by MakeMKV.
"""

import os
import re
import subprocess
import datetime

MAKEMKV_CONF = os.path.expanduser("~/.MakeMKV/settings.conf")


class MakeMKVConfig:
    """
    Read/write ~/.MakeMKV/settings.conf.
    Values are stored internally as plain strings (quotes stripped on load,
    re-added on save).  All values are written as double-quoted strings to
    match the format MakeMKV itself produces.
    """

    _LINE_RE = re.compile(r'^(\w+)\s*=\s*(.*)$')

    # Canonical key order required by MakeMKV
    _KEY_ORDER = [
        "app_DefaultProfileName",
        "app_DestinationDir",
        "app_DestinationType",
        "app_ExpertMode",
        "app_InterfaceLanguage",
        "app_Java",
        "app_Key",
        "app_PreferredLanguage",
        "app_Proxy",
        "app_ShowAVSyncMessages",
        "app_ShowDebug",
        "app_ccextractor",
        "bdplus_DumpAlways",
        "dvd_MinimumTitleLength",
        "dvd_SPRemoveMethod",
        "io_ErrorRetryCount",
        "io_RBufSizeMB",
        "io_SingleDrive",
        "sdf_Stop",
    ]

    def __init__(self, path: str = MAKEMKV_CONF):
        self.path = path
        self.data: dict[str, str] = {}
        self._extra_keys: list[str] = []   # keys outside _KEY_ORDER (e.g. speed_*)
        self.load()

    # ------------------------------------------------------------------ #
    #  Public interface                                                    #
    # ------------------------------------------------------------------ #

    def load(self):
        """Read settings.conf into self.data. Safe to call if file absent."""
        self.data = {}
        self._extra_keys = []
        if not os.path.isfile(self.path):
            return
        with open(self.path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                m = self._LINE_RE.match(stripped)
                if m:
                    key = m.group(1)
                    raw_val = m.group(2).strip()
                    self.data[key] = self._decode_value(raw_val)
                    if key not in self._KEY_ORDER:
                        self._extra_keys.append(key)

    def save(self):
        """
        Write self.data back to settings.conf in MakeMKV's exact format:
          - 3-line comment header
          - blank line 4
          - all key=value pairs from line 5 onwards, all values double-quoted
          - keys in canonical order; unknown keys (e.g. speed_*) appended after
          - trailing blank line
        """
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

        lines: list[str] = []

        # Header (lines 1-3) + blank line 4
        lines += self._build_header()
        lines.append("")   # blank line 4

        written: set[str] = set()

        # Known keys in canonical order
        for key in self._KEY_ORDER:
            if key in self.data:
                lines.append(f'{key} = "{self._escape(self.data[key])}"')
                written.add(key)

        # Extra keys (e.g. speed_HL-DT-ST_…) appended in original order
        seen = set()
        for key in self._extra_keys:
            if key not in written and key not in seen:
                val = self.data.get(key, "")
                lines.append(f'{key} = "{self._escape(val)}"')
                seen.add(key)

        # Trailing blank line (matches MakeMKV's own output)
        lines.append("")

        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")

    # ------------------------------------------------------------------ #
    #  Typed getters / setters                                             #
    # ------------------------------------------------------------------ #

    def get(self, key: str):
        """Return the raw string value for key, or None if absent."""
        return self.data.get(key, None)

    def remove(self, key: str):
        """Delete a key (takes effect on next save)."""
        self.data.pop(key, None)

    def get_str(self, key: str, default: str = "") -> str:
        return self.data.get(key, default)

    def get_bool(self, key: str, default: bool = False) -> bool:
        val = self.data.get(key, "").strip()
        if val in ("1", "true", "yes"):
            return True
        if val in ("0", "false", "no", ""):
            return False
        return default

    def get_int(self, key: str, default: int = 0) -> int:
        try:
            return int(self.data.get(key, str(default)))
        except ValueError:
            return default

    def set_str(self, key: str, value: str):
        self.data[key] = str(value)

    def set_bool(self, key: str, value: bool):
        # MakeMKV stores bools as "1"/"0" (seen in real files: app_ExpertMode="1")
        self.data[key] = "1" if value else "0"

    def set_int(self, key: str, value: int):
        self.data[key] = str(value)

    def get_drive_name(self, index: int = 0) -> str:
        """Return the drive hardware name stored in settings.conf."""
        name = self.get_str(f"app_Drive{index}", "")
        if name:
            return name
        # Fall back: scan extra keys for the last drive-name-shaped value
        for key in reversed(self._extra_keys):
            val = self.data.get(key, "")
            if val and not val.startswith("/") and val.lower() not in ("0", "1", ""):
                return val
        return ""

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _decode_value(raw: str) -> str:
        """Strip surrounding double-quotes if present."""
        if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
            return raw[1:-1]
        return raw

    @staticmethod
    def _escape(value: str) -> str:
        """Escape backslashes and double-quotes inside a value."""
        return value.replace('\\', '\\\\').replace('"', '\\"')

    @staticmethod
    def _get_makemkv_version() -> str:
        """Return the MakeMKV version string, e.g. 'v1.18.3'. Empty on failure."""
        try:
            result = subprocess.run(
                ["makemkvcon", "--version"],
                capture_output=True, text=True, timeout=5,
            )
            m = re.search(r"v[\d.]+", result.stdout + result.stderr)
            return m.group(0) if m else ""
        except Exception:
            return ""

    def _build_header(self) -> list[str]:
        """
        Return the 3 comment lines that MakeMKV writes at the top of the file:
            #
            # MakeMKV settings file, written by MakeMKV vX.Y.Z linux(x64-release)
            #
        """
        version = self._get_makemkv_version()
        version_str = f"MakeMKV {version} linux(x64-release)" if version else "MakeMKV"
        return [
            "#",
            f"# MakeMKV settings file, written by {version_str}",
            "#",
        ]
