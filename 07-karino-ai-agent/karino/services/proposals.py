# -*- coding: utf-8 -*-
"""سرویس پیشنهاد — ساخت، کش و بازگرداندن متن همراه با زمینهٔ آگهی.

تفکیک این لایه از خود نویسنده لازم است چون دو کار متفاوت انجام می‌شود:
``pipeline.proposal`` متن را می‌سازد، ولی اینجا تصمیم گرفته می‌شود چه
زمانی از کش خوانده شود، چه زمانی دوباره ساخته شود و چه چیزی به کاربر
نمایش داده شود.
"""
from __future__ import annotations

import json

from ..core.errors import NotFoundError
from ..core.models import Job, ScoreResult
from ..pipeline.proposal import (DEFAULT_TONE, TONES, VARIANT_LABELS,
                                 build_proposal)
from ..storage import activity, jobs as jobs_repo, proposals as proposals_repo
from ..storage import scores as scores_repo


def generate(job_id: int, *, tone: str = DEFAULT_TONE, variant: str = "standard",
             force: bool = False) -> dict:
    """ساخت (یا خواندن از کش) پیشنهاد یک آگهی.

    ``force=True`` کش را نادیده می‌گیرد — لازم است چون ممکن است پروفایل یا
    تنظیمات LLM تغییر کرده باشد و متن قدیمی دیگر معتبر نباشد.
    """
    row = jobs_repo.get(job_id)
    if not row:
        raise NotFoundError("آگهی مورد نظر پیدا نشد.")

    tone = tone if tone in TONES else DEFAULT_TONE
    variant = variant if variant in ("standard", "short") else "standard"

    if not force:
        cached = proposals_repo.get(job_id, tone=tone, variant=variant)
        if cached and cached["body"]:
            return _payload(row, cached["body"], cached["writer"], tone, variant, cached=True)

    job = _job_from_row(row)
    score_result = _score_from_row(scores_repo.get(job_id))

    body, writer = build_proposal(job, score_result, tone=tone, variant=variant)
    proposals_repo.save(job_id, body, writer, tone=tone, variant=variant)
    activity.log("proposal_created",
                 f"پیشنهاد {TONES[tone].label} "
                 f"({VARIANT_LABELS.get(variant, variant)}) برای آگهی "
                 f"«{row['title'][:60]}» ساخته شد",
                 level="success",
                 meta={"job_id": job_id, "writer": writer, "tone": tone})

    return _payload(row, body, writer, tone, variant, cached=False)


def latest(job_id: int) -> dict | None:
    row = proposals_repo.latest_for_job(job_id)
    if not row:
        return None
    return {"body": row["body"], "writer": row["writer"], "tone": row["tone"],
            "variant": row["variant"], "created_ts": row["created_ts"]}


def _payload(row, body: str, writer: str, tone: str, variant: str, *,
             cached: bool) -> dict:
    return {
        "job_id": int(row["id"]),
        "job_title": row["title"],
        "company": row["company"] or "",
        "tone": tone,
        "tone_label": TONES[tone].label,
        "variant": variant,
        "writer": writer,
        "writer_label": "مدل زبانی" if writer == "llm" else "موتور قاعده‌محور",
        "cached": cached,
        "body": body,
        "char_count": len(body),
        "word_count": len(body.split()),
    }


def _job_from_row(row) -> Job:
    try:
        tags = json.loads(row["tags"] or "[]")
    except (ValueError, TypeError):
        tags = []
    return Job(
        source=row["source"], external_id=row["external_id"], title=row["title"],
        company=row["company"] or "", url=row["url"] or "",
        description=row["description"] or "",
        tags=tags if isinstance(tags, list) else [],
        location=row["location"] or "", remote=bool(row["remote"]),
        employment=row["employment"] or "", salary_text=row["salary_text"] or "",
        salary_min=row["salary_min"], salary_max=row["salary_max"],
        published_ts=row["published_ts"], fingerprint=row["fingerprint"] or "",
    )


def _score_from_row(row) -> ScoreResult | None:
    if not row:
        return None

    def load(field: str) -> list:
        try:
            value = json.loads(row[field] or "[]")
        except (ValueError, TypeError):
            return []
        return value if isinstance(value, list) else []

    from ..core.models import ScoreFactor

    factors = []
    for item in load("factors"):
        if isinstance(item, dict):
            factors.append(ScoreFactor(
                key=item.get("key", ""), label=item.get("label", ""),
                points=float(item.get("points", 0)),
                max_points=float(item.get("max_points", 0)),
                detail=item.get("detail", ""),
                evidence=list(item.get("evidence", []) or [])))

    return ScoreResult(
        total=int(row["total"]), verdict=row["verdict"],
        matched_skills=load("matched"), missing_skills=load("missing"),
        factors=factors, reasons=load("reasons"),
        seniority=row["seniority"] or "unknown",
        engagement=row["engagement"] or "unknown",
    )


__all__ = ["generate", "latest"]
