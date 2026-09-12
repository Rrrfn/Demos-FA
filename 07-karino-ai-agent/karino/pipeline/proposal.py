# -*- coding: utf-8 -*-
"""نویسندهٔ پیشنهاد — مدرک‌محور، کوتاه و حرفه‌ای.

ساختار پیشنهاد سه بخش دارد و هر بخش از دادهٔ واقعی همان آگهی تغذیه می‌شود:

۱) **قلاب**: نام پروژه و مهم‌ترین مهارت متقابل — نشان می‌دهد آگهی خوانده شده.
۲) **مدرک**: دو یا سه نمونه‌کار که *مهارت‌های منطبق همان آگهی* را پوشش می‌دهند.
   انتخاب نمونه‌کار پویا است، نه فهرست ثابت؛ وگرنه پیشنهاد «قالبی» به نظر می‌رسد.
۳) **روش کار**: تعهدهای مشخص تحویل.

اگر ``KARINO_LLM_URL`` تنظیم شده باشد، متن قاعده‌محور به‌عنوان پیش‌نویس به
مدل داده می‌شود و نسخهٔ روان‌ترش برمی‌گردد؛ ولی هر خطای شبکه/سهمیه/قطعی
مدل **بی‌صدا** به همان پیش‌نویس قاعده‌محور برمی‌گردد. یعنی پیشنهادنویس هرگز
به‌خاطر LLM از کار نمی‌افتد.
"""
from __future__ import annotations

import json
import logging
import urllib.request
from dataclasses import dataclass

from ..config import get_settings
from ..core.errors import ProviderError
from ..core.models import (ENGAGEMENT_LABELS, SENIORITY_LABELS, Job,
                          ScoreResult)
from ..profile import PortfolioProject, fa_names, relevant_projects

log = logging.getLogger("krn.proposal")

WRITERS = ("rule_based", "llm")


@dataclass(frozen=True)
class Tone:
    key: str
    label: str
    greeting: str
    closing: str


TONES: dict[str, Tone] = {
    "formal": Tone(
        key="formal",
        label="رسمی و حرفه‌ای",
        greeting="سلام و احترام،",
        closing="با احترام،",
    ),
    "concise": Tone(
        key="concise",
        label="کوتاه و مستقیم",
        greeting="سلام،",
        closing="با تشکر،",
    ),
    "consultative": Tone(
        key="consultative",
        label="مشورتی و همکارانه",
        greeting="سلام، امیدوارم روز خوبی داشته باشید.",
        closing="خوشحال می‌شوم گفتگو را ادامه دهیم،",
    ),
}

DEFAULT_TONE = "formal"

#: برچسب فارسی طول پیشنهاد — برای پیام‌های کاربرپسند و لاگ فعالیت
VARIANT_LABELS: dict[str, str] = {"standard": "استاندارد", "short": "کوتاه"}


def build_proposal(job: Job, score: ScoreResult | None = None, *,
                   tone: str = DEFAULT_TONE,
                   variant: str = "standard") -> tuple[str, str]:
    """برگشت: (متن پیشنهاد، نام نویسنده).

    ``variant``: ``standard`` یا ``short`` — برای پیام‌های کوتاه پلتفرم‌ها.
    """
    tone_obj = TONES.get(tone) or TONES[DEFAULT_TONE]
    projects = relevant_projects(score.matched_skills if score else [],
                                 limit=2 if variant == "short" else 3)
    if not projects and score is None:
        projects = relevant_projects([], limit=1)

    draft = _rule_based(job, score, tone_obj, projects, variant)

    settings = get_settings()
    if settings.llm_url:
        try:
            return _llm(job, draft, settings), "llm"
        except Exception as exc:  # noqa: BLE001 — بازگشت امن عمدی
            log.warning("LLM unavailable, falling back to rule-based draft: %s", exc)
    return draft, "rule_based"


# ---------------------------------------------------------------- قاعده‌محور


def _rule_based(job: Job, score: ScoreResult | None, tone: Tone,
                projects: list[PortfolioProject], variant: str) -> str:
    title = job.title or "این پروژه"
    company = job.company.strip()
    target = f"«{title}»" + (f" در {company}" if company else "")

    parts: list[str] = [tone.greeting, ""]
    parts.append(f"آگهی {target} را دیدم و دقیقاً روی همین حوزه کار کرده‌ام.")

    hook = _hook_line(score)
    if hook:
        parts.append(hook)

    evidence = _evidence_block(projects, score)
    if evidence:
        parts.append("")
        parts.append("نمونه‌های مرتبط از کارهای من:")
        parts.append(evidence)

    fit = _fit_block(score)
    if fit:
        parts.append("")
        parts.append(fit)

    if variant != "short":
        parts.append("")
        parts.append("روش کار من:")
        parts.extend(_method_lines())
        parts.append("")
        parts.append("اگر مایل باشید، همین‌جا لینک زندهٔ نمونه‌ها را می‌فرستم "
                     "و دربارهٔ جزئیات و زمان‌بندی صحبت می‌کنیم.")

    parts.append("")
    parts.append(tone.closing)
    parts.append("— توسعه‌دهنده پایتون، اتوماسیون و داده")

    return "\n".join(parts)


