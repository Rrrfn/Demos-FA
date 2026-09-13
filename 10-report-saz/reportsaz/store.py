# -*- coding: utf-8 -*-
"""انبار بستهٔ پردازش — نگه‌داری فایل، داده، فراداده و خروجی‌ها روی دیسک.

چرا دیسک و نه حافظه؟ سرور WSGI چند کارگر و چند ریسه دارد. اگر نتیجهٔ پردازش
در حافظهٔ یک کارگر بماند، درخواست بعدی که به کارگر دیگری برسد بسته را پیدا
نمی‌کند و کاربر با «یافت نشد» روبه‌رو می‌شود. دیسک مشترک است.

سه قاعده اینجا رعایت می‌شود:

۱) **شناسه پیش از هر کاری اعتبارسنجی می‌شود.** شناسه در نشانی می‌نشیند و
   مستقیماً به مسیر تبدیل می‌شود؛ اگر الگویش بررسی نشود، ``../`` در نشانی به
   مسیر دلخواه روی دیسک می‌رسد. الگو سخت‌گیرانه است: فقط ۱۲ نویسهٔ هگزادسیمال.

۲) **نام فایل ذخیره‌شده هرگز از کاربر گرفته نمی‌شود.** فایل با نام خودمان
   نوشته می‌شود (``source.<ext>``) و نام اصلی فقط به‌عنوان فراداده در JSON
   می‌ماند. این‌طور نام عجیب یا مسیرساز در نام فایل بی‌اثر می‌شود.

۳) **هر بسته پاک می‌شود.** سرویس رایگان دیسک محدود دارد؛ عمر بسته‌ها محدود
   است و تعدادشان سقف دارد. پاک‌سازی خودکار است و به دست کاربر نیاز ندارد.
"""
from __future__ import annotations

import json
import os
import pickle
import re
import secrets
import shutil
import time

from .config import STORE_DIR, STORE_MAX_BUNDLES, STORE_TTL_SECONDS
from .errors import DatasetNotFoundError, FileTooLargeError

#: قالب سخت‌گیرانهٔ شناسه — هر چیزی جز این، درخواست نامعتبر است.
ID_PATTERN = re.compile(r"^[0-9a-f]{12}$")

#: نسخهٔ قالب ذخیره‌سازی. اگر ساختار عوض شود، بستهٔ قدیمی ناخوانا اعلام
#: می‌شود تا از فایل اصلی از نو ساخته شود، نه این‌که خطای عجیب بدهد.
STORE_VERSION = 3

#: دو جدول جداگانه نگه داشته می‌شود: جدول خامِ خوانده‌شده و جدول پاک‌شده.
#: اگر یکی باشند، پاک‌سازی جدول خام را از بین می‌برد و کاربر نمی‌تواند
#: گزینه‌های پاک‌سازی را عوض کند و دوباره اجرا کند — مجبور می‌شود فایل را
#: از نو بارگذاری کند.
FRAME_RAW = "frame_raw.pkl"
FRAME_CLEAN = "frame_clean.pkl"
META_FILE = "meta.json"

#: بخش‌های بایت که هر بار خوانده می‌شود — فایل بزرگ یک‌جا در حافظه نمی‌نشیند.
CHUNK = 1024 * 256


def new_id() -> str:
    """شناسهٔ تازه — تصادفی، پس حدس‌زدن بستهٔ دیگران ممکن نیست."""
    return secrets.token_hex(6)


def validate_id(dataset_id: str | None) -> str:
    """شناسه را بررسی و برمی‌گرداند؛ در غیر این صورت خطای «یافت نشد»."""
    if not dataset_id or not ID_PATTERN.match(str(dataset_id)):
        raise DatasetNotFoundError("این بستهٔ پردازش پیدا نشد یا شناسه‌اش نامعتبر است.")
    return str(dataset_id)


def bundle_dir(dataset_id: str) -> str:
    return os.path.join(STORE_DIR, validate_id(dataset_id))


