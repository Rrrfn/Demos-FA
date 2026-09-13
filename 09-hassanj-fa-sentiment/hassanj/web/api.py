# -*- coding: utf-8 -*-
"""API JSON — با پوشش پاسخ یکدست.

هر پاسخ یا ``{"ok": true, "data": …}`` است یا ``{"ok": false, "error": …}``.
یکدست بودن پوشش یعنی مصرف‌کننده لازم نیست برای هر مسیر شکل پاسخ را جدا حدس
بزند، و خطا هرگز به HTML تبدیل نمی‌شود.

کدهای لاتین برچسب (``pos`` / ``neu`` / ``neg``) در API می‌مانند تا ماشین‌خوان
باشد؛ نگاشت فارسی فقط در رابط کاربری انجام می‌شود.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from .. import services
from ..config import LABELS, MAX_ANALYZE_CHARS
from ..labels import sentiment_label, to_persian_digits
from ..web.context import DATA_NOTE

api = Blueprint("api", __name__, url_prefix="/api")


def ok(data: dict):
    return jsonify({"ok": True, "data": data})


def fail(message: str, status: int = 400):
    return jsonify({"ok": False, "error": message}), status


@api.get("/health")
def health():
    data = services.metrics()
    return ok({
        "status": "ok",
        "best_model": data["best_model"],
        "n_samples": data["n_samples"],
        "labels": list(LABELS),
        "data_note": DATA_NOTE,
    })


@api.post("/analyze")
def analyze():
    #: بدنهٔ JSON می‌تواند هر چیزی باشد — آرایه، عدد، رشته. اگر نوعش بررسی نشود،
    #: ``payload.get`` استثنا می‌دهد و درخواست نامعتبر به خطای ۵۰۰ تبدیل می‌شود.
    #: ورودی بد، خطای *کاربر* است، نه خطای سرور.
    payload = request.get_json(silent=True)
    if payload is not None and not isinstance(payload, dict):
        return fail("بدنهٔ درخواست باید یک شیء JSON باشد.")
    payload = payload or {}
    text = payload.get("text")
    if text is None:
        text = request.form.get("text", "")
    if not isinstance(text, str):
        return fail("مقدار «text» باید رشته باشد.")
    if not text.strip():
        return fail("متن خالی است.")

    result = services.analyse_text(text)
    return ok({
        "label": result["label"],
        "label_fa": sentiment_label(result["label"]),
        "confidence": result["confidence"],
        "band": result["band"],
        "proba": result["proba"],
        "state": result["state"],
        "coverage": result["coverage"],
        "tokens": result["token_count"],
        "known_tokens": result["known_tokens"][:20],
        "unknown_tokens": result["unknown_tokens"][:20],
        "toward": [item["term"] for item in result["toward"]],
        "against": [item["term"] for item in result["against"]],
        "truncated": result["truncated"],
        "max_chars": MAX_ANALYZE_CHARS,
    })


@api.get("/metrics")
def metrics():
    data = services.metrics()
    return ok({
        "best_model": data["best_model"],
        "n_samples": data["n_samples"],
        "vocabulary_size": data["vocabulary_size"],
        "in_domain": data["in_domain"],
        "out_domain": data["out_domain"],
        "cv": data.get("cv", {}),
        "results": data["results"],
        "trained_at": data["trained_at"],
    })


@api.get("/mix")
def mix():
    data = services.mix()
    return ok({
        "actual": data["actual"],
        "predicted": data["predicted"],
        "comparison": data["comparison"],
    })


@api.get("/terms")
def terms():
    code = request.args.get("label", "pos")
    if code not in LABELS:
        return fail(f"برچسب نامعتبر است؛ یکی از {list(LABELS)} را بفرستید.")
    return ok({"label": code, "terms": services.class_terms().get(code, [])})


@api.get("/trend")
def trend():
    rows = services.monthly()
    return ok({"months": [{
        "index": row["month"],
        "label": to_persian_digits(row["month"]),
        "counts": row["counts"],
        "shares": row["shares"],
        "total": row["total"],
    } for row in rows]})


@api.get("/model-status")
def model_status():
    """وضعیت فایل مدل — همان چیزی که صفحهٔ دپلوی به آن نگاه می‌کند."""
    import os

    from ..config import model_path

    path = model_path()
    exists = os.path.exists(path)
    return ok({
        "trained": exists,
        "bytes": os.path.getsize(path) if exists else 0,
        "best_model": services.metrics()["best_model"],
    })
