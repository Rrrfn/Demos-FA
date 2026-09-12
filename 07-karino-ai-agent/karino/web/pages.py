# -*- coding: utf-8 -*-
"""صفحات داشبورد — رندر سمت سرور با دادهٔ کامل.

هر صفحه داده‌اش را از لایهٔ سرویس می‌گیرد؛ قالب هیچ عددی را خودش حساب
نمی‌کند. مزیتش این است که صفحهٔ اول درخواست، بدون هیچ فراخوانی AJAX،
کاملاً پر رندر می‌شود و اگر جاوااسکریپت هم اجرا نشود، داشبورد کار می‌کند.
"""
from __future__ import annotations

import json

from flask import Blueprint, abort, current_app, redirect, render_template, request, url_for

from ..core.errors import NotFoundError, ValidationError
from ..core.text import fa_number
from ..pipeline.proposal import DEFAULT_TONE, TONES
from ..pipeline.scoring import BUDGETS, FACTOR_LABELS, verdict_label
from ..profile import PORTFOLIO, SKILLS, TOTAL_WEIGHT, match_skills
from ..services import analytics
from ..storage import activity, jobs as jobs_repo, proposals as proposals_repo
from ..storage import saved as saved_repo

bp = Blueprint("pages", __name__)

SORT_LABELS = {
    "score": "امتیاز تطابق",
    "published": "تازه‌ترین انتشار",
    "recent": "تازه‌ترین کشف",
    "oldest": "قدیمی‌ترین",
    "company": "نام کارفرما",
}

SCORE_PRESETS = (
    ("all", 0, "همه"),
    ("strong", 72, "قوی (۷۲+)"),
    ("excellent", 85, "عالی (۸۵+)"),
    ("moderate", 55, "متوسط (۵۵+)"),
)


def _settings():
    return current_app.config.get("KARINO_SETTINGS")


def _page_args() -> dict:
    """پارامترهای مشترک فهرست‌ها، با اعتبارسنجی و کران‌گذاری."""
    def _int(name: str, default: int, low: int, high: int) -> int:
        try:
            value = int(request.args.get(name, default))
        except (TypeError, ValueError):
            raise ValidationError(f"مقدار «{name}» باید عدد باشد.") from None
        if not low <= value <= high:
            raise ValidationError(f"مقدار «{name}» باید بین {fa_number(low)} و {fa_number(high)} باشد.")
        return value

    remote_raw = (request.args.get("remote") or "").lower()
    remote = True if remote_raw in {"1", "true", "yes"} else (
        False if remote_raw in {"0", "false", "no"} else None)

    return {
        "q": (request.args.get("q") or "").strip()[:120],
        "min_score": _int("min", 0, 0, 100),
        "source": (request.args.get("source") or "").strip()[:40],
        "remote": remote,
        "sort": (request.args.get("sort") or "score") if request.args.get("sort") in SORT_LABELS else "score",
        "page": _int("page", 1, 1, 500),
        "per_page": _int("per_page", 20, 5, 60),
    }


@bp.route("/")
def overview():
    data = analytics.overview(settings=_settings())
    return render_template(
        "overview.html",
        active="overview",
        data=data,
        headline=analytics.headline(data),
        max_bucket=max(list(data["distribution"].values()) + [1]),
        factor_labels=FACTOR_LABELS,
        verdict_label=verdict_label,
    )


