# -*- coding: utf-8 -*-
"""Chat service — the use case behind POST /api/chat and the widget.

Responsibilities: validate the incoming message, ask the engine, persist the
turn, and expose session history, feedback and human handoff.
"""
from __future__ import annotations

import re
from typing import Any

from flask import current_app

from app.database import ConversationRepository, HandoffRepository, session
from app.errors import NotFoundError, ValidationError
from app.models import ChatReply, ConversationTurn, HandoffRequest

from .knowledge_service import get_engine

SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{6,64}$")
FEEDBACK_VALUES = {"up", "down"}


class ChatService:
    """Application service for visitor conversations."""

    # ------------------------------------------------------------ validation
    @staticmethod
    def normalize_message(raw: Any) -> str:
        """Validate and trim an incoming message, raising ValidationError."""
        if raw is None:
            raise ValidationError("متن پیام ارسال نشده است.", {"field": "message"})
        if not isinstance(raw, str):
            raise ValidationError("متن پیام باید رشته باشد.", {"field": "message"})
        message = " ".join(raw.split())
        if not message:
            raise ValidationError("پیام شما خالی است.", {"field": "message"})
        limit = int(current_app.config["MAX_MESSAGE_LENGTH"])
        if len(message) > limit:
            raise ValidationError(
                f"متن پیام بیش از حد مجاز است (حداکثر {limit} نویسه).",
                {"field": "message", "max_length": limit},
            )
        return message

    @staticmethod
    def normalize_session_id(raw: Any) -> str:
        """Validate a session identifier, generating no implicit state."""
        candidate = str(raw or "").strip()
        if not candidate:
            raise ValidationError("شناسه گفتگو لازم است.", {"field": "session_id"})
        if not SESSION_ID_PATTERN.match(candidate):
            raise ValidationError(
                "شناسه گفتگو معتبر نیست.",
                {"field": "session_id", "pattern": SESSION_ID_PATTERN.pattern},
            )
        return candidate

    # ------------------------------------------------------------------ use cases
    @classmethod
    def ask(cls, raw_message: Any, raw_session_id: Any) -> ChatReply:
        """Answer a message and record the turn."""
        message = cls.normalize_message(raw_message)
        session_id = cls.normalize_session_id(raw_session_id)

        reply = get_engine().reply(message)

        with session() as conn:
            conversation_id = ConversationRepository(conn).log(
                session_id=session_id,
                user_text=message,
                matched_faq_id=reply.faq_id,
                matched_text=reply.matched_question,
                score=reply.score,
                confidence=reply.confidence.value,
                answered=reply.matched,
                category=reply.category,
                latency_ms=reply.latency_ms,
            )

        reply.conversation_id = conversation_id
        return reply

    @staticmethod
    def history(raw_session_id: Any, limit: int = 100) -> list[ConversationTurn]:
        """Return the transcript of one session, oldest first."""
        session_id = ChatService.normalize_session_id(raw_session_id)
        with session() as conn:
            return ConversationRepository(conn).by_session(session_id, limit=limit)

    @staticmethod
    def submit_feedback(conversation_id: int, value: str | None) -> dict[str, Any]:
        """Store a thumbs up/down rating for one answer."""
        if value not in FEEDBACK_VALUES and value is not None:
            raise ValidationError(
                "مقدار بازخورد باید up یا down باشد.", {"field": "feedback"}
            )
        with session() as conn:
            repository = ConversationRepository(conn)
            if repository.get(conversation_id) is None:
                raise NotFoundError("این پیام در تاریخچه پیدا نشد.")
            repository.set_feedback(conversation_id, value)
        return {"conversation_id": conversation_id, "feedback": value}

    @staticmethod
    def request_handoff(
        raw_session_id: Any, reason: Any = None, last_query: Any = None
    ) -> HandoffRequest:
        """Create a human-agent handoff ticket."""
        session_id = ChatService.normalize_session_id(raw_session_id)
        with session() as conn:
            repository = HandoffRepository(conn)
            ticket_id = repository.create(
                session_id=session_id,
                reason=str(reason or "")[:200],
                last_query=str(last_query or "")[:500],
            )
            request = [r for r in repository.list(limit=1) if r.id == ticket_id]
        if not request:  # pragma: no cover - defensive
            raise NotFoundError("ثبت درخواست ناموفق بود.")
        return request[0]
