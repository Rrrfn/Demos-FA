# -*- coding: utf-8 -*-
"""نمودار قیمت — رندر PNG از تاریخچهٔ واقعی.

نکته‌های مهم:

* نمودار فقط از نقاط *ثبت‌شده* ساخته می‌شود. اگر تاریخچه کم باشد،
  به‌جای کشیدن خط تخت یا درون‌یابی، صادقانه پیام «داده کافی نیست»
  برگردانده می‌شود.
* رندر در همان حلقهٔ رویداد انجام می‌شود ولی CPU-bound است؛ برای
  جلوگیری از قفل‌شدن ربات در حجم کوچک این نمودارها، به thread استخر
  واگذار می‌شود.
* فونت: matplotlib فونت فارسی پیش‌فرض ندارد؛ بنابراین محورها و برچسب‌ها
  با ارقام/متن لاتین کوتاه نوشته می‌شوند و متن فارسی در کپشن پیام تلگرام
  می‌آید. این انتخاب عامدانه است تا نمودار مربع‌نما (□□□) نشود.
"""
from __future__ import annotations

import asyncio
import io
import logging
from datetime import datetime

from ..core.models import PricePoint

log = logging.getLogger("ghematyar.charts")

MIN_POINTS = 3


class ChartUnavailable(Exception):
    """نمودار قابل ساخت نیست.

    دو دلیل کاملاً متفاوت دارد و لایهٔ نمایش باید تفاوتشان را بگوید:

    * ``reason="history"`` — دادهٔ ثبت‌شده کافی نیست (وضعیت موقتی)
    * ``reason="backend"`` — موتور رندر (matplotlib) نصب نیست
    """

    def __init__(
        self, have: int, need: int = MIN_POINTS, *, reason: str = "history"
    ) -> None:
        self.have = have
        self.need = need
        self.reason = reason
        super().__init__(f"chart unavailable ({reason}): {have}/{need}")

    @property
    def backend_missing(self) -> bool:
        """آیا مشکل از نبود موتور رندر است؟"""
        return self.reason == "backend"


def render_price_chart(
    title: str,
    points: list[PricePoint],
    *,
    unit: str = "toman",
    width: float = 7.2,
    height: float = 3.6,
) -> bytes:
    """رندر نمودار خطی قیمت و برگرداندن بایت‌های PNG.

    در نبود نقاط کافی :class:`ChartUnavailable` بالا می‌رود.
    """
    if len(points) < MIN_POINTS:
        raise ChartUnavailable(len(points))

    # وارد کردن تنبل matplotlib: بار اول گران است و ربات نباید برای
    # دستورهای غیرنموداری این هزینه را بپردازد. نبود آن به ChartUnavailable
    # با دلیل صریح تبدیل می‌شود تا ربات صادقانه بگوید نمودار غیرفعال است،
    # نه اینکه با ModuleNotFoundError بیفتد.
    try:
        import matplotlib
    except ImportError as exc:
        log.warning("matplotlib is not installed; the chart command is disabled")
        raise ChartUnavailable(len(points), reason="backend") from exc

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ordered = sorted(points, key=lambda p: p.captured_at)
    # محور زمان باید datetime باشد؛ matplotlib با time.struct_time کار نمی‌کند
    xs = [datetime.fromtimestamp(p.captured_at) for p in ordered]
    ys = [p.price for p in ordered]
    unit_label = "USD" if unit == "usd" else "Toman"

    fig, ax = plt.subplots(figsize=(width, height), dpi=130)
    fig.patch.set_facecolor("#ffffff")
    ax.set_facecolor("#fafafa")

    rising = ys[-1] >= ys[0]
    color = "#1a9c5b" if rising else "#d1435b"
    ax.plot(xs, ys, color=color, linewidth=2.0, solid_capstyle="round")
    ax.fill_between(xs, ys, min(ys), color=color, alpha=0.10)
    ax.scatter([xs[-1]], [ys[-1]], color=color, s=26, zorder=5)

    ax.set_title(f"{title}  ({unit_label})", fontsize=11, loc="left", color="#333333")
    ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.35)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.tick_params(axis="both", labelsize=8, colors="#666666")
    fig.autofmt_xdate(rotation=0, ha="center")
    fig.tight_layout(pad=1.1)

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", facecolor=fig.get_facecolor())
    plt.close(fig)
    buffer.seek(0)
    return buffer.read()


async def render_price_chart_async(
    title: str, points: list[PricePoint], *, unit: str = "toman"
) -> bytes:
    """نسخهٔ ناهمگام — رندر در thread جداگانه تا حلقهٔ رویداد قفل نشود."""
    return await asyncio.to_thread(render_price_chart, title, points, unit=unit)


__all__ = ["ChartUnavailable", "render_price_chart", "render_price_chart_async", "MIN_POINTS"]
