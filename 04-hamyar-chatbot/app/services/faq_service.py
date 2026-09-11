# -*- coding: utf-8 -*-
"""FAQ service — knowledge-base administration use cases."""
from __future__ import annotations

from typing import Any, Iterable

from flask import current_app

from app.database import FaqRepository, session
from app.errors import NotFoundError, ValidationError
from app.models import Faq

from .knowledge_service import rebuild_engine

MAX_VARIANTS = 12
MAX_QUESTION_LENGTH = 300
MAX_CATEGORY_LENGTH = 60


class FaqService:
    """Validation and persistence for knowledge-base entries."""

    # ---------------------------------------------------------------- reads
    @staticmethod
    def list(
        search: str | None = None,
        category: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Return a filtered page of FAQs plus pagination metadata."""
        limit = FaqService._clamp(limit, 1, int(current_app.config["MAX_PAGE_SIZE"]))
        offset = FaqService._clamp(offset, 0, 10**6)
        with session() as conn:
            repository = FaqRepository(conn)
            items = repository.list(
                search=search, category=category, limit=limit, offset=offset
            )
            total = repository.count(search=search, category=category)
        return {
            "items": [faq.to_dict() for faq in items],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    @staticmethod
    def get(faq_id: int) -> Faq:
        """Return one FAQ or raise NotFoundError."""
        with session() as conn:
            faq = FaqRepository(conn).get(faq_id)
        if faq is None:
            raise NotFoundError("این پرسش در دانشنامه وجود ندارد.", {"id": faq_id})
        return faq

    @staticmethod
    def categories() -> list[dict[str, Any]]:
        """Return every category with its FAQ count."""
        with session() as conn:
            return FaqRepository(conn).categories()

    # --------------------------------------------------------------- writes
    @classmethod
    def create(cls, payload: Any) -> Faq:
        """Create a FAQ and refresh the retrieval index."""
        question, answer, category, variants = cls._validate(payload, partial=False)
        with session() as conn:
            faq_id = FaqRepository(conn).create(question, answer, category, variants)
        rebuild_engine()
        return cls.get(faq_id)

    @classmethod
    def update(cls, faq_id: int, payload: Any) -> Faq:
        """Update a FAQ and refresh the retrieval index."""
        question, answer, category, variants = cls._validate(payload, partial=False)
        with session() as conn:
            updated = FaqRepository(conn).update(
                faq_id, question, answer, category, variants
            )
        if not updated:
            raise NotFoundError("این پرسش در دانشنامه وجود ندارد.", {"id": faq_id})
        rebuild_engine()
        return cls.get(faq_id)

    @staticmethod
    def delete(faq_id: int) -> dict[str, Any]:
        """Delete a FAQ and refresh the retrieval index."""
        with session() as conn:
            deleted = FaqRepository(conn).delete(faq_id)
        if not deleted:
            raise NotFoundError("این پرسش در دانشنامه وجود ندارد.", {"id": faq_id})
        stats = rebuild_engine()
        return {"deleted": True, "id": faq_id, "index": stats}

    # -------------------------------------------------------------- helpers
    @staticmethod
    def _clamp(value: Any, low: int, high: int) -> int:
        """Coerce a query-string number into a safe range."""
        try:
            number = int(value)
        except (TypeError, ValueError):
            return low
        return max(low, min(high, number))

    @staticmethod
    def _validate(payload: Any, partial: bool = False) -> tuple[str, str, str, list[str]]:
        """Validate a FAQ payload and return normalized fields.

        ``partial`` is reserved for future PATCH support; PUT requires the full
        record so the knowledge base can never end up half-filled.
        """
        if not isinstance(payload, dict):
            raise ValidationError("بدنهٔ درخواست باید JSON باشد.")

        question = str(payload.get("question") or "").strip()
        answer = str(payload.get("answer") or "").strip()
        category = str(payload.get("category") or "عمومی").strip() or "عمومی"

        errors: dict[str, str] = {}
        if len(question) < 3:
            errors["question"] = "پرسش باید حداقل ۳ نویسه باشد."
        elif len(question) > MAX_QUESTION_LENGTH:
            errors["question"] = f"پرسش بیش از {MAX_QUESTION_LENGTH} نویسه است."
        if len(answer) < 3:
            errors["answer"] = "پاسخ باید حداقل ۳ نویسه باشد."
        elif len(answer) > int(current_app.config["MAX_ANSWER_LENGTH"]):
            errors["answer"] = "پاسخ بیش از حد مجاز است."
        if len(category) > MAX_CATEGORY_LENGTH:
            errors["category"] = f"دسته بیش از {MAX_CATEGORY_LENGTH} نویسه است."

        variants = FaqService._variants(payload.get("variants"))
        if len(variants) > MAX_VARIANTS:
            errors["variants"] = f"حداکثر {MAX_VARIANTS} عبارت جایگزین مجاز است."

        if errors:
            raise ValidationError("اطلاعات دانشنامه کامل نیست.", errors)
        return question, answer, category, variants

    @staticmethod
    def _variants(raw: Any) -> list[str]:
        """Accept a list of strings or a newline/comma separated string."""
        if raw is None:
            return []
        if isinstance(raw, str):
            parts: Iterable[str] = raw.replace(",", "\n").splitlines()
        elif isinstance(raw, (list, tuple)):
            parts = [str(item) for item in raw]
        else:
            raise ValidationError("قالب عبارت‌های جایگزین درست نیست.")
        cleaned: list[str] = []
        seen: set[str] = set()
        for part in parts:
            text = " ".join(str(part).split())
            if not text or text in seen:
                continue
            seen.add(text)
            cleaned.append(text[:MAX_QUESTION_LENGTH])
        return cleaned
