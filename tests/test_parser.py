"""
Tests for MakeMKVParser — no GTK required, pure Python.
Run with: pytest tests/
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.makemkv_parser import MakeMKVParser


SAMPLE_DRV_OUTPUT = """\
DRV:0,2,999,0,"ASUS BW-16D1HT","MOVIE_TITLE",/dev/sr0
DRV:1,0,999,0,"","",/dev/sr1
"""

SAMPLE_INFO_OUTPUT = """\
CINFO:2,0,"My Disc"
TCOUNT:3
TINFO:0,2,0,"Title 1"
TINFO:0,9,0,"2:12:34"
TINFO:0,10,0,"25769803776"
TINFO:0,8,0,"22"
TINFO:0,27,0,"title_t00.mkv"
TINFO:1,2,0,"Title 2"
TINFO:1,9,0,"0:05:10"
TINFO:1,10,0,"524288000"
TINFO:1,8,0,"5"
"""

SAMPLE_PROGRESS = "PRGV:512,1024,2048"


def test_parse_drives():
    parser = MakeMKVParser()
    drives = parser.parse_drives(SAMPLE_DRV_OUTPUT)
    assert len(drives) == 1
    d = drives[0]
    assert d.device_path == "/dev/sr0"
    assert d.drive_name == "ASUS BW-16D1HT"
    assert d.disc_name == "MOVIE_TITLE"
    assert d.has_disc is True


def test_parse_titles():
    parser = MakeMKVParser()
    titles = parser.parse_titles(SAMPLE_INFO_OUTPUT)
    assert len(titles) == 2

    t0 = titles[0]
    assert t0.index == 0
    assert t0.name == "Title 1"
    assert t0.duration == "2:12:34"
    assert t0.size_bytes == 25769803776
    assert t0.chapter_count == 22
    assert t0.output_file_name == "title_t00.mkv"
    assert t0.disc_name == "My Disc"

    t1 = titles[1]
    assert t1.name == "Title 2"
    assert t1.chapter_count == 5


def test_title_size_str():
    parser = MakeMKVParser()
    titles = parser.parse_titles(SAMPLE_INFO_OUTPUT)
    assert "GB" in titles[0].size_str
    assert "MB" in titles[1].size_str


def test_parse_progress():
    parser = MakeMKVParser()
    fraction, status = parser.parse_progress(SAMPLE_PROGRESS)
    assert fraction == 0.25
    assert "25%" in status


def test_parse_progress_no_match():
    parser = MakeMKVParser()
    fraction, status = parser.parse_progress("MSG:5010,0,0,\"Done\"")
    assert fraction is None
    assert status == ""


def test_classify_line_msg():
    parser = MakeMKVParser()
    level, text = parser.classify_line('MSG:5005,0,0,"Operation successful"')
    assert level == "OK"
    assert "Operation successful" in text


def test_classify_line_debug():
    parser = MakeMKVParser()
    level, text = parser.classify_line("TINFO:0,2,0,\"foo\"")
    assert level == "DEBUG"


def test_split_fields_quoted():
    result = MakeMKVParser._split_fields('"hello, world",42,"foo"')
    assert result == ['"hello, world"', "42", '"foo"']
