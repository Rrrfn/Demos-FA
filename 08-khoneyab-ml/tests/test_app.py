# -*- coding: utf-8 -*-
"""آزمون اجرای واقعی برنامه — پوستهٔ برنامه و هر هفت صفحه.

این آزمون به‌جای بازبینی دستی، خود برنامه را با ``AppTest`` اجرا می‌کند:
استثناها، خطاهای نمایشی و صفحهٔ خالی لو می‌روند. اگر روزی صفحه‌ای تغییر کند و
دیگر بالا نیاید، همین‌جا معلوم می‌شود.

دو لایه آزمون می‌شود:

* **پوستهٔ برنامه** از ``app.py`` اجرا می‌شود — ناوبری، نوار کنار، پوستهٔ ظاهری.
* **هر صفحه** از یک اسکریپت کوچک اجرا می‌شود که فقط همان نما را صدا می‌زند.
  دلیلش دو چیز است: ``st.navigation`` صفحهٔ جاری را از مسیر نشانی برمی‌دارد و
  در محیط آزمون نمی‌توان صفحه‌ها را با مسیر عوض کرد؛ و اسکریپت باید با کدگذاری
  UTF-8 روی دیسک نوشته شود، وگرنه روی ویندوز متن فارسی در فایل محلی خراب می‌شود.
"""
from __future__ import annotations

import os
import re

import pytest

pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app.py")
TIMEOUT = 120

#: نام صفحه → (نام ماژول نما، پارامترهای نشانی).
VIEWS = {
    "home": ("home", {}),
    "search": ("search", {}),
    "compare": ("compare", {}),
    "estimate": ("predict", {}),
    "analytics": ("analytics", {}),
    "methodology": ("methodology", {}),
    "listing": ("detail", {"item": "KH-1001"}),
}

ENTRY_TEMPLATE = """\
# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, {root!r})
from khoneyab.views import {module} as _view
_view.render()
"""


def visible_text(app: AppTest) -> str:
    """متن دیده‌شدنی صفحه — بدون تگ‌های HTML.

    شاخص‌های این رابط با HTML سفارشی ساخته می‌شوند، نه با ``st.metric``؛ پس
    برای بررسی متن باید همان HTML جدا شود. مقایسه روی متن بدون تگ انجام
    می‌شود چون خود تگ‌ها (``width:100%``) رقم لاتین دارند و ربطی به متن ندارند.
    """
    raw = " ".join(str(block.value) for block in app.markdown)
    # فرمول و نمونه‌کد لاتین می‌مانند (قرارداد جهانی نوشتن ریاضی و کد)؛
    # پس از سنجش خارج می‌شوند، ولی نثر و اعداد رابط باید فارسی باشند.
    raw = re.sub(r"<pre.*?</pre>", " ", raw, flags=re.S)
    raw = re.sub(r"<code.*?</code>", " ", raw, flags=re.S)
    return re.sub(r"<[^>]+>", " ", raw)


def _assert_clean(app: AppTest, name: str) -> None:
    assert not app.exception, f"صفحهٔ {name} استثنا داد: {[str(i) for i in app.exception]}"
    assert not app.error, f"صفحهٔ {name} خطای نمایشی دارد: {[str(i) for i in app.error]}"
    rendered = (len(app.markdown) + len(app.dataframe) + len(app.metric)
                + len(app.selectbox) + len(app.multiselect))
    assert rendered > 0, f"صفحهٔ {name} هیچ محتوایی رندر نکرد"


@pytest.fixture(scope="module")
def shell():
    app = AppTest.from_file(APP, default_timeout=TIMEOUT)
    app.run()
    return app


def render_view(tmp_path, name: str) -> AppTest:
    """اجرای یک نما از طریق اسکریپت موقت با کدگذاری UTF-8."""
    module, params = VIEWS[name]
    script = tmp_path / f"entry_{name}.py"
    script.write_text(ENTRY_TEMPLATE.format(root=ROOT, module=module), encoding="utf-8")
    app = AppTest.from_file(str(script), default_timeout=TIMEOUT)
    for key, value in params.items():
        app.query_params[key] = value
    app.run()
    return app


@pytest.fixture()
def home_app(tmp_path):
    return render_view(tmp_path, "home")


def test_app_shell_starts_clean(shell):
    _assert_clean(shell, "پوسته")


def test_app_shell_shows_the_synthetic_notice(shell):
    text = " ".join(str(block.value) for block in shell.markdown)
    assert "سینتتیک" in text


@pytest.mark.parametrize("name", sorted(VIEWS))
def test_every_page_renders(tmp_path, name):
    _assert_clean(render_view(tmp_path, name), name)


def test_home_mentions_the_platform(home_app):
    text = " ".join(str(block.value) for block in home_app.markdown)
    assert "خان" in text


def test_home_warns_that_data_is_synthetic(home_app):
    text = " ".join(str(block.value) for block in home_app.markdown)
    assert "سینتتیک" in text or "واقعی" in text


def test_search_page_offers_filters(tmp_path):
    app = render_view(tmp_path, "search")
    assert app.selectbox or app.multiselect, "فیلترهای جست‌وجو رندر نشدند"


def test_estimate_page_produces_a_prediction(tmp_path):
    text = visible_text(render_view(tmp_path, "estimate"))
    assert "تومان" in text or "میلیارد" in text
    assert "بازه" in text          # بازهٔ اطمینان هم باید نمایش داده شود


def test_analytics_page_renders_tables_and_charts(tmp_path):
    app = render_view(tmp_path, "analytics")
    assert len(app.dataframe) >= 1, "جدول مناطق رندر نشد"


def test_detail_page_shows_the_listing_identifier(tmp_path):
    """شناسه در رابط با رقم فارسی دیده می‌شود، ولی پیوندها با شناسهٔ خام کار می‌کنند."""
    text = visible_text(render_view(tmp_path, "listing"))
    assert "KH-\u06f1\u06f0\u06f0\u06f1" in text
    assert "KH-1001" not in text


def test_detail_page_with_a_bad_identifier_is_handled(tmp_path):
    script = tmp_path / "entry_missing.py"
    script.write_text(ENTRY_TEMPLATE.format(root=ROOT, module="detail"), encoding="utf-8")
    app = AppTest.from_file(str(script), default_timeout=TIMEOUT)
    app.query_params["item"] = "not-a-real-id"
    app.run()
    assert not app.exception
    text = " ".join(str(block.value) for block in app.markdown)
    assert "پیدا نشد" in text


@pytest.mark.parametrize("name", ["home", "search", "estimate", "analytics",
                                 "methodology", "listing"])
def test_no_latin_digits_in_visible_text(tmp_path, name):
    """در رابط فارسی هیچ رقم لاتینی نباید دیده شود.

    رقم‌های لاتین فقط در جاهایی مجازند که در متن دیده نمی‌شوند (نشانی عکس،
    عرض و ارتفاع تگ). این آزمون همان مرز را نگه می‌دارد.
    """
    text = visible_text(render_view(tmp_path, name))
    offenders = [text[max(0, hit.start() - 30): hit.start() + 20]
                 for hit in re.finditer(r"[0-9]", text)]
    assert not offenders, f"صفحهٔ {name} رقم لاتین دارد: {offenders[:3]}"