def _hook_line(score: ScoreResult | None) -> str:
    """جملهٔ تطبیق — از مهارت‌های واقعی همان آگهی ساخته می‌شود."""
    if not score or not score.matched_skills:
        return ""
    top = fa_names(sorted(score.matched_skills, key=lambda k: -_weight(k))[:3])
    if not top:
        return ""
    return "نقاط هم‌پوشانی اصلی: " + "، ".join(top) + "."


def _weight(key: str) -> int:
    from ..profile import SKILLS

    return SKILLS[key].weight if key in SKILLS else 0


def _evidence_block(projects: list[PortfolioProject],
                    score: ScoreResult | None) -> str:
    lines: list[str] = []
    for project in projects:
        shared = [s for s in project.skills if score and s in score.matched_skills]
        names = fa_names(shared, 3)
        suffix = f" — {project.metric}" if project.metric else ""
        stack = "، ".join(project.stack)
        relevance = f" (مرتبط با {'، '.join(names)})" if names else ""
        lines.append(f"• {project.title}: {project.summary}{suffix}")
        lines.append(f"  پشتهٔ فنی: {stack}{relevance}")
    return "\n".join(lines)


def _fit_block(score: ScoreResult | None) -> str:
    if not score:
        return ""
    lines: list[str] = []

    if score.seniority and score.seniority != "unknown":
        level = SENIORITY_LABELS.get(score.seniority, score.seniority)
        lines.append(f"سطح مورد نیاز آگهی ({level}) با تجربهٔ من هم‌خوان است.")
    if score.engagement and score.engagement != "unknown":
        kind = ENGAGEMENT_LABELS.get(score.engagement, score.engagement)
        lines.append(f"نوع همکاری پیشنهادی شما ({kind}) برای من قابل انجام است.")
    if score.remote:
        lines.append("دورکاری برای من کاملاً امکان‌پذیر است.")
    if score.missing_skills:
        gaps = fa_names([k for k in score.missing_skills if _weight(k) >= 9], 2)
        if gaps:
            lines.append("در «" + "، ".join(gaps) + "» عمق کمتری دارم، ولی "
                         "معادلش را با ابزارهای دیگر پیاده کرده‌ام و سریع یاد می‌گیرم.")
    return " ".join(lines)


def _method_lines() -> list[str]:
    return [
        "• پیش از شروع، ورودی‌ها، خروجی مورد انتظار و معیار پذیرش را با شما نهایی می‌کنم.",
        "• تحویل مرحله‌ای: اول یک نسخهٔ قابل‌مشاهده، بعد اصلاحات شما.",
        "• کد مستند و قابل تحویل، همراه با راهنمای اجرا.",
    ]


# ---------------------------------------------------------------- آداپتور LLM

SYSTEM_PROMPT = (
    "تو یک فریلنسر ارشد پایتون و داده هستی. پیش‌نویس زیر را روان‌تر، طبیعی‌تر و "
    "کوتاه‌تر کن. متن فارسی روان بنویس. ساختار بخش‌ها، نام نمونه‌کارها و پشتهٔ فنی "
    "را حذف یا جعل نکن. ادعای تازه‌ای که در پیش‌نویس نیست اضافه نکن. فقط متن نهایی "
    "پیشنهاد را بنویس."
)


def _llm(job: Job, draft: str, settings) -> str:
    """فراخوانی مدل سازگار با OpenAI؛ خطا به ``ProviderError`` بدل می‌شود."""
    url = settings.llm_url.rstrip("/")
    if not url.endswith("/chat/completions"):
        url = url + "/chat/completions"

    payload = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"عنوان آگهی: {job.title}\n\n{draft}"},
        ],
        "temperature": 0.6,
        "max_tokens": 500,
    }
    headers = {"Content-Type": "application/json"}
    if settings.llm_key:
        headers["Authorization"] = f"Bearer {settings.llm_key}"

    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=settings.http_timeout + 10) as response:
            body = json.loads(response.read().decode("utf-8", "replace"))
    except Exception as exc:  # noqa: BLE001
        raise ProviderError("نویسندهٔ LLM پاسخ نداد", detail=str(exc)[:200]) from exc

    try:
        text = body["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, AttributeError, TypeError) as exc:
        raise ProviderError("پاسخ LLM ساختار مورد انتظار را نداشت",
                            detail=str(body)[:200]) from exc

    if not text:
        raise ProviderError("پاسخ LLM خالی بود")
    return text
