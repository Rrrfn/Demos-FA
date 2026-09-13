# -*- coding: utf-8 -*-
"""آزمون تحلیل گروهی — فایل CSV از بارگذاری تا خروجی.

موارد سنجیده‌شده همان چیزهایی است که در عمل فایل واقعی را می‌شکند: فایل خالی،
CSV خراب، کدگذاری ویندوزی، ستون متن با نام ناشناس، سطرهای خالی و ردیف‌هایی که
مدل روی‌شان سیگنال کافی ندارد.
"""
from __future__ import annotations

import pandas as pd
import pytest

from hassanj.batch import (BatchError, OUTPUT_COLUMNS, analyse_rows, detect_columns,
                           persian_row, preview, read_table, summarise,
                           to_csv_bytes, to_frame)
from hassanj.config import MAX_ANALYZE_CHARS, MAX_BATCH_ROWS, MAX_UPLOAD_BYTES

CSV = ("text,date\n"
       "کیفیت عالی بود و ارسال سریع,1404-01-05\n"
       "خراب رسید و پشتیبانی جواب نداد,1404-01-06\n"
       "بسته رسید باید تست کنم,1404-01-07\n")


def _payload(text: str, encoding: str = "utf-8") -> bytes:
    return text.encode(encoding)


# ------------------------------------------------------------------ خواندن فایل
def test_reads_plain_csv_with_text_column():
    frame, warnings = read_table(_payload(CSV))
    assert list(frame.columns) == ["text", "date"]
    assert len(frame) == 3
    assert warnings == []


def test_reads_excel_exported_utf8_bom():
    frame, _ = read_table(_payload(CSV, "utf-8-sig"))
    assert len(frame) == 3
    assert "کیفیت" in frame.loc[0, "text"]


def test_reads_windows_persian_encoding():
    """خروجی اکسل ویندوزی با کدگذاری cp1256.

    این کدگذاری حروف *عربی* را دارد، نه شکل فارسی‌شان؛ پس ورودی واقعی همان‌طور
    است که اکسل می‌نویسد و نرمال‌سازی باید پس از خواندن درستش کند.
    """
    windows_payload = "text\nكيفيت خيلي خوب بود\nبد بود\n".encode("cp1256")
    frame, _ = read_table(windows_payload)
    assert len(frame) == 2
    from hassanj.normalize import normalize

    repaired = normalize(frame.loc[0, "text"])
    assert repaired == "کیفیت خیلی خوب بود"


@pytest.mark.parametrize("payload", [b"", b"   "])
def test_empty_payload_is_rejected_with_message(payload):
    with pytest.raises(BatchError):
        read_table(payload)


def test_header_only_file_is_rejected():
    with pytest.raises(BatchError):
        read_table(_payload("text\n"))


def test_oversized_payload_is_rejected_before_parsing():
    with pytest.raises(BatchError):
        read_table(b"x" * (MAX_UPLOAD_BYTES + 1))


def test_broken_csv_reports_a_readable_error():
    broken = "text,date\n" + ('"کیفیت عالی بود,1404-01-05\n' * 3)
    with pytest.raises(BatchError):
        read_table(_payload(broken))


def test_row_limit_is_a_warning_not_a_failure():
    rows = "\n".join(f"متن شماره {index} خوب بود" for index in range(MAX_BATCH_ROWS + 25))
    frame, warnings = read_table(_payload("text\n" + rows + "\n"))
    assert len(frame) == MAX_BATCH_ROWS
    assert warnings and "تحلیل شد" in warnings[0]


def test_index_is_reset_after_truncation():
    rows = "\n".join(f"خوب بود {index}" for index in range(MAX_BATCH_ROWS + 5))
    frame, _ = read_table(_payload("text\n" + rows + "\n"))
    assert frame.index.tolist() == list(range(len(frame)))


# ------------------------------------------------------------------ تشخیص ستون
@pytest.mark.parametrize("column", ["text", "comment", "review", "متن", "نظر", "کامنت", "دیدگاه"])
def test_known_text_column_names_are_detected(column):
    frame = pd.DataFrame({column: ["خوب بود"], "extra": ["x"]})
    text_column, date_column, guessed = detect_columns(frame)
    assert text_column == column
    assert guessed is False


def test_unknown_schema_falls_back_with_a_flag():
    frame = pd.DataFrame({"ستون ناشناس": ["خوب بود"], "other": ["x"]})
    text_column, _, guessed = detect_columns(frame)
    assert text_column == "ستون ناشناس"
    assert guessed is True


def test_date_column_detection_is_independent():
    frame = pd.DataFrame({"text": ["خوب بود"], "تاریخ": ["1404-01-05"]})
    assert detect_columns(frame)[1] == "تاریخ"


