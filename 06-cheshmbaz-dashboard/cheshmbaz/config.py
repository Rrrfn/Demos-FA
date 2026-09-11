# -*- coding: utf-8 -*-
"""پیکربندی مرکزی — همهٔ مقادیر از متغیرهای محیطی خوانده می‌شوند.

پیکربندی عمداً تغییرناپذیر است: هیچ بخشی از برنامه در زمان اجرا آن را
دست‌کاری نمی‌کند. در عوض تست‌ها نسخهٔ تازه می‌سازند.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = _env(name)
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name).lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class DataConfig:
    """تنظیمات لایهٔ شبکه و تازگی داده."""

    request_timeout: float = field(default_factory=lambda: _env_float("HTTP_TIMEOUT", 12.0))
    max_attempts: int = field(default_factory=lambda: _env_int("HTTP_MAX_ATTEMPTS", 3))
    backoff_base: float = field(default_factory=lambda: _env_float("HTTP_BACKOFF_BASE", 0.6))
    backoff_max: float = field(default_factory=lambda: _env_float("HTTP_BACKOFF_MAX", 8.0))
    breaker_threshold: int = field(
        default_factory=lambda: _env_int("PROVIDER_BREAKER_THRESHOLD", 4)
    )
    breaker_cooldown: int = field(
        default_factory=lambda: _env_int("PROVIDER_BREAKER_COOLDOWN", 120)
    )
    user_agent: str = field(
        default_factory=lambda: _env(
            "HTTP_USER_AGENT", "Mozilla/5.0 (compatible; Cheshmbaz/2.0; +https://cheshmbaz.ir)"
        )
    )

    # آستانه‌های تازگی (ثانیه). دادهٔ کهنه برچسب می‌خورد و از این حد به بعد
    # دیگر به‌عنوان قیمت جاری نمایش داده نمی‌شود.
    live_within: int = field(default_factory=lambda: _env_int("DATA_LIVE_WITHIN", 1800))
    stale_after: int = field(default_factory=lambda: _env_int("DATA_STALE_AFTER", 7200))
    expire_after: int = field(default_factory=lambda: _env_int("DATA_EXPIRE_AFTER", 86400))
    history_retention_days: int = field(
        default_factory=lambda: _env_int("HISTORY_RETENTION_DAYS", 400)
    )


@dataclass(frozen=True)
class CollectorConfig:
    """تنظیمات جمع‌آور."""

    interval_seconds: int = field(
        default_factory=lambda: _env_int("COLLECT_INTERVAL_SECONDS", 1800)
    )
    enabled: bool = field(default_factory=lambda: _env_bool("COLLECT_ENABLED", True))
    # چند نمونه بدون تغییر را «راکد» تلقی کنیم و در لاگ هشدار بدهیم
    frozen_gap_max: int = field(default_factory=lambda: _env_int("COLLECT_FROZEN_MAX", 12))


@dataclass(frozen=True)
class AlertConfig:
    """تنظیمات موتور هشدار."""

    # آستانهٔ پیش‌فرض نوسان درصدی
    default_pct: float = field(default_factory=lambda: _env_float("ALERT_PCT", 2.0))
    interval_seconds: int = field(default_factory=lambda: _env_int("ALERT_EVAL_SECONDS", 300))
    # کمینهٔ فاصله بین دو رخداد برای یک قاعده (ضد سیل)
    cooldown_seconds: int = field(default_factory=lambda: _env_int("ALERT_COOLDOWN", 21600))
    max_rules: int = field(default_factory=lambda: _env_int("ALERT_MAX_RULES", 200))
    max_events: int = field(default_factory=lambda: _env_int("ALERT_MAX_EVENTS", 5000))


@dataclass(frozen=True)
class ApiConfig:
    """تنظیمات لایهٔ HTTP."""

    # کش کوتاه‌مدت پاسخ‌ها (ثانیه) — از فشار روی پایگاه داده کم می‌کند
    cache_seconds: int = field(default_factory=lambda: _env_int("API_CACHE_SECONDS", 10))
    default_page_size: int = field(default_factory=lambda: _env_int("API_PAGE_SIZE", 25))
    max_page_size: int = field(default_factory=lambda: _env_int("API_MAX_PAGE_SIZE", 200))


@dataclass(frozen=True)
class Config:
    """پیکربندی کامل برنامه."""

    env: str = field(default_factory=lambda: _env("CHESHMAZ_ENV", "development").lower())
    port: int = field(default_factory=lambda: _env_int("PORT", 10000))
    admin_token: str = field(default_factory=lambda: _env("CHESHMAZ_ADMIN_TOKEN"))
    data_dir: Path = field(
        default_factory=lambda: Path(
            _env("CHESHMAZ_DATA_DIR") or (PROJECT_ROOT / "data")
        )
    )
    db_path: Path = field(
        default_factory=lambda: Path(
            _env("CHESHMAZ_DB_PATH") or (PROJECT_ROOT / "data" / "cheshmbaz.db")
        )
    )

    data: DataConfig = field(default_factory=DataConfig)
    collector: CollectorConfig = field(default_factory=CollectorConfig)
    alerts: AlertConfig = field(default_factory=AlertConfig)
    api: ApiConfig = field(default_factory=ApiConfig)

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    def ensure_dirs(self) -> None:
        """اطمینان از وجود پوشهٔ داده."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def retuned(self, **overrides) -> "Config":
        """نسخهٔ تغییر‌یافته — برای تست‌ها و پروفایل‌های جایگزین."""
        nested: dict[str, dict] = {}
        for key, value in list(overrides.items()):
            if key in {"data", "collector", "alerts", "api"} and isinstance(value, dict):
                nested[key] = value
                overrides.pop(key)
        result: Config = replace(self, **overrides)
        for key, values in nested.items():
            result = replace(result, **{key: replace(getattr(result, key), **values)})
        return result


def load_config() -> Config:
    """خواندن پیکربندی از محیط."""
    return Config()
