# -*- coding: utf-8 -*-
"""پیکربندی کارینو — از متغیرهای محیطی خوانده و یک‌بار اعتبارسنجی می‌شود.

همهٔ مقدارها یک جا جمع می‌شوند تا هیچ ماژولی مستقیم ``os.environ`` نخواند؛
این کار تست‌پذیری را ساده می‌کند (فقط ``load_settings`` را monkeypatch می‌کنیم)
و از پیکربندی پراکنده جلوگیری می‌کند.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _env(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    return default if value is None else value.strip()


def _env_int(name: str, default: int, *, low: int | None = None, high: int | None = None) -> int:
    raw = _env(name)
    try:
        value = int(raw) if raw else default
    except ValueError:
        value = default
    if low is not None:
        value = max(low, value)
    if high is not None:
        value = min(high, value)
    return value


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name).lower()
    if not raw:
        return default
    return raw not in {"0", "false", "no", "off"}


def _env_list(name: str) -> list[str]:
    raw = _env(name)
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


@dataclass(frozen=True)
class Settings:
    """تنظیمات بی‌تغییر — یک نمونه در طول عمر پروسه."""

    env: str = "development"
    port: int = 10000

    data_dir: str = field(default_factory=lambda: os.path.join(BASE_DIR, "data"))
    db_path: str = ""

    # منابع — کلیدهای ثبت‌شده در karino.sources.REGISTRY
    enabled_sources: list[str] = field(default_factory=list)
    # فیدهای دلخواه (RSS) که کاربر می‌تواند از داشبورد اضافه کند
    extra_feeds: list[str] = field(default_factory=list)

    # شبکه
    http_timeout: int = 20
    http_retries: int = 2
    http_backoff: float = 1.5

    # خط لوله
    max_jobs: int = 400
    per_source_limit: int = 60
    max_age_days: int = 45

    # پیکربندی پس‌زمینه
    enable_scheduler: bool = True
    fetch_interval_min: int = 360
    collect_on_boot: bool = True

    # آداپتور LLM اختیاری (سازگار با OpenAI)
    llm_url: str = ""
    llm_key: str = ""
    llm_model: str = "gpt-4o-mini"

    # توکن اختیاری برای endpointهای تغییر وضعیت
    admin_token: str = ""

    # دانه‌های نمونه — فقط وقتی هیچ منبع واقعی جواب ندهد و این پرچم روشن باشد
    seed_demo: bool = False

    def ensure_dirs(self) -> None:
        os.makedirs(self.data_dir, exist_ok=True)

    @property
    def is_production(self) -> bool:
        return self.env == "production"


def load_settings() -> Settings:
    """خواندن تنظیمات از محیط با مقادیر پیش‌فرض معقول."""
    data_dir = _env("KARINO_DATA_DIR") or os.path.join(BASE_DIR, "data")
    db_path = _env("KARINO_DB_PATH") or os.path.join(data_dir, "karino.db")
    sources = _env_list("KARINO_SOURCES")

    return Settings(
        env=_env("KARINO_ENV", "development"),
        port=_env_int("PORT", 10000, low=1, high=65535),
        data_dir=data_dir,
        db_path=db_path,
        enabled_sources=sources,
        extra_feeds=_env_list("JOB_FEED_URLS"),
        http_timeout=_env_int("KARINO_HTTP_TIMEOUT", 20, low=3, high=120),
        http_retries=_env_int("KARINO_HTTP_RETRIES", 2, low=0, high=5),
        http_backoff=float(_env("KARINO_HTTP_BACKOFF") or 1.5),
        max_jobs=_env_int("KARINO_MAX_JOBS", 400, low=20, high=10000),
        per_source_limit=_env_int("KARINO_PER_SOURCE_LIMIT", 60, low=5, high=500),
        max_age_days=_env_int("KARINO_MAX_AGE_DAYS", 45, low=1, high=365),
        enable_scheduler=_env_bool("ENABLE_SCHEDULER", True),
        fetch_interval_min=_env_int("FETCH_INTERVAL_MIN", 360, low=5, high=10080),
        collect_on_boot=_env_bool("KARINO_COLLECT_ON_BOOT", True),
        llm_url=_env("KARINO_LLM_URL"),
        llm_key=_env("KARINO_LLM_KEY"),
        llm_model=_env("KARINO_LLM_MODEL", "gpt-4o-mini"),
        admin_token=_env("KARINO_ADMIN_TOKEN"),
        seed_demo=_env_bool("KARINO_SEED_DEMO", False),
    )


_settings: Settings | None = None


def get_settings(refresh: bool = False) -> Settings:
    """نمونهٔ تنها (singleton) با امکان ساخت دوباره در تست‌ها."""
    global _settings
    if _settings is None or refresh:
        _settings = load_settings()
    return _settings