# ------------------------------------------------------------------ تحلیل ردیف‌ها
def test_analysis_marks_state_per_row(pipeline):
    rows = analyse_rows(pipeline, ["کیفیت عالی بود و ارسال سریع",
                                   "",
                                   "!!! ... ؟",
                                   "The delivery was slower than promised"])
    assert rows[0]["state"] == "ok"
    assert rows[1]["state"] == "empty"
    assert rows[2]["state"] == "no_signal"
    assert rows[3]["state"] == "out_of_domain"


def test_analysis_only_labels_rows_with_signal(pipeline):
    rows = analyse_rows(pipeline, ["کیفیت عالی بود و ارسال سریع", "", "؟؟"])
    assert rows[0]["label_fa"] != "—"
    assert rows[1]["label"] == "" and rows[1]["confidence"] is None
    assert rows[2]["label_fa"] == "—"


def test_analysis_preserves_row_order(pipeline):
    rows = analyse_rows(pipeline, ["بد بود", "", "عالی بود"])
    assert [row["index"] for row in rows] == [0, 1, 2]


def test_analysis_truncates_overlong_rows(pipeline):
    rows = analyse_rows(pipeline, ["خوب بود " * (MAX_ANALYZE_CHARS // 4)])
    assert len(rows[0]["text"]) == MAX_ANALYZE_CHARS
    assert rows[0]["state"] == "ok"


def test_analysis_returns_no_signals_for_unanalysed_rows(pipeline):
    rows = analyse_rows(pipeline, ["", "خوب بود و عالی"])
    assert rows[0]["signals"] == []
    assert isinstance(rows[1]["signals"], list)


def test_analysis_on_empty_input(pipeline):
    assert analyse_rows(pipeline, []) == []


# --------------------------------------------------------------------- خلاصه
def test_summary_counts_only_graded_rows(pipeline):
    rows = analyse_rows(pipeline, ["عالی بود و سریع", "", "بد بود"])
    summary = summarise(rows)
    assert summary["rows"] == 3
    assert summary["analysed"] == 2
    assert summary["skipped"] == 1
    assert sum(summary["counts"].values()) == 2
    assert abs(sum(summary["shares"].values()) - 1.0) < 1e-6
    assert summary["skipped_reasons"]


def test_summary_handles_a_file_with_no_analysable_rows(pipeline):
    summary = summarise(analyse_rows(pipeline, ["", "؟؟"]))
    assert summary["analysed"] == 0
    assert summary["skipped"] == 2
    assert all(share == 0.0 for share in summary["shares"].values())
    assert summary["mean_confidence"] == 0.0


def test_summary_confidence_is_bounded(pipeline):
    summary = summarise(analyse_rows(pipeline, ["عالی بود", "بد بود", "معمولی"]))
    assert 0.0 <= summary["mean_confidence"] <= 1.0


# --------------------------------------------------------------------- خروجی
def test_dataframe_has_the_documented_columns(pipeline):
    frame = to_frame(analyse_rows(pipeline, ["عالی بود", ""]))
    assert list(frame.columns) == list(OUTPUT_COLUMNS)
    assert len(frame) == 2


def test_csv_export_is_excel_safe_and_named_in_persian():
    payload, filename = to_csv_bytes(analyse_rows_from_fixture(), "comments.csv")
    assert payload.startswith(b"\xef\xbb\xbf")          # BOM برای اکسل
    assert filename.endswith("-تحلیل.csv")
    assert "comments" in filename
    text = payload.decode("utf-8-sig")
    assert "کیفیت" in text
    assert list(text.splitlines()[0].split(",")) == list(OUTPUT_COLUMNS)


def test_csv_export_uses_persian_digits_like_the_interface():
    """خروجی هم متن محصول است؛ رقم لاتین در آن استثنا نیست."""
    from hassanj.batch import analyse_rows as run
    from hassanj import services

    rows = run(services.model(), ["کیفیت عالی بود و ارسال سریع", ""])
    text = to_csv_bytes(rows, "comments.csv")[0].decode("utf-8-sig")
    assert not any(char in text for char in "0123456789")
    assert "٪" in text


def test_csv_export_without_name_still_works(pipeline):
    _, filename = to_csv_bytes(analyse_rows(pipeline, ["عالی بود"]))
    assert filename.endswith("-تحلیل.csv")


def analyse_rows_from_fixture():
    """تحلیل دو ردیف ثابت — کمک برای آزمون خروجی بدون نیاز به مدل بزرگ‌تر."""
    from hassanj import services

    return analyse_rows(services.model(), ["کیفیت عالی بود", ""])


def test_preview_limits_rows(pipeline):
    rows = analyse_rows(pipeline, [f"خوب بود {index}" for index in range(40)])
    assert len(preview(rows, limit=10)) == 10
    assert len(preview(rows)) == 40


def test_persian_row_uses_persian_digits_only(pipeline):
    row = persian_row(analyse_rows(pipeline, ["کیفیت عالی بود" + " و سریع" * 20])[0])
    assert not any(char in row["index"] for char in "0123456789")
    assert row["confidence"] == "—" or row["confidence"].endswith("٪")
    assert set(row) >= {"index", "text", "label", "confidence", "state", "signals"}
