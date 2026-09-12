# -*- coding: utf-8 -*-
"""آزمون‌های صفحات داشبورد — رندر سمت سرور، فرم‌ها و صفحهٔ خطا.

داشبورد بدون جاوااسکریپت هم باید کامل کار کند؛ پس همهٔ صفحات اینجا با
کلاینت آزمون (بدون مرورگر) خوانده و بررسی می‌شوند.
"""
from __future__ import annotations

import re

import pytest

PAGES = ("/", "/jobs", "/saved", "/sources", "/activity", "/profile", "/proposal")


def html(client, path: str) -> str:
    response = client.get(path)
    assert response.status_code == 200, path
    return response.get_data(as_text=True)


def plain(text: str) -> str:
    """متن بدون نیم‌فاصله — برای مقایسه‌هایی که به ZWNJ حساس نباشند."""
    return text.replace("\u200c", "")


# ---------------------------------------------------------------- رندر پایه


@pytest.mark.parametrize("path", PAGES)
def test_every_page_renders(client, seeded, path):
    body = html(client, path)
    assert "<html" in body.lower()
    assert "کارینو" in body


@pytest.mark.parametrize("path", PAGES)
def test_pages_never_show_python_placeholders(client, seeded, path):
    """متغیر بدون مقدار نباید به‌شکل ``None`` یا ``Undefined`` به کاربر برسد."""
    body = html(client, path)
    assert "None" not in body
    assert "Undefined" not in body


def test_overview_shows_real_totals(client, seeded):
    body = html(client, "/")
    assert "آگهی" in body
    assert "امتیاز" in body


def test_jobs_list_renders_the_stored_jobs(client, seeded):
    body = html(client, "/jobs")
    assert "توسعه‌دهندهٔ پایتون و Flask" in body


def test_jobs_empty_state_is_explicit(client):
    """فهرست خالی باید توضیح داشته باشد، نه صفحهٔ سفید."""
    body = html(client, "/jobs")
    assert "آگهی" in body


# ---------------------------------------------------------------- جزئیات و تحلیل


def test_job_detail_explains_the_score(client, seeded):
    """خواستهٔ اصلی محصول: کاربر باید بفهمد امتیاز از کجا آمده."""
    body = html(client, f"/jobs/{seeded[0]}")
    assert "چرا این امتیاز" in body
    assert "تطبیق مهارت" in body
    assert "توسعه‌دهندهٔ پایتون و Flask" in body


def test_job_detail_shows_recommended_evidence(client, seeded):
    body = html(client, f"/jobs/{seeded[0]}")
    assert "کارهای من" in body or "نمونه" in body


def test_job_detail_offers_the_proposal_workshop(client, seeded):
    body = html(client, f"/jobs/{seeded[0]}")
    assert "پیشنهاد" in body


def test_unknown_job_page_renders_the_error_template(client, seeded):
    response = client.get("/jobs/999999")
    assert response.status_code == 404
    assert "کارینو" in response.get_data(as_text=True)


def test_unknown_path_renders_the_error_template(client):
    response = client.get("/no-such-page")
    assert response.status_code == 404
    assert "کارینو" in response.get_data(as_text=True)


# ---------------------------------------------------------------- اعتبارسنجی فیلترها


@pytest.mark.parametrize("query", ("min=abc", "page=0", "per_page=1000", "min=250"))
def test_invalid_filter_values_are_rejected(client, query):
    assert client.get(f"/jobs?{query}").status_code == 400


def test_unknown_sort_falls_back_to_score(client, seeded):
    """ترتیب ناشناخته در صفحه، برخلاف API، خطا نیست؛ به پیش‌فرض برمی‌گردد."""
    assert client.get("/jobs?sort=magic").status_code == 200


def test_score_preset_filter_narrows_the_list(client, seeded):
    all_rows = html(client, "/jobs").count('class="job-row"')
    high_rows = html(client, "/jobs?min=99").count('class="job-row"')
    assert all_rows == 3
    assert 0 <= high_rows < all_rows


# ---------------------------------------------------------------- فرم‌ها


def test_generating_a_proposal_from_the_form_redirects_back(client, seeded):
    job_id = seeded[0]
    response = client.post(f"/jobs/{job_id}/proposal",
                           data={"tone": "formal", "variant": "standard"})
    assert response.status_code == 302
    assert f"/jobs/{job_id}" in response.headers["Location"]

    body = html(client, f"/jobs/{job_id}")
    assert "هنوز پیشنهادی برای این آگهی ساخته نشده است" not in body
    assert plain("قاعده‌محور") in plain(body)
    assert "نویسنده" in body


def test_toggling_saved_from_the_form(client, seeded):
    job_id = seeded[0]
    response = client.post(f"/saved/{job_id}/toggle", data={"next": "/saved"})
    assert response.status_code == 302
    assert html(client, "/saved").count('class="job-row"') == 1

    client.post(f"/saved/{job_id}/toggle", data={"next": "/saved"})
    assert "خالی است" in html(client, "/saved")


