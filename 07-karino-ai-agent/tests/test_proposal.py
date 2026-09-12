# -*- coding: utf-8 -*-
"""آزمون‌های پیشنهادنویس — مدرک‌محوری، لحن، طول و بازگشت امن LLM.

خواستهٔ محصول دو چیز است: پیشنهاد باید *مخصوص همان آگهی* باشد (نه قالب
ثابت) و اگر مدل زبانی از دسترس خارج شد، سامانه نباید بشکند. هر دو اینجا
آزموده می‌شوند.
"""
from __future__ import annotations

import json
import time
from dataclasses import replace

import pytest

from karino.core.models import Job
from karino.core.text import search_key
from karino.pipeline.proposal import (DEFAULT_TONE, SYSTEM_PROMPT, TONES,
                                      build_proposal)
from karino.pipeline.scoring import score
from karino.profile import PORTFOLIO


def build_job(**overrides) -> Job:
    data = dict(
        source="test", external_id="p-1",
        title="توسعه‌دهندهٔ پایتون برای ساخت API",
        company="شرکت آزمون",
        description="نیاز به توسعه‌دهندهٔ پایتون با Flask و دیتابیس SQL. دورکاری کامل، پروژه‌ای.",
        tags=["python", "flask", "sql"],
        location="دورکاری", remote=True, employment="freelance",
        published_ts=int(time.time()) - 3600,
    )
    data.update(overrides)
    return Job(**data)


def has_latin_digit(text: str) -> bool:
    return any(ch.isdigit() and ch.isascii() for ch in text)


@pytest.fixture()
def scored_job():
    job = build_job()
    return job, score(job)


# ---------------------------------------------------------------- قاعده‌محور


def test_default_writer_is_rule_based(scored_job):
    job, result = scored_job
    body, writer = build_proposal(job, result)
    assert writer == "rule_based"
    assert len(body) > 200


def test_proposal_mentions_the_actual_job(scored_job):
    """پیشنهاد باید نشان دهد آگهی خوانده شده: عنوان و کارفرما در متن بیایند."""
    job, result = scored_job
    body, _ = build_proposal(job, result)
    assert job.title in body
    assert job.company in body


def test_proposal_without_company_omits_dangling_preposition(scored_job):
    """نام کارفرمای خالی نباید به «در » آویزان بدل شود."""
    job = build_job(company="", title="پروژهٔ ساخت API با پایتون")
    result = score(job)
    body, _ = build_proposal(job, result)
    assert f"آگهی «{job.title}» را دیدم" in body
    assert "«»" not in body


def test_evidence_block_cites_real_portfolio_projects(scored_job):
    job, result = scored_job
    body, _ = build_proposal(job, result)
    assert "کارهای من" in body
    titles = [project.title for project in PORTFOLIO]
    assert any(title in body for title in titles)


def test_evidence_is_job_specific_not_a_fixed_list(scored_job):
    """دو آگهی با مهارت‌های متفاوت نباید متن یکسان بگیرند."""
    api_body, _ = build_proposal(*scored_job)
    data_job = build_job(title="دیتاآنالیست با پایتون و pandas و داشبورد",
                         description="تحلیل دادهٔ فروش با pandas و ساخت داشبورد. " * 6,
                         tags=["python", "pandas", "dashboard"], remote=True)
    data_body, _ = build_proposal(data_job, score(data_job))
    assert api_body != data_body


def test_tones_change_the_greeting(scored_job):
    job, result = scored_job
    bodies = {key: build_proposal(job, result, tone=key)[0] for key in TONES}
    assert len(set(bodies.values())) == len(TONES)
    assert TONES["formal"].greeting in bodies["formal"]
    assert TONES["concise"].greeting in bodies["concise"]


def test_unknown_tone_falls_back_to_default(scored_job):
    job, result = scored_job
    fallback, _ = build_proposal(job, result, tone="not_a_tone")
    default, _ = build_proposal(job, result, tone=DEFAULT_TONE)
    assert fallback == default


def test_short_variant_drops_the_method_block(scored_job):
    job, result = scored_job
    short, _ = build_proposal(job, result, variant="short")
    standard, _ = build_proposal(job, result)
    assert "روش کار من" not in short
    assert "روش کار من" in standard
    assert len(short) < len(standard)


