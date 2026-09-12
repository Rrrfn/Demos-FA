# -*- coding: utf-8 -*-
"""API نسخه‌دار — قالب پاسخ یکدست و اعتبارسنجی کامل.

هر پاسخ یکی از دو شکل زیر است تا کلاینت هیچ‌وقت حدس نزند::

    {"ok": true,  "data": ..., "meta": {...}}
    {"ok": false, "error": {"code": "...", "message": "...", "detail": "..."}}

مسیرها زیر ``/api/v1`` هستند تا تغییرات آینده نسخهٔ قدیم را نشکند. ``/health``
عامداً بیرون از این پیشوند و بدون پوشش است، چون سامانهٔ پایش میزبان
(Render) شکل ثابتی از آن انتظار دارد.
"""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from ..core.errors import NotFoundError, UnauthorizedError, ValidationError
from ..core.text import fa_number
from ..services import analytics
from ..services.ingest import known_sources, rescore_job, run_ingest
from ..services.proposals import generate as generate_proposal
from ..storage import activity, jobs as jobs_repo, proposals as proposals_repo
from ..storage import saved as saved_repo, sources as sources_repo

bp = Blueprint("api", __name__, url_prefix="/api/v1")

PER_PAGE_MAX = 100


def ok(data, **meta):
    payload = {"ok": True, "data": data}
    payload["meta"] = {"count": len(data)} if isinstance(data, list) else {}
    payload["meta"].update(meta)
    return jsonify(payload)


def fail(code: str, message: str, status: int, detail: str = ""):
    body = {"ok": False, "error": {"code": code, "message": message}}
    if detail:
        body["error"]["detail"] = detail
    return jsonify(body), status


def _settings():
    return current_app.config.get("KARINO_SETTINGS")


def _int_arg(name: str, default: int, low: int, high: int) -> int:
    raw = request.args.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValidationError(f"پارامتر «{name}» باید عدد صحیح باشد.",
                              detail=f"{name}={raw}") from None
    if not low <= value <= high:
        raise ValidationError(
            f"پارامتر «{name}» باید بین {fa_number(low)} و {fa_number(high)} باشد.",
            detail=f"{name}={raw}")
    return value


def _bool_arg(name: str) -> bool | None:
    raw = request.args.get(name)
    if raw is None or raw == "":
        return None
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValidationError(f"پارامتر «{name}» باید بله/خیر باشد.", detail=f"{name}={raw}")


def _require_admin():
    """محافظت اختیاری endpointهای تغییر وضعیت.

    اگر توکنی تنظیم نشده باشد، مسیر باز است — عمداً، تا دموی عمومی با یک
    کلیک کار کند. به‌محض تنظیم ``KARINO_ADMIN_TOKEN``، همهٔ مسیرهای نوشتن
    هدر ``X-Admin-Token`` می‌خواهند.
    """
    token = _settings().admin_token
    if not token:
        return
    provided = request.headers.get("X-Admin-Token") or request.args.get("token") or ""
    if provided != token:
        raise UnauthorizedError("توکن مدیریت نامعتبر است.")


# ---------------------------------------------------------------- سلامت


@bp.get("/health")
def health():
    """سلامت سمت API — با همان پوشش بقیهٔ مسیرهای نسخه‌دار.

    ``/health`` بدون پیشوند و بدون پوشش، برای سامانهٔ پایش میزبان است؛ این
    یکی قرارداد عمومی API را رعایت می‌کند تا کلاینت برای خواندن آن مجبور
    نباشد شکل پاسخ را حدس بزند.
    """
    return ok({
        "status": "ok",
        "service": "karino-ai-agent",
        "version": current_app.config.get("KARINO_VERSION", "1.0"),
        "env": _settings().env,
    })


# ---------------------------------------------------------------- نمای کلی


@bp.get("/overview")
def overview():
    return ok(analytics.overview(settings=_settings()))


