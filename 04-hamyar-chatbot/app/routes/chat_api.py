# -*- coding: utf-8 -*-
"""Conversation API.

Endpoints
---------
POST /api/chat          answer a message and log the turn
GET  /api/history       transcript of one session
POST /api/feedback      rate a logged answer
POST /api/handoff       request a human agent (returns a ticket number)
GET  /api/suggestions   type-ahead over the knowledge base
"""
from __future__ import annotations

import secrets

from flask import Blueprint, jsonify, request

from app.errors import ValidationError
from app.services import ChatService, get_engine

bp = Blueprint("chat_api", __name__, url_prefix="/api")


def _json_body() -> dict:
    """Return the JSON body, rejecting non-object payloads."""
    payload = request.get_json(silent=True)
    if payload is None:
        raise ValidationError("بدنهٔ درخواست باید JSON باشد.")
    if not isinstance(payload, dict):
        raise ValidationError("بدنهٔ درخواست باید یک آبجکت JSON باشد.")
    return payload


@bp.post("/chat")
def chat():
    """Answer a visitor message.

    Request body::

        {"message": "هزینه ارسال چقدر است؟", "session_id": "web-abc123"}

    ``session_id`` is optional; when omitted the server generates one and
    returns it so the client can keep the conversation thread.
    """
    body = _json_body()
    session_id = str(body.get("session_id") or "").strip()
    generated = False
    if not session_id:
        session_id = "web-" + secrets.token_urlsafe(9)
        generated = True

    reply = ChatService.ask(body.get("message"), session_id)
    payload = reply.to_dict()
    payload["session_id"] = session_id
    payload["session_generated"] = generated
    return jsonify(payload), 200


@bp.get("/history")
def history():
    """Return the transcript of a session, oldest first."""
    session_id = request.args.get("session_id")
    limit = request.args.get("limit", 100, type=int)
    turns = ChatService.history(session_id, limit=max(1, min(limit, 200)))
    return jsonify(
        {
            "session_id": session_id,
            "count": len(turns),
            "turns": [turn.to_dict() for turn in turns],
        }
    )


@bp.post("/feedback")
def feedback():
    """Rate one answer: ``{"conversation_id": 12, "feedback": "up"}``."""
    body = _json_body()
    conversation_id = body.get("conversation_id")
    if not isinstance(conversation_id, int):
        raise ValidationError("شناسهٔ پیام نامعتبر است.", {"field": "conversation_id"})
    result = ChatService.submit_feedback(conversation_id, body.get("feedback"))
    return jsonify({"ok": True, **result})


@bp.post("/handoff")
def handoff():
    """Request a human agent and return the ticket number."""
    body = _json_body()
    request_obj = ChatService.request_handoff(
        body.get("session_id"), body.get("reason"), body.get("last_query")
    )
    payload = request_obj.to_dict()
    return jsonify(
        {
            "ok": True,
            **payload,
            "message": f"درخواست شما با شماره {payload['ticket']} ثبت شد. "
            "کارشناس پشتیبانی به‌زودی گفتگو را ادامه می‌دهد.",
        }
    ), 201


@bp.get("/suggestions")
def suggestions():
    """Type-ahead suggestions for the composer."""
    query = request.args.get("q", "")
    limit = max(1, min(request.args.get("limit", 6, type=int), 12))
    return jsonify({"query": query, "suggestions": get_engine().suggest(query, limit)})
