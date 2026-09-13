# -*- coding: utf-8 -*-
"""مرز اعتماد ورودی — پسوند، محتوا، حجم و نام فایل."""
from __future__ import annotations

import os

import pytest

from reportsaz.errors import (CorruptFileError, FileTooLargeError,
                              LegacyFormatError, MissingFileError,
                              UnsupportedFormatError)
from reportsaz.ingest.security import (check_mime, display_name,
                                       inspect_upload, validate_content,
                                       validate_extension, validate_name)
from reportsaz.config import MAX_UPLOAD_BYTES


# ------------------------------------------------------------------ نام
@pytest.mark.parametrize("raw,expected", [
    ("report.xlsx", "report.xlsx"),
    ("/etc/passwd", "passwd"),
    ("C:\\\\temp\\\\فایل.xlsx", "فایل.xlsx"),
    ("../../secret.xlsx", "secret.xlsx"),
    ("   ", "فایل بدون نام"),
    ("", "فایل بدون نام"),
    (None, "فایل بدون نام"),
])
def test_display_name_is_safe(raw, expected):
    assert display_name(raw) == expected


def test_display_name_strips_control_and_override_characters():
    """نویسهٔ کنترلی و بازنویسی جهت متن نباید در نام بماند.

    نویسهٔ ``‮`` (راست‌به‌چپ‌بر) می‌تواند پسوند نمایشی فایل را جعل کند.
    """
    name = display_name("report\u202exlsx.exe")
    assert "\u202e" not in name
    assert "\x00" not in display_name("bad\x00name.xlsx")


def test_display_name_is_bounded():
    long_name = "a" * 400 + ".xlsx"
    assert len(display_name(long_name)) <= 120


# ------------------------------------------------------------------ پسوند
@pytest.mark.parametrize("name,expected", [
    ("data.xlsx", "xlsx"),
    ("DATA.XLSX", "xlsx"),
    ("data.csv", "csv"),
    ("آمار فروش.xlsx", "xlsx"),
])
def test_validate_extension_accepts(name, expected):
    assert validate_extension(name) == expected


@pytest.mark.parametrize("name", ["data.xls", "data.xlsm", "data.ods"])
def test_validate_extension_rejects_legacy_with_guidance(name):
    """قالب قدیمی باید پیام راهنما بدهد، نه خطای عمومی."""
    with pytest.raises(LegacyFormatError) as info:
        validate_extension(name)
    assert "xlsx" in str(info.value).lower() or "csv" in str(info.value).lower()


@pytest.mark.parametrize("name", ["data.txt", "data.pdf", "data.exe",
                                  "data.json", "بدونپسوند"])
def test_validate_extension_rejects_unknown(name):
    with pytest.raises((UnsupportedFormatError, LegacyFormatError)):
        validate_extension(name)


# ------------------------------------------------------------------ حجم و نام
def test_validate_name_requires_a_file():
    with pytest.raises(MissingFileError):
        validate_name("")
    with pytest.raises(MissingFileError):
        validate_name(None)


def test_validate_name_enforces_size():
    with pytest.raises(FileTooLargeError):
        validate_name("big.xlsx", MAX_UPLOAD_BYTES + 1)


def test_inspect_upload_returns_warnings_for_mime_mismatch():
    """نوع اعلامی مرورگر ملاک نیست، ولی ناهماهنگی گزارش می‌شود."""
    info = inspect_upload("data.csv", "image/png", 1024)
    assert info["extension"] == "csv"
    assert info["warnings"]
    assert "png" in info["warnings"][0]


def test_check_mime_accepts_empty_declaration():
    assert check_mime("", "csv") == []
    assert check_mime(None, "xlsx") == []


# ------------------------------------------------------------------ محتوا
def test_validate_content_rejects_binary_as_csv(tmp_path):
    """فایل دودویی با پسوند csv باید رد شود، حتی اگر پسوندش درست باشد."""
    path = tmp_path / "fake.csv"
    path.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64)
    with pytest.raises(CorruptFileError):
        validate_content(str(path), "csv")


def test_validate_content_rejects_text_as_xlsx(tmp_path):
    path = tmp_path / "fake.xlsx"
    path.write_text("not a workbook at all", encoding="utf-8")
    with pytest.raises(CorruptFileError):
        validate_content(str(path), "xlsx")


def test_validate_content_rejects_empty_file(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_bytes(b"")
    with pytest.raises(CorruptFileError):
        validate_content(str(path), "csv")


def test_validate_content_accepts_real_xlsx(xlsx_file, tmp_path):
    path = tmp_path / "real.xlsx"
    path.write_bytes(xlsx_file)
    assert validate_content(str(path), "xlsx") == []


def test_validate_content_accepts_persian_csv(csv_file, tmp_path):
    path = tmp_path / "real.csv"
    path.write_bytes(csv_file)
    assert validate_content(str(path), "csv") == []


def test_validate_content_flags_truncated_zip(tmp_path):
    """آرشیو بریده باید هشدار بدهد، نه این‌که بی‌صدا رد شود."""
    truncated = tmp_path / "cut.xlsx"
    truncated.write_bytes(b"PK\x03\x04" + os.urandom(200))
    warnings = validate_content(str(truncated), "xlsx")
    assert any("آرشیو" in item for item in warnings)
