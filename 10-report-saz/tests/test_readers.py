# -*- coding: utf-8 -*-
"""خواندن جدول — کدگذاری، جداکننده، سرصفحه و حالت‌های شکست."""
from __future__ import annotations

import io

import pandas as pd
import pytest

from reportsaz.config import MAX_ROWS
from reportsaz.errors import CorruptFileError, EmptyDatasetError, EmptyFileError
from reportsaz.ingest.readers import read_table


def _write(tmp_path, name: str, payload: bytes) -> str:
    path = tmp_path / name
    path.write_bytes(payload)
    return str(path)


# ------------------------------------------------------------------ XLSX
def test_reads_xlsx(tmp_path, frame):
    from tests.conftest import xlsx_bytes

    path = _write(tmp_path, "d.xlsx", xlsx_bytes(frame))
    result = read_table(path, "xlsx")
    assert result.rows == len(frame)
    assert result.columns == frame.shape[1]
    assert result.sheet == "داده"
    assert list(result.frame.columns) == list(frame.columns)


def test_finds_header_after_title_rows(tmp_path, titled_xlsx):
    """فایل‌های اداری چند سطر عنوان بالای جدول دارند."""
    path = _write(tmp_path, "titled.xlsx", titled_xlsx)
    result = read_table(path, "xlsx")
    assert result.header_row == 4
    assert result.skipped_rows == 3
    assert "منطقه" in result.frame.columns
    assert "مبلغ" in result.frame.columns
    assert result.rows == 20


def test_reads_second_sheet_when_first_is_empty(tmp_path, frame):
    import openpyxl

    book = openpyxl.Workbook()
    book.active.title = "خالی"
    sheet = book.create_sheet("داده‌ها")
    sheet.append(list(frame.columns))
    for record in frame.head(5).to_dict("records"):
        sheet.append([record[name] for name in frame.columns])
    buffer = io.BytesIO()
    book.save(buffer)
    path = _write(tmp_path, "two.xlsx", buffer.getvalue())

    result = read_table(path, "xlsx")
    assert result.sheet == "داده‌ها"
    assert result.rows == 5


def test_rejects_workbook_without_data(tmp_path):
    import openpyxl

    book = openpyxl.Workbook()
    buffer = io.BytesIO()
    book.save(buffer)
    path = _write(tmp_path, "blank.xlsx", buffer.getvalue())
    with pytest.raises(EmptyDatasetError):
        read_table(path, "xlsx")


def test_rejects_corrupt_xlsx(tmp_path):
    path = _write(tmp_path, "broken.xlsx", b"PK\x03\x04" + b"\x00" * 40)
    with pytest.raises(CorruptFileError):
        read_table(path, "xlsx")


# ------------------------------------------------------------------ CSV
def test_reads_utf8_csv(tmp_path, frame):
    from tests.conftest import csv_bytes

    path = _write(tmp_path, "d.csv", csv_bytes(frame))
    result = read_table(path, "csv")
    assert result.rows == len(frame)
    assert result.encoding in ("utf-8-sig", "utf-8")
    assert result.separator == ","


def test_reads_utf8_bom_csv(tmp_path, frame):
    from tests.conftest import csv_bytes

    path = _write(tmp_path, "d.csv", csv_bytes(frame, encoding="utf-8-sig"))
    result = read_table(path, "csv")
    assert result.encoding == "utf-8-sig"
    #: با BOM، نام ستون اول نباید نویسهٔ نامرئی داشته باشد.
    assert not list(result.frame.columns)[0].startswith("\ufeff")


def test_reads_windows_persian_csv(tmp_path):
    """فایل‌های فارسی ویندوزی معمولاً cp1256 هستند.

    ستون‌ها عمداً فقط حروفی هستند که در cp1256 وجود دارند؛ نیم‌فاصلهٔ فارسی
    در این کدگذاری نیست و دادهٔ آزمون را غیرقابل رمزگذاری می‌کرد.
    """
    #: فقط نویسه‌هایی که در cp1256 هستند: «ی» فارسی (U+06CC) و «ک» فارسی
    #: (U+06A9) در این کدگذاری وجود ندارند، پس دادهٔ آزمون با آن‌ها ساخته
    #: نمی‌شود.
    frame = pd.DataFrame({"شهر": ["تهران", "مشهد", "بغداد"],
                          "عدد": [1200, 3400, 5600]})
    from tests.conftest import csv_bytes

    path = _write(tmp_path, "d.csv", csv_bytes(frame, encoding="cp1256"))
    result = read_table(path, "csv")
    assert result.encoding == "cp1256"
    assert "تهران" in set(result.frame["شهر"].dropna().astype(str))


@pytest.mark.parametrize("separator", [";", "\t", "|"])
def test_detects_separator(tmp_path, frame, separator):
    """تشخیص خودکار جداکننده؛ ویرگول در داده هم هست."""
    payload = frame.to_csv(index=False, sep=separator).encode("utf-8")
    path = _write(tmp_path, "d.csv", payload)
    result = read_table(path, "csv")
    assert result.columns == frame.shape[1], result.separator


