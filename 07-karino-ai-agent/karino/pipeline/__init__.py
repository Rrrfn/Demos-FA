# -*- coding: utf-8 -*-
"""خط لولهٔ داده: یکسان‌سازی → حذف تکراری → امتیازدهی → پیشنهاد."""
from .dedupe import SIMILARITY_THRESHOLD, dedupe, known_fingerprints
from .normalize import fingerprint, normalize, similarity
from .proposal import DEFAULT_TONE, TONES, build_proposal
from .scoring import BUDGETS, FACTOR_LABELS, score, verdict_for, verdict_label

__all__ = [
    "normalize", "fingerprint", "similarity",
    "dedupe", "known_fingerprints", "SIMILARITY_THRESHOLD",
    "score", "BUDGETS", "FACTOR_LABELS", "verdict_for", "verdict_label",
    "build_proposal", "TONES", "DEFAULT_TONE",
]
