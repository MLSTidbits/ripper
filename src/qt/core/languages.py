"""
languages.py — ISO 639-2 language list for the Preferred Language dropdowns.

Primary source : /usr/share/iso-codes/json/iso_639-2.json  (487 entries on
                 most Debian/Ubuntu/Fedora/Arch systems; install the
                 'iso-codes' package if it is missing).
Fallback       : a small hardcoded table of the 20 most common languages.

Public API
----------
get_languages() -> list[tuple[str, str]]
    Sorted (display_name, iso639_2_alpha_3) pairs, e.g. ("English", "eng").
    Names with semicolons (e.g. "Spanish; Castilian") are trimmed to the
    first alternative so the list stays concise.

get_system_language_code() -> str
    ISO 639-2 code for the running OS language (from $LANG / $LANGUAGE).
    Falls back to "eng" if detection fails.
"""

import json
import os
import re

_ISO_CODES_PATH = "/usr/share/iso-codes/json/iso_639-2.json"

_FALLBACK_LANGUAGES: list[tuple[str, str]] = sorted([
    ("Arabic",     "ara"), ("Chinese",    "zho"), ("Czech",      "ces"),
    ("Danish",     "dan"), ("Dutch",      "nld"), ("English",    "eng"),
    ("Finnish",    "fin"), ("French",     "fra"), ("German",     "deu"),
    ("Greek",      "ell"), ("Hebrew",     "heb"), ("Hungarian",  "hun"),
    ("Italian",    "ita"), ("Japanese",   "jpn"), ("Korean",     "kor"),
    ("Norwegian",  "nor"), ("Polish",     "pol"), ("Portuguese", "por"),
    ("Romanian",   "ron"), ("Russian",    "rus"), ("Spanish",    "spa"),
    ("Swedish",    "swe"), ("Thai",       "tha"), ("Turkish",    "tur"),
    ("Ukrainian",  "ukr"),
], key=lambda x: x[0])

# 2-letter ISO 639-1 -> ISO 639-2 for the most common cases
_ALPHA2_TO_ALPHA3: dict[str, str] = {
    "ar": "ara", "zh": "zho", "cs": "ces", "da": "dan", "nl": "nld",
    "en": "eng", "fi": "fin", "fr": "fra", "de": "deu", "el": "ell",
    "he": "heb", "hu": "hun", "it": "ita", "ja": "jpn", "ko": "kor",
    "nb": "nob", "no": "nor", "pl": "pol", "pt": "por", "ro": "ron",
    "ru": "rus", "es": "spa", "sv": "swe", "th": "tha", "tr": "tur",
    "uk": "ukr",
}


def get_languages() -> list[tuple[str, str]]:
    """
    Return a sorted list of (display_name, iso639_2_code) tuples.
    Sourced from the system iso-codes package when available.
    """
    try:
        with open(_ISO_CODES_PATH) as f:
            data = json.load(f)
        entries = data.get("639-2", [])
        langs = []
        for e in entries:
            code = e.get("alpha_3")
            name = e.get("name", "")
            if not code or not name:
                continue
            # Trim "Spanish; Castilian" → "Spanish"
            name = name.split(";")[0].strip()
            langs.append((name, code))
        return sorted(langs, key=lambda x: x[0])
    except Exception:
        return list(_FALLBACK_LANGUAGES)


def get_system_language_code() -> str:
    """
    Detect the OS preferred language and return its ISO 639-2 code.
    Reads $LANGUAGE (colon-separated list), then $LANG, then $LC_ALL.
    Returns 'eng' if nothing can be determined.
    """
    candidates = []
    for var in ("LANGUAGE", "LANG", "LC_ALL"):
        val = os.environ.get(var, "")
        if val:
            # LANGUAGE may be "de:fr:en"; take all parts
            candidates.extend(val.replace("-", "_").split(":"))

    for raw in candidates:
        # Match the language prefix: "en", "en_US", "en_US.UTF-8", "eng"
        m = re.match(r"([a-zA-Z]{2,3})", raw)
        if not m:
            continue
        prefix = m.group(1).lower()

        # 3-letter code — try direct lookup in iso-codes first
        if len(prefix) == 3:
            try:
                with open(_ISO_CODES_PATH) as f:
                    data = json.load(f)
                for e in data.get("639-2", []):
                    if e.get("alpha_3") == prefix:
                        return prefix
            except Exception:
                pass
            # Check hardcoded fallback
            if any(c == prefix for _, c in _FALLBACK_LANGUAGES):
                return prefix

        # 2-letter code — map via iso-codes alpha_2 field
        if len(prefix) == 2:
            try:
                with open(_ISO_CODES_PATH) as f:
                    data = json.load(f)
                for e in data.get("639-2", []):
                    if e.get("alpha_2") == prefix:
                        return e["alpha_3"]
            except Exception:
                pass
            if prefix in _ALPHA2_TO_ALPHA3:
                return _ALPHA2_TO_ALPHA3[prefix]

    return "eng"