def test_proposal_works_without_a_score():
    """نویسنده نباید به امتیاز وابسته باشد؛ آگهی تازه ممکن است امتیاز نداشته باشد."""
    job = build_job()
    body, writer = build_proposal(job, None)
    assert writer == "rule_based"
    assert job.title in body
    assert TONES[DEFAULT_TONE].greeting in body


def test_proposal_mentions_gaps_honestly(scored_job):
    """اگر شکاف مهمی هست، پنهان نمی‌شود؛ با صداقت اعلام می‌شود."""
    job = build_job(title="مهندس یادگیری ماشین و NLP",
                    description="کار با scikit-learn، مدل زبانی و محاسبات عددی برای پیش‌بینی. " * 6,
                    tags=["machine learning", "nlp"])
    result = score(job)
    assert result.missing_skills
    body, _ = build_proposal(job, result)
    assert "عمق کمتری دارم" in body


def test_proposal_never_leaks_latin_digits(scored_job):
    """قاعدهٔ محصول: متن نمایشی هیچ رقم لاتینی ندارد."""
    job, result = scored_job
    body, _ = build_proposal(job, result)
    assert not has_latin_digit(body), body


def test_proposal_is_deterministic(scored_job):
    job, result = scored_job
    assert build_proposal(job, result)[0] == build_proposal(job, result)[0]


# ---------------------------------------------------------------- آداپتور LLM


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture()
def llm_settings(monkeypatch, settings):
    tuned = replace(settings, llm_url="https://llm.example/v1", llm_key="secret")
    monkeypatch.setattr("karino.pipeline.proposal.get_settings", lambda refresh=False: tuned)
    return tuned


def test_llm_writer_used_when_available(scored_job, llm_settings, monkeypatch):
    captured: dict = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["auth"] = request.headers.get("Authorization")
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse({"choices": [{"message": {"content": "متن روان‌شدهٔ نهایی"}}]})

    monkeypatch.setattr("karino.pipeline.proposal.urllib.request.urlopen", fake_urlopen)

    job, result = scored_job
    body, writer = build_proposal(job, result)

    assert writer == "llm"
    assert body == "متن روان‌شدهٔ نهایی"
    assert captured["url"] == "https://llm.example/v1/chat/completions"
    assert captured["auth"] == "Bearer secret"
    assert captured["body"]["model"] == llm_settings.llm_model
    assert captured["body"]["messages"][0]["content"] == SYSTEM_PROMPT
    assert job.title in captured["body"]["messages"][1]["content"]


def test_llm_network_failure_falls_back_to_draft(scored_job, llm_settings, monkeypatch):
    """قطعی مدل نباید پیشنهادنویس را از کار بیندازد."""
    def boom(request, timeout=None):
        raise OSError("connection refused")

    monkeypatch.setattr("karino.pipeline.proposal.urllib.request.urlopen", boom)

    job, result = scored_job
    body, writer = build_proposal(job, result)

    assert writer == "rule_based"
    assert job.title in body


def test_llm_malformed_response_falls_back(scored_job, llm_settings, monkeypatch):
    monkeypatch.setattr("karino.pipeline.proposal.urllib.request.urlopen",
                        lambda request, timeout=None: _FakeResponse({"unexpected": True}))

    job, result = scored_job
    _, writer = build_proposal(job, result)
    assert writer == "rule_based"


def test_llm_empty_answer_falls_back(scored_job, llm_settings, monkeypatch):
    monkeypatch.setattr(
        "karino.pipeline.proposal.urllib.request.urlopen",
        lambda request, timeout=None: _FakeResponse(
            {"choices": [{"message": {"content": "   "}}]}))

    job, result = scored_job
    _, writer = build_proposal(job, result)
    assert writer == "rule_based"


def test_llm_prompt_forbids_fabrication():
    """پرامپت باید صریحاً جعل نام نمونه‌کار و پشتهٔ فنی را ممنوع کند."""
    assert "جعل نکن" in SYSTEM_PROMPT
    assert search_key("نمونه‌کار") in search_key(SYSTEM_PROMPT)
