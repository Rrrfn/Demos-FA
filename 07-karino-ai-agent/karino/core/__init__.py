# -*- coding: utf-8 -*-
"""لایهٔ پایه: خطاها، متن و مدل‌های دامنه."""
from .errors import (ConflictError, KarinoError, NotFoundError, ProviderError,
                     SourceError, UnauthorizedError, ValidationError)
from .models import (ENGAGEMENT_LABELS, SENIORITY_LABELS, VERDICT_LABELS,
                     ActivityEvent, Job, RawJob, ScoreFactor, ScoreResult,
                     SourceStatus)
from .text import (compact, detect_engagement, detect_seniority, fa_delta,
                   fa_number, freshness_band, normalize_fa, normalize_title,
                   relative_time, search_key, strip_html)

__all__ = [
    "KarinoError", "ValidationError", "NotFoundError", "ConflictError",
    "SourceError", "UnauthorizedError", "ProviderError",
    "RawJob", "Job", "ScoreFactor", "ScoreResult", "SourceStatus",
    "ActivityEvent", "SENIORITY_LABELS", "ENGAGEMENT_LABELS", "VERDICT_LABELS",
    "normalize_fa", "search_key", "strip_html", "compact", "fa_number",
    "fa_delta", "relative_time", "freshness_band", "normalize_title",
    "detect_seniority", "detect_engagement",
]