def test_toggle_for_unknown_job_is_404(client, seeded):
    assert client.post("/saved/999999/toggle").status_code == 404


def test_rescoring_from_the_form(client, seeded):
    response = client.post(f"/jobs/{seeded[0]}/rescore")
    assert response.status_code == 302


def test_rescore_for_unknown_job_is_404(client, seeded):
    assert client.post("/jobs/999999/rescore").status_code == 404


def test_proposal_form_for_unknown_job_is_404(client, seeded):
    assert client.post("/jobs/999999/proposal", data={}).status_code == 404


# ---------------------------------------------------------------- کارگاه پیشنهاد


def test_proposal_workshop_can_preselect_a_job(client, seeded):
    body = html(client, f"/proposal?job={seeded[0]}")
    assert "توسعه‌دهندهٔ پایتون و Flask" in body


# ---------------------------------------------------------------- پروفایل


def test_profile_page_lists_skills_and_portfolio(client, seeded):
    body = html(client, "/profile")
    assert "پایتون" in body
    assert "کارینو" in body          # نام یکی از نمونه‌کارها


# ---------------------------------------------------------------- قاعدهٔ نمایش


_TAG = re.compile(r"<[^>]+>")


def _chrome(body: str) -> str:
    """متن *قابل مشاهدهٔ* نوار کنار و پانویس — نه متن آگهی‌ها و نه ویژگی‌های تگ.

    تگ‌ها حذف می‌شوند چون مقدارهایی مثل ``width="30"`` رقم دارند ولی کاربر
    آن‌ها را نمی‌بیند؛ سنجش باید روی متن باشد، نه روی همهٔ بایت‌های HTML.
    """
    parts = []
    for start, end in (("<aside", "</aside>"), ("<footer", "</footer>")):
        begin = body.find(start)
        stop = body.find(end, begin)
        if begin != -1 and stop != -1:
            parts.append(body[begin:stop])
    return _TAG.sub(" ", "".join(parts))


@pytest.mark.parametrize("path", PAGES)
def test_interface_chrome_has_no_latin_digits(client, seeded, path):
    """متن ساختاری رابط (شمارهٔ نسخه و شمارنده‌ها) نباید رقم لاتین داشته باشد."""
    chrome = _chrome(html(client, path))
    offenders = [ch for ch in chrome if ch.isdigit() and ch.isascii()]
    assert not offenders, f"{path}: {offenders}"


def test_activity_page_translates_machine_keys(client, seeded):
    """شناسهٔ رویداد و کلیدهای ``meta`` هرگز خام به کاربر نشان داده نمی‌شوند."""
    from karino.storage import activity

    activity.log("ingest_done", "۲ آگهی تازه ثبت شد", level="success",
                 meta={"new": 2, "fetched": 5, "writer": "rule_based",
                       "internal_only": "value"})
    body = html(client, "/activity")

    assert "جمع‌آوری" in body                 # عنوان فارسی رویداد
    assert "تازه: ۲" in body
    assert "واکشی‌شده: ۵" in body
    assert "نویسنده: قاعده‌محور" in body
    for token in ("ingest_done", "internal_only", "rule_based", "writer"):
        assert token not in body, token


def test_sources_page_spells_out_milliseconds(client, seeded):
    """واحد مدت زمان باید فارسی باشد، نه مختصر انگلیسی ``ms``."""
    from karino.storage import sources as sources_repo

    sources_repo.record("remotive", ok=True, jobs=4, duration_ms=1506)
    assert "میلی‌ثانیه" in html(client, "/sources")


def test_proposal_message_is_human_readable(client, seeded):
    """پیام ساخت پیشنهاد نباید کدهای ``formal/standard`` را نشان دهد."""
    client.post(f"/api/v1/jobs/{seeded[0]}/proposal", json={})
    body = html(client, "/activity")
    assert "رسمی و حرفه‌ای" in body
    assert "formal/standard" not in body
    assert "رسمی و حرفه‌ای (استاندارد)" in body


def test_environment_badge_is_persian(client, seeded):
    """نشان محیط اجرا باید فارسی باشد؛ «development» در رابط ناتمام است."""
    body = html(client, "/")
    assert "توسعه" in body
    assert ">development<" not in body.replace("\n", "")


def test_presentation_labels_cover_every_kind_and_env():
    """هر شناسهٔ رویدادی که کد ثبت می‌کند باید برچسب فارسی داشته باشد."""
    import pathlib
    import re as _re

    from karino.web.presentation import ACTIVITY_KIND_LABELS, env_label

    root = pathlib.Path(__file__).resolve().parent.parent / "karino"
    logged: set[str] = set()
    for path in root.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        logged |= set(_re.findall(r'(?:activity\.log|level\.log)\(\s*"([a-z_]+)"', source))

    missing = sorted(logged - set(ACTIVITY_KIND_LABELS))
    assert not missing, f"unlabelled activity kinds: {missing}"

    for env in ("development", "production", "test", "", None):
        assert env_label(env) and not any(
            ch.isdigit() and ch.isascii() for ch in env_label(env))
