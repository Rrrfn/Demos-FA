# -*- coding: utf-8 -*-
"""خط لولهٔ جمع‌آوری — اجرای کامل از منابع تا حافظه.

ترتیب دقیقاً همان چیزی است که محصول وعده می‌دهد:

    منابع → واکشی → یکسان‌سازی → حذف تکراری → امتیازدهی → ذخیره

دو قاعدهٔ سخت در این لایه رعایت می‌شود:

۱) **انزوای خطا.** هر منبع در ``try`` خودش اجرا می‌شود؛ خطای یکی فقط در
   گزارش منابع و صفحهٔ فعالیت ثبت می‌شود و بقیه بی‌وقفه ادامه می‌دهند.

۲) **صداقت داده.** اگر هیچ منبعی جواب نداد، سامانه آگهی جعلی نمی‌سازد؛
   وضعیت «هیچ منبعی پاسخ نداد» را با علت هر منبع برمی‌گرداند تا رابط
   همان را نشان دهد. دانهٔ نمونه فقط با پرچم صریح و با برچسب «نمونه» می‌آید.
"""
from __future__ import annotations

import logging
import time

from ..config import Settings, get_settings
from ..core.models import ActivityEvent, Job, SourceStatus
from ..core.text import fa_number
from ..pipeline.dedupe import dedupe
from ..pipeline.normalize import normalize
from ..pipeline.scoring import score
from ..sources import LABELS, KINDS, build_sources, describe
from ..storage import activity, jobs as jobs_repo, scores as scores_repo
from ..storage import sources as sources_repo
from .seed import sample_jobs

log = logging.getLogger("krn.ingest")


def run_ingest(*, settings: Settings | None = None, sources=None,
               client=None, allow_seed: bool | None = None) -> dict:
    """یک دور کامل جمع‌آوری. خروجی، آمار کامل و قابل‌نمایش است."""
    settings = settings or get_settings()
    started = time.time()
    now = int(started)

    connectors = sources if sources is not None else build_sources(settings, client=client)
    statuses: list[SourceStatus] = []
    raw_jobs = []

    for connector in connectors:
        status = SourceStatus(key=connector.key, label=connector.label,
                              kind=connector.kind)
        t0 = time.time()
        try:
            fetched = connector.fetch()
            status.ok = True
            status.jobs = len(fetched)
            status.last_success_ts = now
            raw_jobs.extend(fetched)
        except Exception as exc:  # noqa: BLE001 — عمداً پهن: انزوای کامل منبع
            status.ok = False
            status.error = _short_error(exc)
            status.jobs = 0
            log.warning("source failed [%s]: %s", connector.key, exc)
            activity.log("source_error",
                         f"منبع «{connector.label}» پاسخ نداد — {status.error}",
                         level="warning", meta={"source": connector.key})
        finally:
            status.duration_ms = int((time.time() - t0) * 1000)
            status.last_run_ts = now
            sources_repo.record(connector.key, ok=status.ok, jobs=status.jobs,
                                error=status.error, duration_ms=status.duration_ms,
                                now=now)
        statuses.append(status)

    seeded = False
    if not raw_jobs:
        if allow_seed is None:
            allow_seed = settings.seed_demo
        if allow_seed:
            raw_jobs = sample_jobs(now=now)
            seeded = True
            statuses.append(SourceStatus(key="seed", label="نمونهٔ آفلاین",
                                         kind="seed", ok=True,
                                         jobs=len(raw_jobs), last_run_ts=now,
                                         last_success_ts=now))
            activity.log("seed_used",
                         "هیچ منبع زنده‌ای پاسخ نداد؛ دانهٔ نمونهٔ آفلاین (با برچسب نمونه) بارگذاری شد",
                         level="warning")
        else:
            activity.log("ingest_empty",
                         "هیچ منبعی آگهی برنگرداند و دانهٔ نمونه غیرفعال است — فهرست خالی ماند",
                         level="warning")

    stats = _store(raw_jobs, now=now, settings=settings)
    stats.update({
        "seeded": seeded,
        "sources": [s.to_dict() for s in statuses],
        "duration_ms": int((time.time() - started) * 1000),
        "live_sources": sum(1 for s in statuses if s.ok and s.key != "seed"),
        "failed_sources": sum(1 for s in statuses if not s.ok),
    })
    stats["message"] = _summary_message(stats)
    activity.log("ingest_done", stats["message"],
                 level="success" if stats["new"] else "info",
                 meta={"new": stats["new"], "scored": stats["scored"],
                       "fetched": stats["fetched"]})
    log.info("ingest done: %s", {k: stats[k] for k in ("fetched", "new", "scored", "unique")})
    return stats


