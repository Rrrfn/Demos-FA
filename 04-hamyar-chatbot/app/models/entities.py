# -*- coding: utf-8 -*-
"""Domain entities shared across the application.

These are plain dataclasses: the storage layer returns them, the service layer
consumes them and the API layer serialises them. No ORM, no framework types.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Confidence(str, Enum):
    """Retrieval confidence band attached to every reply."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    @property
    def label(self) -> str:
        """Persian label used by the UI."""
        return {
            "high": "اطمینان بالا",
            "medium": "اطمینان متوسط",
            "low": "اطمینان پایین",
        }[self.value]


class FallbackReason(str, Enum):
    """Why a reply did not come straight from the knowledge base."""

    EMPTY = "empty_message"
    TOO_LONG = "message_too_long"
    LOW = "low_confidence"
    MEDIUM = "medium_confidence"
    OUT_OF_DOMAIN = "out_of_domain"
    NO_KNOWLEDGE = "empty_knowledge_base"


@dataclass(frozen=True, slots=True)
class Faq:
    """A knowledge-base entry with its alternative phrasings."""

    id: int
    question: str
    answer: str
    category: str
    variants: tuple[str, ...] = ()
    created_at: str | None = None
    updated_at: str | None = None

    def to_dict(self, with_variants: bool = True) -> dict[str, Any]:
        """Serialise for the API."""
        data: dict[str, Any] = {
            "id": self.id,
            "question": self.question,
            "answer": self.answer,
            "category": self.category,
        }
        if with_variants:
            data["variants"] = list(self.variants)
        return data


@dataclass(frozen=True, slots=True)
class KbEntry:
    """One indexable unit: a primary question or one of its variants."""

    faq_id: int
    text: str
    is_primary: bool = False


@dataclass(slots=True)
class Candidate:
    """A scored retrieval hit."""

    faq_id: int
    text: str
    score: float
    word_score: float = 0.0
    char_score: float = 0.0
    is_primary: bool = False
    category: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialise a suggestion for the API."""
        return {
            "faq_id": self.faq_id,
            "question": self.text,
            "score": round(self.score, 3),
            "category": self.category,
        }


@dataclass(slots=True)
class ChatReply:
    """The complete outcome of one chat turn."""

    answer: str
    matched: bool
    confidence: Confidence
    score: float
    faq_id: int | None = None
    category: str | None = None
    matched_question: str | None = None
    suggestions: list[Candidate] = field(default_factory=list)
    fallback_reason: FallbackReason | None = None
    latency_ms: int = 0
    conversation_id: int | None = None
    handoff_available: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serialise for the JSON API."""
        return {
            "answer": self.answer,
            "matched": self.matched,
            "confidence": self.confidence.value,
            "confidence_label": self.confidence.label,
            "score": round(self.score, 3),
            "relevance": round(self.score * 100),
            "faq_id": self.faq_id,
            "category": self.category,
            "matched_question": self.matched_question,
            "suggestions": [c.to_dict() for c in self.suggestions],
            "fallback_reason": self.fallback_reason.value if self.fallback_reason else None,
            "latency_ms": self.latency_ms,
            "conversation_id": self.conversation_id,
            "handoff_available": self.handoff_available,
        }


@dataclass(frozen=True, slots=True)
class ConversationTurn:
    """A logged chat turn, used by the admin conversation log."""

    id: int
    session_id: str
    user_text: str
    matched_faq_id: int | None
    matched_text: str | None
    score: float
    confidence: str
    answered: bool
    category: str | None
    feedback: str | None
    latency_ms: int | None
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        """Serialise for the API and templates."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "message": self.user_text,
            "matched_faq_id": self.matched_faq_id,
            "matched_question": self.matched_text,
            "score": round(self.score, 3),
            "confidence": self.confidence,
            "answered": self.answered,
            "category": self.category,
            "feedback": self.feedback,
            "latency_ms": self.latency_ms,
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class HandoffRequest:
    """A request for a human agent."""

    id: int
    session_id: str
    reason: str | None
    last_query: str | None
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        """Serialise for the API."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "reason": self.reason,
            "last_query": self.last_query,
            "created_at": self.created_at,
            "ticket": f"HM-{self.id:05d}",
        }
