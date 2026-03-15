"""
MakeMKVParser — Parses the structured output of `makemkvcon -r`.

makemkvcon -r emits lines in a machine-readable format:
  MSG:code,flags,count,message,format,...
  PRGV:current,total,max
  PRGC:code,id,name
  PRGT:code,id,name
  TCOUNT:count
  CINFO:id,code,value
  TINFO:title,id,code,value
  SINFO:title,stream,id,code,value
  DRV:index,visible,enabled,flags,drive_name,disc_name,device_path

DRV visible field values:
  0 = drive not present / hidden — skip entirely
  1 = drive present, disc inserted
  2 = drive present, no disc

flags field:
  Bit 0 set = disc is present and readable
"""

import re
from core.models import DriveInfo, TitleInfo


class MakeMKVParser:
    # Message code → log level mapping (subset)
    MSG_LEVELS = {
        5005: "OK",
        5010: "OK",
        5011: "WARNING",
        5020: "ERROR",
        5021: "ERROR",
        9001: "INFO",
        9002: "INFO",
        9003: "INFO",
        9004: "OK",
        9005: "WARNING",
    }

    # TINFO/CINFO attribute IDs we care about
    ATTR_DISC_TYPE        = 1   # CINFO id 1 = disc type string, e.g. "Blu-ray", "DVD"
    ATTR_NAME            = 2
    ATTR_CHAPTER_COUNT   = 8
    ATTR_DURATION        = 9
    ATTR_DISK_SIZE_STR   = 10   # human-readable string, e.g. "4.2 GB"
    ATTR_DISK_SIZE_BYTES = 11   # raw size in bytes as an integer string
    ATTR_OUTPUT_FILENAME = 27

    def parse_drives(self, output: str) -> list[DriveInfo]:
        """
        Return only drives that have a disc inserted and are readable.
        Drives that are present but empty, or not present at all, are excluded.
        """
        drives = []
        for line in output.splitlines():
            if not line.startswith("DRV:"):
                continue
            # DRV:index,visible,enabled,flags,drive_name,disc_name,device_path
            parts = self._split_fields(line[4:])
            if len(parts) < 6:
                continue

            try:
                index   = int(parts[0])
                visible = int(parts[1])
                flags   = int(parts[3]) if parts[3].strip() else 0
            except ValueError:
                continue

            # visible == 0  → drive slot not present, skip completely
            if visible == 0:
                continue

            drive_name  = parts[4].strip('"')
            disc_name   = parts[5].strip('"')
            device_path = parts[6].strip('"') if len(parts) > 6 else f"/dev/sr{index}"

            # Only include drives that actually have a disc inserted.
            # makemkvcon signals this two ways: a non-empty disc_name, or
            # flags bit-0 set.  Either is sufficient.
            has_disc = bool(disc_name) or bool(flags & 1)
            if not has_disc:
                continue

            drives.append(DriveInfo(
                device_path=device_path,
                drive_index=index,
                drive_name=drive_name,
                disc_name=disc_name,
                has_disc=True,
            ))
        return drives

    def parse_titles(self, output: str) -> tuple[list[TitleInfo], str]:
        """
        Returns (titles, disc_type_str) where disc_type_str is e.g. 'Blu-ray' or 'DVD'.
        """
        titles: dict[int, dict] = {}
        disc_name = ""
        disc_type = ""

        for line in output.splitlines():
            if line.startswith("CINFO:"):
                parts = self._split_fields(line[6:])
                if len(parts) < 3:
                    continue
                try:
                    attr_id = int(parts[0])
                except ValueError:
                    continue
                value = parts[2].strip('"')
                if attr_id == self.ATTR_DISC_TYPE:
                    disc_type = value
                elif attr_id == self.ATTR_NAME:
                    disc_name = value

            elif line.startswith("TCOUNT:"):
                pass  # used for progress

            elif line.startswith("TINFO:"):
                parts = self._split_fields(line[6:])
                if len(parts) < 4:
                    continue
                try:
                    title_idx = int(parts[0])
                    attr_id   = int(parts[1])
                    value     = parts[3].strip('"')
                except (ValueError, IndexError):
                    continue

                if title_idx not in titles:
                    titles[title_idx] = {
                        "index": title_idx,
                        "name": f"Title {title_idx + 1}",
                        "disc_name": disc_name,
                        "duration": "0:00:00",
                        "size_bytes": 0,
                        "chapter_count": 0,
                        "output_file_name": "",
                    }

                t = titles[title_idx]
                if attr_id == self.ATTR_NAME:
                    t["name"] = value
                elif attr_id == self.ATTR_DURATION:
                    t["duration"] = value
                elif attr_id == self.ATTR_DISK_SIZE_BYTES:
                    try:
                        t["size_bytes"] = int(value)
                    except ValueError:
                        pass
                elif attr_id == self.ATTR_DISK_SIZE_STR:
                    # Fallback: if we never get the raw bytes ID, parse the
                    # human string so size_str at least shows something.
                    if t["size_bytes"] == 0:
                        t["_size_str_fallback"] = value
                elif attr_id == self.ATTR_CHAPTER_COUNT:
                    try:
                        t["chapter_count"] = int(value)
                    except ValueError:
                        pass
                elif attr_id == self.ATTR_OUTPUT_FILENAME:
                    t["output_file_name"] = value

        result = []
        for idx in sorted(titles):
            d = titles[idx]
            d["disc_name"] = disc_name
            # If makemkvcon only gave us the human-readable size string,
            # convert it back to an approximate byte count so size_str works.
            fallback = d.pop("_size_str_fallback", None)
            if d["size_bytes"] == 0 and fallback:
                d["size_bytes"] = self._parse_size_str(fallback)
            result.append(TitleInfo(**d))
        return result, disc_type

    def parse_libre_drive_status(self, output: str) -> str:
        """
        Extract LibreDrive status from makemkvcon info output.
        MakeMKV reports it in MSG lines containing "LibreDrive" and "Status:".
        Returns a short status string, or "" if not found.
        """
        status = ""
        in_libre_section = False
        for line in output.splitlines():
            # MSG lines contain human-readable text in field index 3
            if line.startswith("MSG:"):
                parts = self._split_fields(line[4:])
                if len(parts) >= 4:
                    text = parts[3].strip('"')
                    if "LibreDrive" in text:
                        in_libre_section = True
                    if in_libre_section and "Status:" in text:
                        # e.g. "Status: Enabled" or "Status: Possible, not yet enabled"
                        after = text.split("Status:", 1)[1].strip()
                        # Strip any HTML tags
                        import re
                        status = re.sub(r"<[^>]+>", "", after).strip()
                        break
        return status

    def parse_progress(self, line: str, title_size_bytes: int = 0) -> tuple[float | None, str]:
        """
        Parse a PRGV line and return (fraction 0-1, status_str) or (None, "").

        PRGV:current,total,max
          current  - progress counter, runs 0..max
          total    - mirrors max (always 65536); does NOT carry file size
          max      - fixed denominator, always 65536

        title_size_bytes: pass the known size from TitleInfo.size_bytes so the
        status string can show a meaningful file size while ripping.
        The percentage is shown on the scale thumb so the status shows size only.
        """
        if not line.startswith("PRGV:"):
            return None, ""
        parts = line[5:].split(",")
        try:
            current = int(parts[0])
            maximum = int(parts[2])
        except (ValueError, IndexError):
            return None, ""

        if maximum <= 0:
            return None, ""

        fraction = min(current / maximum, 1.0)

        # Use the pre-known title size for the display string
        size_bytes = title_size_bytes
        if size_bytes >= 1_073_741_824:
            size_str = f"{size_bytes / 1_073_741_824:.2f} GB"
        elif size_bytes >= 1_048_576:
            size_str = f"{size_bytes / 1_048_576:.0f} MB"
        else:
            size_str = ""

        return fraction, size_str


    def classify_line(self, line: str) -> tuple[str, str]:
        """Return (level, human_readable_text) for a raw makemkvcon line."""
        if line.startswith("MSG:"):
            parts = self._split_fields(line[4:])
            if len(parts) >= 4:
                try:
                    code  = int(parts[0])
                    level = self.MSG_LEVELS.get(code, "INFO")
                    text  = parts[3].strip('"')
                    return level, text
                except ValueError:
                    pass
            return "INFO", line

        if line.startswith(("PRGV:", "PRGC:", "PRGT:", "TCOUNT:", "TINFO:", "CINFO:", "SINFO:", "DRV:")):
            return "DEBUG", line

        return "INFO", line

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _parse_size_str(s: str) -> int:
        """Convert a human size string like '4.2 GB' or '700 MB' to bytes."""
        s = s.strip()
        try:
            parts = s.split()
            num = float(parts[0])
            unit = parts[1].upper() if len(parts) > 1 else "B"
            multipliers = {"B": 1, "KB": 1024, "MB": 1_048_576,
                           "GB": 1_073_741_824, "TB": 1_099_511_627_776}
            return int(num * multipliers.get(unit, 1))
        except Exception:
            return 0

    @staticmethod
    def _split_fields(s: str) -> list[str]:
        """Split comma-separated fields, respecting quoted strings."""
        fields = []
        current = []
        in_quotes = False
        for ch in s:
            if ch == '"':
                in_quotes = not in_quotes
                current.append(ch)
            elif ch == ',' and not in_quotes:
                fields.append("".join(current))
                current = []
            else:
                current.append(ch)
        fields.append("".join(current))
        return fields
