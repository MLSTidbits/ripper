"""
Data models used across the application.
These are plain Python dataclasses — no GTK dependency.
"""

from dataclasses import dataclass, field
from typing import Optional
import datetime


@dataclass
class DriveInfo:
    """Represents a detected optical drive."""
    device_path: str           # e.g. /dev/sr0
    drive_index: int = 0       # makemkvcon disc index (0, 1, 2…)
    drive_name: str = ""       # e.g. "ASUS BW-16D1HT"
    disc_name: str = ""        # e.g. "MOVIE_TITLE"
    has_disc: bool = False
    disc_type: str = ""        # e.g. "Blu-ray", "DVD"
    libre_drive_status: str = ""   # "Enabled", "Possible, not yet enabled", etc.


@dataclass
class TitleInfo:
    """A single title/track found on a disc."""
    index: int
    name: str
    disc_name: str
    duration: str              # e.g. "2:12:34"
    size_bytes: int = 0
    chapter_count: int = 0
    selected: bool = True
    output_file_name: str = ""

    @property
    def size_str(self) -> str:
        gb = self.size_bytes / 1_073_741_824
        if gb >= 1:
            return f"{gb:.1f} GB"
        mb = self.size_bytes / 1_048_576
        return f"{mb:.0f} MB"


@dataclass
class BackupJob:
    """Tracks a single backup operation, past or present."""
    disc_name: str
    source_device: str
    destination: str
    size_bytes: int = 0
    status: str = "queued"     # queued | running | done | failed
    timestamp: str = field(default_factory=lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
    error_message: Optional[str] = None

    @property
    def size_str(self) -> str:
        if self.size_bytes == 0:
            return "—"
        gb = self.size_bytes / 1_073_741_824
        return f"{gb:.1f} GB"


@dataclass
class RipJob:
    """Tracks a single rip operation."""
    disc_name: str
    drive_index: int
    destination: str
    title_indices: list[int]
    # Maps title index → custom output filename (empty = use makemkvcon default)
    custom_filenames: dict = field(default_factory=dict)
    status: str = "queued"
    progress: float = 0.0
    current_title: int = 0
    timestamp: str = field(default_factory=lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
    error_message: Optional[str] = None