def exists(dataset_id: str | None) -> bool:
    try:
        return os.path.isdir(bundle_dir(dataset_id))
    except DatasetNotFoundError:
        return False


def create(dataset_id: str) -> str:
    path = bundle_dir(dataset_id)
    os.makedirs(path, exist_ok=True)
    return path


def save_source(dataset_id: str, stream, extension: str,
                limit: int) -> tuple[str, int, bool]:
    """ذخیرهٔ فایل ورودی به‌صورت جریانی.

    جریانی خوانده می‌شود تا فایل ۱۲ مگابایتی یک‌جا در حافظه ننشیند، و در همان
    حال سقف حجم سنجیده می‌شود — اگر مرورگر سقف را دور بزند، اینجا متوقف می‌شود.

    خروجی: ``(مسیر, حجم, بریده‌شده)``
    """
    path = os.path.join(create(dataset_id), f"source.{extension or 'bin'}")
    total = 0
    truncated = False
    with open(path, "wb") as handle:
        while True:
            block = stream.read(CHUNK)
            if not block:
                break
            total += len(block)
            if total > limit:
                truncated = True
                handle.close()
                remove(dataset_id)
                raise FileTooLargeError(
                    f"حجم فایل بیش از حد مجاز است. سقف مجاز "
                    f"{limit // (1024 * 1024)} مگابایت است.",
                    detail=f"received>{limit}")
            handle.write(block)
    return path, total, truncated