@bp.get("/profile")
def profile():
    from ..profile import CATEGORIES, PORTFOLIO, SKILLS, TOTAL_WEIGHT

    return ok({
        "total_weight": TOTAL_WEIGHT,
        "skills": [
            {"key": s.key, "label": s.fa, "weight": s.weight,
             "category": s.category, "category_label": CATEGORIES.get(s.category, s.category)}
            for s in sorted(SKILLS.values(), key=lambda s: -s.weight)
        ],
        "portfolio": [
            {"id": p.id, "title": p.title, "summary": p.summary,
             "stack": list(p.stack), "skills": list(p.skills), "metric": p.metric}
            for p in PORTFOLIO
        ],
    })


# ---------------------------------------------------------------- آگهی‌ها


@bp.get("/jobs")
def list_jobs():
    page = _int_arg("page", 1, 1, 1000)
    per_page = _int_arg("per_page", 20, 1, PER_PAGE_MAX)
    min_score = _int_arg("min", 0, 0, 100)
    max_score = _int_arg("max", 100, 0, 100)
    if min_score > max_score:
        raise ValidationError("کمینهٔ امتیاز نمی‌تواند از بیشینهٔ آن بزرگ‌تر باشد.")

    source = (request.args.get("source") or "").strip()
    if source and source not in {s["key"] for s in known_sources()} and source != "seed":
        raise ValidationError("منبع درخواستی شناخته‌شده نیست.",
                              detail=f"source={source}")

    sort = (request.args.get("sort") or "score")
    if sort not in jobs_repo.SORT_OPTIONS:
        raise ValidationError("ترتیب درخواستی پشتیبانی نمی‌شود.",
                              detail=f"sort={sort}")

    rows, total = jobs_repo.query(
        q=(request.args.get("q") or "").strip()[:120], min_score=min_score,
        max_score=max_score, source=source, remote=_bool_arg("remote"),
        saved_only=bool(_bool_arg("saved")), sort=sort, page=page,
        per_page=per_page)

    items = [analytics.job_payload(row) for row in rows]
    page_count = max(1, (total + per_page - 1) // per_page)

    return jsonify({
        "ok": True,
        "data": items,
        "meta": {
            "count": len(items), "total": total, "page": page,
            "per_page": per_page, "page_count": page_count,
            "has_next": page < page_count, "has_prev": page > 1,
        },
    })


@bp.get("/jobs/<int:job_id>")
def get_job(job_id: int):
    row = jobs_repo.get(job_id)
    if not row:
        raise NotFoundError("آگهی مورد نظر پیدا نشد.")
    data = analytics.job_payload(row)
    data["description"] = row["description"] or ""
    data["match"] = analytics.match_analysis(row)
    return ok(data)


@bp.get("/jobs/<int:job_id>/match")
def job_match(job_id: int):
    row = jobs_repo.get(job_id)
    if not row:
        raise NotFoundError("آگهی مورد نظر پیدا نشد.")
    return ok(analytics.match_analysis(row))


@bp.post("/jobs/<int:job_id>/rescore")
def job_rescore(job_id: int):
    _require_admin()
    if not jobs_repo.get(job_id):
        raise NotFoundError("آگهی مورد نظر پیدا نشد.")
    rescore_job(job_id)
    row = jobs_repo.get(job_id)
    return ok(analytics.match_analysis(row))


# ---------------------------------------------------------------- پیشنهاد


@bp.get("/jobs/<int:job_id>/proposal")
def get_proposal(job_id: int):
    if not jobs_repo.get(job_id):
        raise NotFoundError("آگهی مورد نظر پیدا نشد.")
    tone = _tone_arg()
    variant = _variant_arg()
    saved = proposals_repo.get(job_id, tone=tone, variant=variant)
    if not saved:
        return ok({"job_id": job_id, "tone": tone, "variant": variant,
                   "body": None, "exists": False})
    return ok({"job_id": job_id, "tone": tone, "variant": variant,
               "body": saved["body"], "writer": saved["writer"],
               "created_ts": saved["created_ts"], "exists": True})


@bp.post("/jobs/<int:job_id>/proposal")
def create_proposal(job_id: int):
    """ساخت پیشنهاد — با کلید ``force`` می‌توان کش را نادیده گرفت."""
    _require_admin()
    data = request.get_json(silent=True) or {}
    tone = (data.get("tone") or request.args.get("tone") or "formal").strip()
    variant = (data.get("variant") or request.args.get("variant") or "standard").strip()
    if tone not in ("formal", "concise", "consultative"):
        raise ValidationError("لحن درخواستی پشتیبانی نمی‌شود.", detail=f"tone={tone}")
    if variant not in ("standard", "short"):
        raise ValidationError("طول درخواستی پشتیبانی نمی‌شود.", detail=f"variant={variant}")

    payload = generate_proposal(job_id, tone=tone, variant=variant,
                                force=bool(data.get("force")))
    return ok(payload)


def _tone_arg() -> str:
    tone = (request.args.get("tone") or "formal").strip()
    if tone not in ("formal", "concise", "consultative"):
        raise ValidationError("لحن درخواستی پشتیبانی نمی‌شود.", detail=f"tone={tone}")
    return tone


def _variant_arg() -> str:
    variant = (request.args.get("variant") or "standard").strip()
    if variant not in ("standard", "short"):
        raise ValidationError("طول درخواستی پشتیبانی نمی‌شود.", detail=f"variant={variant}")
    return variant


# ---------------------------------------------------------------- ذخیره‌شده


@bp.get("/saved")
def list_saved():
    rows, total = jobs_repo.query(saved_only=True, sort="score",
                                  per_page=_int_arg("per_page", 50, 1, PER_PAGE_MAX))
    return jsonify({"ok": True, "data": [analytics.job_payload(r) for r in rows],
                    "meta": {"count": len(rows), "total": total, "saved_total": saved_repo.count()}})


@bp.post("/jobs/<int:job_id>/save")
def save_job(job_id: int):
    _require_admin()
    if not jobs_repo.get(job_id):
        raise NotFoundError("آگهی مورد نظر پیدا نشد.")
    created = saved_repo.add(job_id)
    if created:
        activity.log("job_saved", "آگهی به فهرست ذخیره‌شده افزوده شد",
                     meta={"job_id": job_id})
    return ok({"job_id": job_id, "saved": True, "created": created})


@bp.delete("/jobs/<int:job_id>/save")
def unsave_job(job_id: int):
    _require_admin()
    if not jobs_repo.get(job_id):
        raise NotFoundError("آگهی مورد نظر پیدا نشد.")
    removed = saved_repo.remove(job_id)
    if removed:
        activity.log("job_unsaved", "آگهی از فهرست ذخیره‌شده برداشته شد",
                     meta={"job_id": job_id})
    return ok({"job_id": job_id, "saved": False, "removed": removed})


# ---------------------------------------------------------------- منابع و فعالیت


@bp.get("/sources")
def list_sources():
    health = analytics.source_health(settings=_settings())
    for item in health:
        item["success_rate"] = sources_repo.success_rate(item["key"])
    return ok(health)


@bp.get("/activity")
def list_activity():
    limit = _int_arg("limit", 30, 1, 200)
    level = (request.args.get("level") or "").strip()
    if level and level not in activity.LEVELS:
        raise ValidationError("سطح درخواستی شناخته‌شده نیست.", detail=f"level={level}")
    return ok(activity.grouped(limit=limit) if not level
              else [dict(r) for r in activity.recent(limit, level=level)],
              counts=activity.count_by_level())


# ---------------------------------------------------------------- جمع‌آوری


@bp.post("/ingest")
def ingest():
    """اجرای یک دور جمع‌آوری. ورودی اختیاری ``sources`` فهرست کلید منابع است."""
    _require_admin()
    data = request.get_json(silent=True) or {}
    requested = data.get("sources")
    settings = _settings()

    if requested is not None:
        if not isinstance(requested, list) or not requested:
            raise ValidationError("فهرست منابع باید یک آرایهٔ ناتهی باشد.")
        from ..sources import ALL_KEYS

        unknown = [k for k in requested if k not in ALL_KEYS]
        if unknown:
            raise ValidationError("کلید منبع ناشناخته در فهرست درخواست.",
                                  detail=f"unknown={unknown}")
        settings = _with_sources(settings, list(requested))

    stats = run_ingest(settings=settings)
    return ok(stats)


def _with_sources(settings, keys: list[str]):
    """کپی تنظیمات با فهرست منابع دلخواه — ``Settings`` بی‌تغییر است."""
    from dataclasses import replace

    return replace(settings, enabled_sources=keys)
