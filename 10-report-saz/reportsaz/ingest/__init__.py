# -*- coding: utf-8 -*-
"""لایهٔ ورود داده — از فایل خام تا جدول قابل تحلیل."""
from __future__ import annotations

from .cells import (clean_text, jalali_to_gregorian, normalize_digits,
                    parse_bool, parse_date, parse_number, plausible_date)
from .readers import ReadResult, read_table
from .security import (display_name, inspect_upload, validate_content,
                       validate_extension, validate_name)

__all__ = [
    "ReadResult",
    "read_table",
    "clean_text",
    "normalize_digits",
    "parse_number",
    "parse_bool",
    "parse_date",
    "plausible_date",
    "jalali_to_gregorian",
    "display_name",
    "inspect_upload",
    "validate_content",
    "validate_extension",
    "validate_name",
]