def save_meta(dataset_id: str, meta: dict) -> None:
    payload = dict(meta)
    payload["_store_version"] = STORE_VERSION
    payload["_written_at"] = time.time()
    with open(os.path.join(bundle_dir(dataset_id), META_FILE), "w",
              encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def load_meta(dataset_id: str) -> dict:
    path = os.path.join(bundle_dir(dataset_id), META_FILE)
    try:
        with open(path, encoding="utf-8") as handle:
            meta = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        raise DatasetNotFoundError(
            "بستهٔ پردازش ناقص است و خوانده نشد. لطفاً فایل را دوباره بارگذاری کنید.",
            detail=str(error)) from error
    if meta.get("_store_version") != STORE_VERSION:
        raise DatasetNotFoundError(
            "بستهٔ پردازش با نسخهٔ دیگری از سرویس ساخته شده است؛ لطفاً فایل را "
            "دوباره بارگذاری کنید.")
    return meta


def patch_meta(dataset_id: str, **changes) -> dict:
    """به‌روزرسانی بخشی از فراداده — بدون از دست دادن بقیهٔ کلیدها."""
    meta = load_meta(dataset_id)
    meta.update(changes)
    save_meta(dataset_id, meta)
    return load_meta(dataset_id)


def save_frame(dataset_id: str, frame, name: str = FRAME_RAW) -> None:
    """ذخیرهٔ یک جدول.

    قالب pickle انتخاب شده چون داده فقط بین درخواست‌های *همین* سرویس رد و بدل
    می‌شود و نوع ستون‌ها باید دست‌نخورده بماند. نسخهٔ قالب در فراداده ثبت
    می‌شود، پس بستهٔ ناسازگار تشخیص داده و از فایل اصلی از نو ساخته می‌شود.
    """
    with open(os.path.join(bundle_dir(dataset_id), name), "wb") as handle:
        pickle.dump(frame, handle, protocol=pickle.HIGHEST_PROTOCOL)


def load_frame(dataset_id: str, name: str = FRAME_RAW):
    """یک جدول ذخیره‌شده؛ اگر خوانده نشد ``None`` تا از فایل اصلی ساخته شود."""
    path = os.path.join(bundle_dir(dataset_id), name)
    try:
        with open(path, "rb") as handle:
            return pickle.load(handle)
    except (OSError, pickle.UnpicklingError, EOFError, AttributeError, ImportError):
        return None


def drop_frame(dataset_id: str, name: str) -> None:
    """حذف یک جدول ذخیره‌شده. نبودنش خطا نیست."""
    try:
        os.remove(os.path.join(bundle_dir(dataset_id), name))
    except OSError:
        return


def source_path(dataset_id: str) -> str:
    """مسیر فایل اصلی بارگذاری‌شده.

    نام فایل از فراداده خوانده می‌شود چون پسوندش با نوع واقعی فایل عوض می‌شود،
    ولی همیشه نامی است که خودمان ساخته‌ایم — نه نامی که کاربر فرستاده.
    """
    meta = load_meta(dataset_id)
    name = (meta.get("files") or {}).get("source")
    if not name:
        raise DatasetNotFoundError(
            "فایل اصلی این بسته در دسترس نیست؛ لطفاً فایل را دوباره "
            "بارگذاری کنید.")
    return os.path.join(bundle_dir(dataset_id), name)


def artifact_path(dataset_id: str, kind: str) -> str:
    """مسیر خروجی ساخته‌شده (اکسل، PDF) — تنها اگر موجود باشد."""
    return os.path.join(bundle_dir(dataset_id), f"report.{kind}")


def save_artifact(dataset_id: str, kind: str, payload: bytes) -> str:
    path = artifact_path(dataset_id, kind)
    with open(path, "wb") as handle:
        handle.write(payload)
    return path


def has_artifact(dataset_id: str, kind: str) -> bool:
    path = artifact_path(dataset_id, kind)
    return os.path.isfile(path) and os.path.getsize(path) > 0


def remove(dataset_id: str) -> None:
    """حذف کامل یک بسته. نبودنش خطا نیست."""
    try:
        shutil.rmtree(bundle_dir(dataset_id), ignore_errors=True)
    except DatasetNotFoundError:
        return


def touch(dataset_id: str) -> None:
    """به‌روزرسانی زمان آخرین استفاده."""
    try:
        patch_meta(dataset_id, _written_at=time.time())
    except DatasetNotFoundError:
        return


def sweep(force: bool = False) -> dict:
    """پاک‌سازی بسته‌های منقضی و مازاد.

    دو قاعده: هر بسته بالای عمر مجاز پاک می‌شود، و اگر شمار بسته‌ها از سقف
    بگذرد قدیمی‌ترین‌ها پاک می‌شوند. پاک‌سازی روی خودِ ریشه اجرا می‌شود و
    پوشه‌های در حال استفاده (که ویندوز قفل کرده) بی‌صدا رد می‌شوند.
    """
    removed: list[str] = []
    kept: list[tuple[float, str]] = []
    now = time.time()

    try:
        names = os.listdir(STORE_DIR)
    except OSError:
        return {"removed": 0, "kept": 0}

    for name in names:
        path = os.path.join(STORE_DIR, name)
        if not os.path.isdir(path) or not ID_PATTERN.match(name):
            continue
        try:
            stamp = os.path.getmtime(os.path.join(path, META_FILE))
        except OSError:
            stamp = os.path.getmtime(path)

        expired = (now - stamp) > STORE_TTL_SECONDS
        if expired or force:
            if _try_remove(path):
                removed.append(name)
            continue
        kept.append((stamp, name))

    kept.sort()
    overflow = len(kept) - STORE_MAX_BUNDLES
    for _, name in kept[:max(0, overflow)]:
        if _try_remove(os.path.join(STORE_DIR, name)):
            removed.append(name)

    return {"removed": len(removed), "kept": len(kept) - max(0, overflow)}


def _try_remove(path: str) -> bool:
    try:
        shutil.rmtree(path)
        return True
    except OSError:
        return False


def usage() -> dict:
    """حجم و شمار بسته‌های روی دیسک — برای صفحهٔ وضعیت و پاک‌سازی."""
    total = 0
    count = 0
    try:
        names = os.listdir(STORE_DIR)
    except OSError:
        return {"bundles": 0, "bytes": 0}
    for name in names:
        path = os.path.join(STORE_DIR, name)
        if not os.path.isdir(path):
            continue
        count += 1
        for root, _, files in os.walk(path):
            for item in files:
                try:
                    total += os.path.getsize(os.path.join(root, item))
                except OSError:
                    continue
    return {"bundles": count, "bytes": total}
