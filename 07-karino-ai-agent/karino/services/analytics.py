# -*- coding: utf-8 -*-
"""تحلیل و تجمیع — همهٔ اعدادی که داشبورد نشان می‌دهد از اینجا می‌آید.

هیچ عددی در قالب HTML سخت‌کد نمی‌شود و هیچ نموداری تزئینی نیست: هر مقدار
خروجی این لایه، از پایگاه دادهٔ واقعی محاسبه شده است. اگر داده کافی نباشد،
همان «دادهٔ کافی نیست» برگردانده می‌شود، نه یک عدد ساختگی.
"""
from __future__ import annotations

import json
import time

from ..config import Settings, get_settings
from ..core.models import VERDICT_LABELS
from ..core.text import fa_number
from ..pipeline.scoring import FACTOR_LABELS
from ..profile import TOP_SCORE_THRESHOLD, match_skills
from ..storage import activity, jobs as jobs_repo, proposals as proposals_repo
from ..storage import saved as saved_repo, scores as scores_repo
from ..storage import sources as sources_repo


def overview(*, settings: Settings | None = None, now: int | None = None) -> dict:
    """نمای کلی — اعداد کلیدی، توزیع امتیاز، سلامت منابع و بهترین‌ها."""
    settings = settings or get_settings()
    now = int(now if now is not None else time.time())

    total_jobs = jobs_repo.count()
    new_today = jobs_repo.count_since(now - 86_400)
    new_week = jobs_repo.count_since(now - 7 * 86_400)
    distribution = scores_repo.distribution()
    average = scores_repo.average()

    # «بهترین‌ها» با رتبه‌بندی واقعی انتخاب می‌شود، نه با آستانهٔ سخت.
    # دلیلش این است که با آستانهٔ ثابت، در منبعی که اکثر آگهی‌ها تخصصی
    # نیستند، این بخش خالی می‌ماند و کاربر فکر می‌کند سامانه کار نکرده؛
    # در حالی که پاسخ درست «کمترین تطابق‌ها را نشان بده» است. آستانهٔ
    # «قوی» همچنان برای شمارش و برچسب‌گذاری جداگانه محاسبه می‌شود.
    top_rows, top_total = jobs_repo.query(sort="score", per_page=5)
    strong = distribution["72-84"] + distribution["85-100"]

    return {
        "total_jobs": total_jobs,
        "new_today": new_today,
        "new_week": new_week,
        "average_score": average,
        "strong_matches": strong,
        "top_threshold": TOP_SCORE_THRESHOLD,
        "saved_count": saved_repo.count(),
        "proposal_count": proposals_repo.count(),
        "distribution": distribution,
        "top_matches": [_row_brief(row) for row in top_rows],
        "top_matches_total": top_total,
        "sources": source_health(settings=settings),
        "by_source": [dict(row) for row in jobs_repo.source_breakdown()],
        "activity": activity.grouped(limit=8),
        "factor_labels": FACTOR_LABELS,
        "verdict_labels": VERDICT_LABELS,
        "health_ok": bool(total_jobs),
    }


def source_health(*, settings: Settings | None = None) -> list[dict]:
    """وضعیت هر منبع — از گزارش اجراهای واقعی، نه از فرض."""
    settings = settings or get_settings()
    latest = sources_repo.latest_per_source()
    breakdown = {row["source"]: row["jobs"] for row in jobs_repo.source_breakdown()}

    from ..sources import KINDS, LABELS

    out: list[dict] = []
    for key, label in LABELS.items():
        run = latest.get(key)
        enabled = (not settings.enabled_sources) or key in settings.enabled_sources
        out.append({
            "key": key,
            "label": label,
            "kind": KINDS.get(key, "rss"),
            "enabled": enabled,
            "has_run": run is not None,
            "ok": bool(run["ok"]) if run else False,
            "last_jobs": int(run["jobs"]) if run else 0,
            "error": (run["error"] if run else "") or "",
            "duration_ms": int(run["duration_ms"]) if run else 0,
            "last_run_ts": int(run["ts"]) if run else None,
            "last_success_ts": int(run["last_success_ts"]) if run and run["last_success_ts"] else None,
            "success_rate": sources_repo.success_rate(key),
            "stored_jobs": int(breakdown.get(key, 0)),
        })
    return out


