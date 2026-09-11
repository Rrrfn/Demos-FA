# -*- coding: utf-8 -*-
"""پیکربندی مرکزی — همهٔ مقادیر از متغیرهای محیطی خوانده می‌شوند.

هیچ مقدار حساسی در کد نیست؛ توکن تلگرام و کلیدهای اختیاری فقط از محیط می‌آیند.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


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


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("GHEMATYAR_DATA_DIR") or BASE_DIR / "data")


@dataclass(frozen=True)
class TelegramConfig:
    """تنظیمات اتصال به تلگرام."""

    token: str = field(default_factory=lambda: _env("TELEGRAM_TOKEN"))
    # webhook (تولید)
    webhook_base_url: str = field(
        default_factory=lambda: _env("RENDER_EXTERNAL_URL") or _env("WEBHOOK_BASE_URL")
    )
    webhook_path: str = field(default_factory=lambda: _env("WEBHOOK_PATH", "/tg-webhook"))
    webhook_secret: str = field(
        default_factory=lambda: _env("TELEGRAM_WEBHOOK_SECRET", "ghematyar-webhook-secret")
    )
    port: int = field(default_factory=lambda: _env_int("PORT", 10000))
    # افراد مجاز به استفاده از دستورهای مدیریتی (خالی = همه)
    admin_ids: tuple[int, ...] = field(
        default_factory=lambda: tuple(
            int(x) for x in _env("ADMIN_IDS").replace(" ", "").split(",") if x.isdigit()
        )
    )

    @property
    def configured(self) -> bool:
        return bool(self.token)

    @property
    def webhook_url(self) -> str:
        if not self.webhook_base_url:
            return ""
        return self.webhook_base_url.rstrip("/") + self.webhook_path


@dataclass(frozen=True)
class DataConfig:
    """تنظیمات لایهٔ داده — کش، تلاش مجدد و آستانهٔ کهنگی."""

    # کش کوتاه‌مدت قیمت‌ها (ثانیه) — درخواست کاربر از همان کش پاسخ می‌گیرد
    cache_ttl: int = field(default_factory=lambda: _env_int("PRICE_CACHE_TTL", 60))
    # اگر داده قدیمی‌تر از این باشد، «کهنه» علامت می‌خورد (ثانیه)
    stale_after: int = field(default_factory=lambda: _env_int("PRICE_STALE_AFTER", 900))
    # اگر داده قدیمی‌تر از این باشد، دیگر نمایش داده نمی‌شود (ثانیه)
    expire_after: int = field(default_factory=lambda: _env_int("PRICE_EXPIRE_AFTER", 3600))
    # شبکه
    request_timeout: float = field(default_factory=lambda: _env_float("HTTP_TIMEOUT", 10.0))
    max_attempts: int = field(default_factory=lambda: _env_int("HTTP_MAX_ATTEMPTS", 3))
    backoff_base: float = field(default_factory=lambda: _env_float("HTTP_BACKOFF_BASE", 0.5))
    backoff_max: float = field(default_factory=lambda: _env_float("HTTP_BACKOFF_MAX", 8.0))
    # مدارشکن: پس از این تعداد خطای پیوسته، سرویس مدتی کنار گذاشته می‌شود
    breaker_threshold: int = field(default_factory=lambda: _env_int("PROVIDER_BREAKER_THRESHOLD", 3))
    breaker_cooldown: int = field(default_factory=lambda: _env_int("PROVIDER_BREAKER_COOLDOWN", 120))
    # تاریخچه
    history_retention_days: int = field(default_factory=lambda: _env_int("HISTORY_RETENTION_DAYS", 90))
    user_agent: str = field(
        default_factory=lambda: _env(
            "HTTP_USER_AGENT",
            "Mozilla/5.0 (compatible; GhematyarBot/2.0; +https://t.me/)",
        )
    )


@dataclass(frozen=True)
class AlertsConfig:
    """تنظیمات موتور هشدار."""

    interval: int = field(default_factory=lambda: _env_int("ALERT_CHECK_INTERVAL", 120))
    max_per_user: int = field(default_factory=lambda: _env_int("MAX_ALERTS_PER_USER", 15))
    # کمینهٔ فاصله بین دو اعلان برای یک قلم (ضد سیل پیام) — ثانیه
    notify_cooldown: int = field(default_factory=lambda: _env_int("ALERT_NOTIFY_COOLDOWN", 600))
    # سقف اعلان ارسالی برای هر کاربر در هر ساعت
    max_notifications_per_hour: int = field(
        default_factory=lambda: _env_int("ALERT_MAX_PER_HOUR", 10)
    )
    # پس از چند بار خطای ارسال، هشدار غیرفعال می‌شود (کاربر ربات را بلاک کرده)
    disable_after_failures: int = field(default_factory=lambda: _env_int("ALERT_DISABLE_AFTER", 5))


@dataclass(frozen=True)
class Config:
    """پیکربندی کامل برنامه."""

    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    data: DataConfig = field(default_factory=DataConfig)
    alerts: AlertsConfig = field(default_factory=AlertsConfig)
    db_path: Path = field(
        default_factory=lambda: Path(
            os.environ.get("GHEMATYAR_DB_PATH") or (DATA_DIR / "ghematyar.db")
        )
    )
    env: str = field(default_factory=lambda: (_env("GHEMATYAR_ENV", "development").lower()))

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    def ensure_dirs(self) -> None:
        """اطمینان از وجود پوشهٔ داده."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)


def load_config() -> Config:
    """ساخت پیکربندی از محیط (یا پیکربندی تزریق‌شده در تست‌ها)."""
    return Config()
