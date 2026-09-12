# -*- coding: utf-8 -*-
"""مدل‌های دامنه — ساختارهای مشترک بین منابع، خط لوله، حافظه و API.

این مدل‌ها از هم جدا نگه داشته شده‌اند تا هر لایه فقط چیزی را ببیند که لازم
دارد: کانکتور یک ``RawJob`` می‌سازد، خط لوله آن را به ``Job`` بدل می‌کند،
موتور امتیازدهی ``ScoreResult`` برمی‌گرداند و رابط ``ScoreFactor`` را برای
توضیح «چرا این امتیاز؟» رندر می‌کند.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class RawJob:
    """خروجی خام یک کانکتور، پیش از یکسان‌سازی."""

    source: str
    external_id: str
    title: str
    company: str = ""
    url: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    location: str = ""
    remote: bool | None = None
    employment: str = ""
    salary_text: str = ""
    salary_min: float | None = None
    salary_max: float | None = None
    published_ts: int | None = None


@dataclass
class Job:
    """آگهی یکسان‌شده و آمادهٔ ذخیره."""

    source: str
    external_id: str
    title: str
    company: str = ""
    url: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    location: str = ""
    remote: bool = False
    employment: str = ""
    salary_text: str = ""
    salary_min: float | None = None
    salary_max: float | None = None
    published_ts: int | None = None
    fingerprint: str = ""

    @property
    def text_for_matching(self) -> str:
        return " ".join(filter(None, [self.title, self.description, " ".join(self.tags)]))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScoreFactor:
    """یک مؤلفهٔ امتیاز، همراه با مدرکِ خودش.

    ``evidence`` همان چیزی است که «چرا این امتیاز؟» را قابل‌اعتماد می‌کند:
    عدد بدون مدرک، جعبه‌سیاه است.
    """

    key: str
    label: str
    points: float
    max_points: float
    detail: str = ""
    evidence: list[str] = field(default_factory=list)

    @property
    def ratio(self) -> float:
        if self.max_points <= 0:
            return 0.0
        return max(0.0, min(1.0, self.points / self.max_points))

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "points": round(self.points, 1),
            "max_points": self.max_points,
            "ratio": round(self.ratio, 3),
            "detail": self.detail,
            "evidence": self.evidence,
        }


@dataclass
class ScoreResult:
    """نتیجهٔ کامل امتیازدهی یک آگهی."""

    total: int
    verdict: str
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    factors: list[ScoreFactor] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    seniority: str = "unknown"
    engagement: str = "unknown"
    remote: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "verdict": self.verdict,
            "matched_skills": self.matched_skills,
            "missing_skills": self.missing_skills,
            "factors": [f.to_dict() for f in self.factors],
            "reasons": self.reasons,
            "seniority": self.seniority,
            "engagement": self.engagement,
            "remote": self.remote,
        }


#: برچسب فارسی سطح ارشدیت
SENIORITY_LABELS = {
    "junior": "جونیور",
    "mid": "میان‌رده",
    "senior": "سنیور",
    "unknown": "نامشخص",
}

#: برچسب فارسی نوع همکاری
ENGAGEMENT_LABELS = {
    "freelance": "پروژه‌ای / فریلنس",
    "fulltime": "تمام‌وقت",
    "internship": "کارآموزی",
    "unknown": "نامشخص",
}

VERDICT_LABELS = {
    "excellent": "تطابق عالی",
    "strong": "تطابق قوی",
    "moderate": "تطابق متوسط",
    "weak": "تطابق ضعیف",
}


@dataclass
class SourceStatus:
    """وضعیت یک منبع پس از آخرین اجرا."""

    key: str
    label: str
    kind: str = "rss"
    enabled: bool = True
    ok: bool = False
    jobs: int = 0
    error: str = ""
    duration_ms: int = 0
    last_run_ts: int | None = None
    last_success_ts: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "kind": self.kind,
            "enabled": self.enabled,
            "ok": self.ok,
            "jobs": self.jobs,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "last_run_ts": self.last_run_ts,
            "last_success_ts": self.last_success_ts,
        }


@dataclass
class ActivityEvent:
    """رخداد قابل‌نمایش در صفحهٔ فعالیت."""

    kind: str
    message: str
    level: str = "info"
    ts: int | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "message": self.message,
            "level": self.level,
            "ts": self.ts,
            "meta": self.meta,
        }
