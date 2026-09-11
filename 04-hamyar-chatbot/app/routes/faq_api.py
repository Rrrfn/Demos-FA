# -*- coding: utf-8 -*-
"""Knowledge-base API.

Endpoints
---------
GET    /api/faqs             list/search FAQs
POST   /api/faqs             create a FAQ                (admin token)
GET    /api/faqs/<id>        read one FAQ
PUT    /api/faqs/<id>        replace one FAQ             (admin token)
DELETE /api/faqs/<id>        delete one FAQ              (admin token)
GET    /api/categories       categories with counts
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.errors import ValidationError
from app.security import admin_protected, admin_required
from app.services import FaqService

bp = Blueprint("faq_api", __name__, url_prefix="/api")


def _json_body() -> dict:
    """Return the JSON body, rejecting non-object payloads."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValidationError("بدنهٔ درخواست باید یک آبجکت JSON باشد.")
    return payload


@bp.get("/faqs")
def list_faqs():
    """List knowledge-base entries with optional search and category filter."""
    page = FaqService.list(
        search=request.args.get("search") or None,
        category=request.args.get("category") or None,
        limit=request.args.get("limit", 200, type=int),
        offset=request.args.get("offset", 0, type=int),
    )
    return jsonify({"faqs": page["items"], **{k: page[k] for k in ("total", "limit", "offset")}})


@bp.post("/faqs")
@admin_required
def create_faq():
    """Create a FAQ and reindex the engine."""
    faq = FaqService.create(_json_body())
    return jsonify({"ok": True, "faq": faq.to_dict()}), 201


@bp.get("/faqs/<int:faq_id>")
def get_faq(faq_id: int):
    """Return one FAQ with its alternative phrasings."""
    return jsonify({"faq": FaqService.get(faq_id).to_dict()})


@bp.put("/faqs/<int:faq_id>")
@admin_required
def update_faq(faq_id: int):
    """Replace a FAQ's content and reindex the engine."""
    faq = FaqService.update(faq_id, _json_body())
    return jsonify({"ok": True, "faq": faq.to_dict()})


@bp.delete("/faqs/<int:faq_id>")
@admin_required
def delete_faq(faq_id: int):
    """Delete a FAQ and reindex the engine."""
    return jsonify(FaqService.delete(faq_id))


@bp.get("/categories")
def categories():
    """Return every category with its FAQ count."""
    return jsonify(
        {
            "categories": FaqService.categories(),
            "admin_protected": admin_protected(),
        }
    )