def match_analysis(job_row, *, limit_related: int = 4) -> dict:
    """تحلیل کامل تطابق یک آگهی — آمادهٔ رندر در صفحهٔ جزئیات."""
    matched = _json_list(job_row["matched"]) if "matched" in job_row.keys() else []
    factors_raw = _json_list(job_row["factors"]) if "factors" in job_row.keys() else []
    reasons = _json_list(job_row["reasons"]) if "reasons" in job_row.keys() else []

    factors = []
    for item in factors_raw:
        if not isinstance(item, dict):
            continue
        factors.append({
            **item,
            "percent": int(round(float(item.get("ratio", 0)) * 100)),
        })

    missing = [k for k in _json_list(job_row["missing"]) if k] if "missing" in job_row.keys() else []
    from ..profile import SKILLS, fa_names, relevant_projects

    return {
        "score": job_row["total"] if "total" in job_row.keys() else -1,
        "verdict": job_row["verdict"] if "verdict" in job_row.keys() else "",
        "verdict_label": VERDICT_LABELS.get(
            job_row["verdict"] if "verdict" in job_row.keys() else "", "—"),
        "matched_keys": matched,
        "matched_skills": fa_names(sorted(matched, key=lambda k: -SKILLS[k].weight)
                                   if matched else [], 8),
        "missing_skills": fa_names(sorted([k for k in missing if k in SKILLS],
                                          key=lambda k: -SKILLS[k].weight), 6),
        "factors": factors,
        "reasons": reasons,
        "projects": [
            {"id": p.id, "title": p.title, "summary": p.summary,
             "stack": list(p.stack), "metric": p.metric}
            for p in relevant_projects(matched, limit=limit_related)
        ],
    }


def job_payload(row) -> dict:
    """تبدیل ردیف پایگاه داده به دیکشنری JSON-پذیر برای API."""
    tags = _json_list(row["tags"]) if "tags" in row.keys() else []
    return {
        "id": int(row["id"]),
        "source": row["source"],
        "title": row["title"],
        "company": row["company"] or "",
        "url": row["url"] or "",
        "location": row["location"] or "",
        "remote": bool(row["remote"]),
        "employment": row["employment"] or "",
        "salary": row["salary_text"] or "",
        "tags": tags,
        "published_ts": row["published_ts"],
        "first_seen_ts": row["first_seen_ts"],
        "seen_count": int(row["seen_count"] or 1),
        "score": int(row["total"]) if "total" in row.keys() and row["total"] is not None else None,
        "verdict": row["verdict"] if "verdict" in row.keys() else "",
        "saved": bool(row["is_saved"]) if "is_saved" in row.keys() else False,
        "has_proposal": bool(row["proposal_count"]) if "proposal_count" in row.keys() else False,
    }


def _row_brief(row) -> dict:
    data = job_payload(row)
    data["matched"] = _json_list(row["matched"])[:4] if "matched" in row.keys() else []
    from ..profile import fa_names

    data["matched_fa"] = fa_names(data["matched"], 4)
    return data


def _json_list(raw) -> list:
    try:
        value = json.loads(raw) if raw else []
    except (ValueError, TypeError):
        return []
    return value if isinstance(value, list) else []


def headline(overview_data: dict) -> str:
    """یک جملهٔ خلاصه برای بالای داشبورد."""
    total = overview_data["total_jobs"]
    if not total:
        return "هنوز آگهی‌ای ثبت نشده — یک دور جمع‌آوری اجرا کنید."
    strong = overview_data["strong_matches"]
    return (f"{fa_number(total)} آگهی در پایگاه داده · "
            f"{fa_number(overview_data['new_today'])} تازه در ۲۴ ساعت · "
            f"{fa_number(strong)} با تطابق قوی (امتیاز {fa_number(TOP_SCORE_THRESHOLD)}+)")


__all__ = ["overview", "source_health", "match_analysis", "job_payload", "headline"]
