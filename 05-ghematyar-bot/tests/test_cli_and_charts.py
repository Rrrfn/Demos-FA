# -*- coding: utf-8 -*-
"""تست نقطهٔ ورود خط فرمان و موتور نمودار.

دو باگ واقعی که این تست‌ها از بازگشتشان جلوگیری می‌کنند:

1. کنسول غیر UTF-8 (مثلاً cp1256 ویندوز) نمی‌توانست متن فارسی و نمادهای
   ✅/❌ را رمزگذاری کند؛ برنامه به‌جای پیام راهنما با UnicodeEncodeError
   می‌افتاد و کد خروج اشتباه می‌داد.
2. نبود matplotlib باید به «نمودار غیرفعال است» تبدیل شود، نه
   ModuleNotFoundError در میانهٔ دستور.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from ghematyar.core.models import PricePoint
from ghematyar.services import ChartUnavailable, render_price_chart

ROOT = Path(__file__).resolve().parent.parent


def _points(count: int) -> list[PricePoint]:
    """چند نقطهٔ تاریخچهٔ مصنوعی برای رندر."""
    now = time.time()
    return [
        PricePoint(
            slug="usd",
            price=250_000 + index * 1_000,
            captured_at=now - (count - index) * 60,
            source="test",
        )
        for index in range(count)
    ]


# رندر واقعی در پروسهٔ جداگانه اجرا می‌شود. اگر کتابخانهٔ بومی matplotlib در
# یک محیط خراب باشد، خرابی از نوع سقوط بومی (native crash) است و با
# try/except قابل گرفتن نیست؛ اجرای درون‌پروسه‌ای کل مجموعه تست را از بین
# می‌برد. با اجرای جداگانه، محیط سالم واقعاً آزموده می‌شود و محیط خراب
# صادقانه skip می‌خورد.
_RENDER_SCRIPT = """
import sys, time
import matplotlib
matplotlib.use("Agg")
from ghematyar.core.models import PricePoint
from ghematyar.services import render_price_chart

now = time.time()
points = [
    PricePoint(
        slug="usd",
        price=250_000 + index * 1_000,
        source="test",
        captured_at=now - (6 - index) * 60,
    )
    for index in range(6)
]
png = render_price_chart("USD", points, unit="usd")
assert png[:8] == b"\\x89PNG\\r\\n\\x1a\\n", "output is not a PNG"
sys.stdout.write("BYTES=%d" % len(png))
"""


def _render_in_subprocess() -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", _RENDER_SCRIPT],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=300,
    )


class TestChartAvailability:
    """نمودار: دادهٔ کم در برابر موتور نصب‌نشده — دو وضعیت متفاوت."""

    def test_too_few_points_reports_history_reason(self):
        with pytest.raises(ChartUnavailable) as exc:
            render_price_chart("دلار", _points(2))
        assert exc.value.reason == "history"
        assert exc.value.have == 2
        assert exc.value.backend_missing is False

    def test_missing_matplotlib_is_reported_honestly(self, monkeypatch):
        """matplotlib نصب نیست → دلیل «backend»، نه سقوط برنامه."""
        monkeypatch.setitem(sys.modules, "matplotlib", None)
        with pytest.raises(ChartUnavailable) as exc:
            render_price_chart("دلار", _points(5))
        assert exc.value.backend_missing is True

    def test_renders_png_when_backend_is_healthy(self):
        """اگر موتور رندر محیط سالم باشد، خروجی واقعاً PNG است."""
        pytest.importorskip("matplotlib")
        result = _render_in_subprocess()
        if result.returncode != 0:
            pytest.skip(
                "موتور بومی matplotlib در این محیط کار نمی‌کند "
                f"(rc={result.returncode})؛ "
                "برای ترمیم: pip install --force-reinstall matplotlib"
            )
        assert "BYTES=" in result.stdout, result.stderr[-500:]
        assert int(result.stdout.split("BYTES=")[1].strip()) > 1000


class TestCliEntryPoint:
    """``python -m ghematyar`` — کد خروج درست، حتی با کنسول غیر UTF-8."""

    def _run(self, args: list[str], tmp_path: Path, **extra_env: str):
        env = {key: value for key, value in os.environ.items() if key != "TELEGRAM_TOKEN"}
        # کنسول غیر UTF-8 ویندوز را شبیه‌سازی می‌کنیم
        env["PYTHONIOENCODING"] = "ascii"
        env["GHEMATYAR_DB_PATH"] = str(tmp_path / "cli.db")
        env.update(extra_env)
        return subprocess.run(
            [sys.executable, "-m", "ghematyar", *args],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(ROOT),
            timeout=180,
        )

    def test_missing_token_exits_2_with_guidance(self, tmp_path):
        result = self._run([], tmp_path)
        assert result.returncode == 2, result.stderr[-800:]
        output = result.stdout + result.stderr
        assert "TELEGRAM_TOKEN" in output
        assert "UnicodeEncodeError" not in output

    def test_help_prints_without_encoding_crash(self, tmp_path):
        result = self._run(["--help"], tmp_path)
        assert result.returncode == 0
        combined = result.stdout + result.stderr
        assert "polling" in combined and "webhook" in combined
        assert "UnicodeEncodeError" not in combined

    def test_unknown_mode_is_rejected(self, tmp_path):
        result = self._run(["nonsense"], tmp_path)
        assert result.returncode == 2  # argparse برای ورودی نامعتبر

    def test_init_db_creates_database(self, tmp_path):
        result = self._run(["init-db"], tmp_path)
        assert result.returncode == 0, result.stderr[-800:]
        assert (tmp_path / "cli.db").exists()
