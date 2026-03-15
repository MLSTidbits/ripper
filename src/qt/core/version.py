"""
Single source of truth for the application version.
Reads the version string from /usr/share/doc/makemkv-gtk/version.

Installed path : /usr/share/ripper/version
Development    : <project>/doc/version
"""

def get_version() -> str:
    """Return the version string, e.g. '0.1.0'."""
    try:
        with open("/usr/share/doc/reel-common/version") as f:
            return f.read().strip()
    except OSError:
        return "unknown"