def _store(raw_jobs, *, now: int, settings: Settings) -> dict:
    """یکسان‌سازی → حذف تکراری → امتیازدهی → ذخیره."""
    normalized: list[Job] = [normalize(raw, now=now) for raw in raw_jobs]
    normalized = [job for job in normalized if job.title]

    # انگشت‌نگاشت رکوردهای موجود پاس داده می‌شود تا آگهی‌ای که همین حالا از
    # منبع دیگری ثبت شده، دوباره وارد نشود (تکرار بین‌منبعی در دو دور).
    unique, dedupe_stats = dedupe(normalized,
                                  existing_fingerprints=jobs_repo.existing_fingerprints())

    new_count = updated = scored = 0
    for job in unique:
        job_id, is_new = jobs_repo.upsert(job, now=now)
        if not is_new:
            updated += 1
            continue
        result = score(job, now=now)
        scores_repo.save(job_id, result, now=now)
        new_count += 1
        scored += 1

    pruned = jobs_repo.prune(max_jobs=settings.max_jobs,
                             max_age_days=settings.max_age_days, now=now)

    return {
        "fetched": len(normalized),
        "unique": dedupe_stats["unique"],
        "duplicates": dedupe_stats["duplicate_fingerprint"] + dedupe_stats["duplicate_similar"],
        "duplicates_cross_source": dedupe_stats["duplicate_fingerprint"],
        "duplicates_similar": dedupe_stats["duplicate_similar"],
        "known": dedupe_stats["already_known"],
        "new": new_count,
        "updated": updated,
        "scored": scored,
        "pruned": pruned,
        "total_jobs": jobs_repo.count(),
    }


def score_pending(*, limit: int = 200) -> int:
    """امتیازدهی آگهی‌هایی که از قبل در پایگاه داده هستند ولی امتیاز ندارند."""
    now = int(time.time())
    pending = scores_repo.unscored_job_ids(limit)
    done = 0
    for job_id in pending:
        row = jobs_repo.get(job_id)
        if not row:
            continue
        job = _row_to_job(row)
        scores_repo.save(job_id, score(job, now=now), now=now)
        done += 1
    if done:
        activity.log("score_backfill", f"{fa_number(done)} آگهی امتیازدهی شد",
                     level="info", meta={"count": done})
    return done


def rescore_job(job_id: int, *, now: int | None = None) -> int | None:
    """امتیازدهی دوبارهٔ یک آگهی با پروفایل و وزن‌های فعلی.

    پس از تغییر ترجیحات یا وزن مهارت‌ها لازم است؛ وگرنه امتیاز ذخیره‌شده
    دیگر بازتاب پروفایل فعلی نیست اما همچنان به‌عنوان نظر روز نمایش داده
    می‌شود.
    """
    row = jobs_repo.get(job_id)
    if not row:
        return None
    now = int(now if now is not None else time.time())
    scores_repo.save(job_id, score(_row_to_job(row), now=now), now=now)
    return job_id


def _row_to_job(row) -> Job:
    import json

    try:
        tags = json.loads(row["tags"] or "[]")
    except (ValueError, TypeError):
        tags = []
    return Job(
        source=row["source"], external_id=row["external_id"], title=row["title"],
        company=row["company"] or "", url=row["url"] or "",
        description=row["description"] or "", tags=tags if isinstance(tags, list) else [],
        location=row["location"] or "", remote=bool(row["remote"]),
        employment=row["employment"] or "", salary_text=row["salary_text"] or "",
        salary_min=row["salary_min"], salary_max=row["salary_max"],
        published_ts=row["published_ts"], fingerprint=row["fingerprint"] or "",
    )


def _summary_message(stats: dict) -> str:
    if not stats["fetched"]:
        return "هیچ آگهی تازه‌ای واکشی نشد"
    parts = [f"{fa_number(stats['fetched'])} آگهی واکشی شد، "
             f"{fa_number(stats['unique'])} یکتا پس از حذف تکراری"]
    if stats["new"]:
        parts.append(f"{fa_number(stats['new'])} آگهی تازه ثبت و امتیازدهی شد")
    else:
        parts.append("همه از قبل شناخته‌شده بودند")
    if stats["duplicates"]:
        parts.append(f"{fa_number(stats['duplicates'])} تکرار حذف شد")
    return " · ".join(parts)


def _short_error(exc: Exception) -> str:
    detail = getattr(exc, "detail", "") or str(exc)
    return detail[:300]


def known_sources() -> list[dict]:
    """فهرست همهٔ منابع ثبت‌شده (فعال یا نه) برای صفحهٔ منابع."""
    return [describe(key) for key in LABELS]


__all__ = ["run_ingest", "score_pending", "rescore_job", "known_sources",
           "KINDS", "LABELS"]