def test_quoted_commas_do_not_break_columns(tmp_path):
    """مقدار متنی با ویرگول داخلش نباید ستون بشکند."""
    from tests.conftest import csv_bytes

    frame = pd.DataFrame({"نام": ['شرکت الف، واحد فروش', "شرکت ب"],
                          "مبلغ": [1200, 3400]})
    path = _write(tmp_path, "d.csv", csv_bytes(frame))
    result = read_table(path, "csv")
    assert result.columns == 2
    assert result.rows == 2


def test_rejects_empty_csv(tmp_path):
    path = _write(tmp_path, "empty.csv", b"")
    with pytest.raises(EmptyFileError):
        read_table(path, "csv")


def test_rejects_header_only_csv(tmp_path):
    path = _write(tmp_path, "head.csv", "a,b,c\n".encode("utf-8"))
    with pytest.raises(EmptyDatasetError):
        read_table(path, "csv")


def test_rejects_binary_csv(tmp_path):
    path = _write(tmp_path, "binary.csv", b"\x00\x01\x02\x03" * 64)
    with pytest.raises(CorruptFileError):
        read_table(path, "csv")


def test_rejects_utf16_csv_with_clear_message(tmp_path):
    """فایل UTF-16 باید با پیام روشن رد شود.

    بدترین حالت این است که بایت‌هایش با cp1256 "موفق" رمزگشایی شوند و متنی
    بی‌معنا بی‌صدا وارد تحلیل شود. پیام باید بگوید چه باید کرد.
    """
    payload = "منطقه,مبلغ\nتهران,1200\n".encode("utf-16")
    path = _write(tmp_path, "utf16.csv", payload)
    with pytest.raises(CorruptFileError) as info:
        read_table(path, "csv")
    assert "UTF-16" in str(info.value)


# ------------------------------------------------------------------ ستون‌ها
def test_deduplicates_column_names(tmp_path):
    """اکسل اجازه می‌دهد دو ستون هم‌نام باشند؛ pandas با آن مشکل دارد."""
    payload = ("مبلغ,مبلغ,مبلغ\n1,2,3\n4,5,6\n").encode("utf-8")
    path = _write(tmp_path, "dupe.csv", payload)
    result = read_table(path, "csv")
    names = list(result.frame.columns)
    assert len(set(names)) == 3
    assert names[0] == "مبلغ"


def test_names_unnamed_columns(tmp_path):
    payload = ("مقدار,,توضیح\n1,2,سه\n4,5,شش\n").encode("utf-8")
    path = _write(tmp_path, "nameless.csv", payload)
    result = read_table(path, "csv")
    assert all(str(name).strip() for name in result.frame.columns)


def test_drops_fully_empty_columns_and_rows(tmp_path):
    payload = ("الف,ب,ج\n1,,2\n,,\n3,,4\n").encode("utf-8")
    path = _write(tmp_path, "sparse.csv", payload)
    result = read_table(path, "csv")
    assert "ب" not in result.frame.columns
    assert result.rows == 2


def test_ragged_rows_are_skipped_with_a_warning(tmp_path):
    """سطر با تعداد ستون متفاوت باید رد شود *و اعلام شود*، نه این‌که کل
    فایل شکست بخورد یا سطر بی‌صدا حذف شود."""
    payload = ("الف,ب,ج\n1,2,3\n4,5,6,7\n8,9,10\n").encode("utf-8")
    path = _write(tmp_path, "ragged.csv", payload)
    result = read_table(path, "csv")
    assert result.rows == 2
    assert any("سطر" in item for item in result.warnings)


def test_flags_missing_header(tmp_path):
    """جدول بدون سرصفحه باید هشدار بدهد و نام ستون بسازد."""
    payload = ("1,2,3\n4,5,6\n7,8,9\n").encode("utf-8")
    path = _write(tmp_path, "noheader.csv", payload)
    result = read_table(path, "csv")
    assert result.rows >= 1
    assert any("سرصفحه" in item for item in result.warnings)


# ------------------------------------------------------------------ سقف‌ها
def test_truncates_large_csv_and_says_so(tmp_path, monkeypatch):
    """بریدن سطر باید اعلام شود، نه این‌که بی‌صدا رخ دهد."""
    import reportsaz.ingest.readers as readers

    monkeypatch.setattr(readers, "MAX_ROWS", 25)
    rows = "\n".join(f"{index},{index * 2}" for index in range(60))
    payload = f"الف,ب\n{rows}\n".encode("utf-8")
    path = _write(tmp_path, "big.csv", payload)
    result = read_table(path, "csv")
    assert result.rows == 25
    assert result.truncated is True
    assert any("سطر" in item for item in result.warnings)


def test_summary_is_serialisable(tmp_path, frame):
    from tests.conftest import xlsx_bytes

    path = _write(tmp_path, "d.xlsx", xlsx_bytes(frame))
    summary = read_table(path, "xlsx").summary()
    for key in ("rows", "columns", "sheet", "encoding", "separator",
                "header_row", "skipped_rows", "truncated", "warnings"):
        assert key in summary