@bp.route("/jobs")
def jobs():
    args = _page_args()
    rows, total = jobs_repo.query(
        q=args["q"], min_score=args["min_score"], source=args["source"],
        remote=args["remote"], sort=args["sort"], page=args["page"],
        per_page=args["per_page"])
    items = [analytics.job_payload(row) for row in rows]
    for item, row in zip(items, rows):
        item["factors"] = analytics._json_list(row["factors"])
        item["reasons"] = analytics._json_list(row["reasons"])[:3]

    return render_template(
        "jobs.html",
        active="jobs",
        jobs=items,
        total=total,
        args=args,
        page_count=max(1, (total + args["per_page"] - 1) // args["per_page"]),
        sort_labels=SORT_LABELS,
        presets=SCORE_PRESETS,
        source_labels=analytics.source_health(settings=_settings()),
        query_string=_query_string(args),
        verdict_label=verdict_label,
    )


@bp.route("/jobs/<int:job_id>")
def job_detail(job_id: int):
    row = jobs_repo.get(job_id)
    if not row:
        raise NotFoundError("آگهی مورد نظر پیدا نشد.")
    analysis = analytics.match_analysis(row)
    job = analytics.job_payload(row)
    try:
        tags = json.loads(row["tags"] or "[]")
    except (ValueError, TypeError):
        tags = []
    job["description"] = row["description"] or ""
    job["tags"] = tags if isinstance(tags, list) else []

    return render_template(
        "job_detail.html",
        active="jobs",
        job=job,
        analysis=analysis,
        budgets=BUDGETS,
        factor_labels=FACTOR_LABELS,
        proposals=proposals_repo.list_for_job(job_id),
        tones=TONES,
        default_tone=DEFAULT_TONE,
        score_presets=SCORE_PRESETS,
    )


@bp.route("/saved")
def saved():
    rows, total = jobs_repo.query(saved_only=True, sort="score", per_page=60)
    items = [analytics.job_payload(row) for row in rows]
    return render_template("saved.html", active="saved", jobs=items, total=total,
                           verdict_label=verdict_label)


@bp.route("/sources")
def sources():
    health = analytics.source_health(settings=_settings())
    history = {item["key"]: [dict(r) for r in _source_history(item["key"])] for item in health}
    return render_template("sources.html", active="sources", sources=health,
                           history=history,
                           errors=[dict(r) for r in activity.recent(limit=30)
                                   if r["level"] in ("warning", "error")])


def _source_history(key: str):
    from ..storage import sources as sources_repo

    return sources_repo.history(key, limit=12)


@bp.route("/activity")
def activity_page():
    events = activity.grouped(limit=80)
    return render_template("activity.html", active="activity", events=events,
                           counts=activity.count_by_level())


@bp.route("/proposal")
def proposal_page():
    """کارگاه پیشنهاد — انتخاب آگهی، لحن و طول، و ساخت متن."""
    rows, total = jobs_repo.query(min_score=0, sort="score", per_page=40)
    items = [analytics.job_payload(row) for row in rows]

    selected = None
    selected_id = request.args.get("job", type=int)
    if selected_id:
        row = jobs_repo.get(selected_id)
        if row:
            selected = analytics.job_payload(row)

    tone = request.args.get("tone") or DEFAULT_TONE
    return render_template(
        "proposal.html",
        active="proposal",
        jobs=items,
        total=total,
        selected=selected,
        tones=TONES,
        tone=tone if tone in TONES else DEFAULT_TONE,
        recent_proposals=[dict(r) for r in proposals_repo.recent(6)],
    )


@bp.route("/profile")
def profile_page():
    """صفحهٔ پروفایل — مهارت‌های وزنی و سبد نمونه‌کار."""
    grouped: dict[str, list] = {}
    from ..profile import CATEGORIES

    for spec in SKILLS.values():
        grouped.setdefault(spec.category, []).append(spec)

    order = sorted(grouped.items(),
                   key=lambda pair: -max(s.weight for s in pair[1]))
    return render_template(
        "profile.html",
        active="profile",
        categories=[(CATEGORIES.get(key, key), specs) for key, specs in order],
        portfolio=PORTFOLIO,
        total_weight=TOTAL_WEIGHT,
        prefs=_prefs_view(),
    )


def _prefs_view() -> dict:
    """ترجیحات پروفایل به‌شکل قابل‌نمایش در قالب."""
    from ..core.models import ENGAGEMENT_LABELS, SENIORITY_LABELS
    from ..profile import PREFS, TOP_SCORE_THRESHOLD

    return {
        "seniority": SENIORITY_LABELS.get(PREFS.target_seniority, PREFS.target_seniority),
        "preferred": [ENGAGEMENT_LABELS.get(k, k) for k in PREFS.preferred_engagement],
        "disliked": [ENGAGEMENT_LABELS.get(k, k) for k in PREFS.disliked_engagement],
        "remote": PREFS.prefers_remote,
        "locations": list(PREFS.preferred_locations),
        "top_threshold": TOP_SCORE_THRESHOLD,
    }


@bp.route("/jobs/<int:job_id>/proposal", methods=["POST"])
def generate_proposal(job_id: int):
    """ساخت پیشنهاد از فرم صفحهٔ جزئیات، سپس بازگشت به همان صفحه."""
    from ..services.proposals import generate

    tone = request.form.get("tone") or DEFAULT_TONE
    variant = request.form.get("variant") or "standard"
    try:
        generate(job_id, tone=tone, variant=variant)
    except NotFoundError:
        abort(404)
    return redirect(url_for("pages.job_detail", job_id=job_id) + f"#proposal-{tone}-{variant}")


@bp.route("/saved/<int:job_id>/toggle", methods=["POST"])
def toggle_saved(job_id: int):
    if not jobs_repo.get(job_id):
        raise NotFoundError("آگهی مورد نظر پیدا نشد.")
    saved_repo.toggle(job_id)
    return redirect(request.form.get("next") or url_for("pages.saved"))


@bp.route("/jobs/<int:job_id>/rescore", methods=["POST"])
def rescore(job_id: int):
    """امتیازدهی دوباره با پروفایل فعلی — بعد از تغییر وزن‌ها مفید است."""
    from ..services.ingest import rescore_job

    if not jobs_repo.get(job_id):
        raise NotFoundError("آگهی مورد نظر پیدا نشد.")
    rescore_job(job_id)
    return redirect(url_for("pages.job_detail", job_id=job_id))


@bp.route("/collect", methods=["POST"])
def collect():
    """اجرای یک دور جمع‌آوری از رابط، سپس بازگشت به فهرست."""
    from ..services.ingest import run_ingest

    run_ingest(settings=_settings())
    return redirect(request.form.get("next") or url_for("pages.jobs"))


def _query_string(args: dict) -> str:
    """پارامترهای فیلتر به‌شکل رشته، برای حفظ فیلترها در لینک صفحه‌بندی."""
    from urllib.parse import urlencode

    clean = {k: v for k, v in args.items()
             if v not in (None, "", 0) and not (k == "page")}
    if args.get("remote") is False:
        clean["remote"] = "0"
    clean["sort"] = args.get("sort", "score")
    return urlencode(clean)
