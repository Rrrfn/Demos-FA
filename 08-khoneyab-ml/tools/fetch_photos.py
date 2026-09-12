# -*- coding: utf-8 -*-
"""جمع‌آوری عکس‌های واقعی املاک از ویکی‌انبار.

چرا این ابزار وجود دارد: رابط کاربری باید عکس *واقعی* نشان دهد، نه تصویر برداری
و نه طرح گرافیکی — و باید مطمئن باشیم حق استفاده از هر عکس را داریم. ویکی‌انبار
فرادادهٔ مجوز و پدیدآورنده را همراه فایل می‌دهد و همین کار را قابل استناد
می‌کند: هیچ عکسی بدون ثبت مجوز و صفحهٔ اصلی اثر ذخیره نمی‌شود.

**چرا جست‌وجوی آزاد کافی نیست.** جست‌وجوی متن‌کامل ویکی‌انبار صحنهٔ خیابان،
نقشه، حکاکی و بنای تاریخی هم برمی‌گرداند؛ نتیجه‌اش مجموعه‌ای ناهمگون است که به
نمونه‌کار املاک نمی‌آید. این ابزار به جای جست‌وجو، از **دسته‌های گزیدهٔ** خود
ویکی‌انبار عکس برمی‌دارد:

* نمای بیرونی از دسته‌های «Quality images of houses in <کشور>» — این‌ها را
  داوران انسانی ویکی‌انبار از نظر کیفیت عکاسی تأیید کرده‌اند.
* فضای داخلی از زیردسته‌های «Interiors of houses» که خودشان اتاق‌محورند
  (Living rooms، Kitchens، Bedrooms…). این تفکیک باعث می‌شود عکس آشپزخانه به
  جای نشیمن نرود؛ تناسب موضوع از *دسته* می‌آید، نه از حدس روی عنوان.

فراداده به‌صورت دسته‌ای (`titles` تا ۵۰ مورد در هر درخواست) گرفته می‌شود؛ پس
کل کار با چند درخواست انجام می‌شود، نه صدها درخواست.

اجرا:

    python tools/fetch_photos.py            # دانلود و ساخت آرشیو
    python tools/fetch_photos.py --dry-run  # فقط گزارش انتخاب‌ها
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(BASE_DIR, "static", "img", "properties")
CACHE_DIR = os.path.join(BASE_DIR, "tools", ".cache")
COMMONS_API = "https://commons.wikimedia.org/w/api.php"

#: شناسهٔ توصیفی برای فراخوانی API (سیاست ویکی‌انبار همین را می‌خواهد) و شناسهٔ
#: مرورگری برای *دانلود فایل*؛ سرور فایل، درخواست غیرمرورگری را با ۴۰۳ رد می‌کند.
API_UA = "KhoneyabDemo/1.0 (portfolio demo; contact: demo@example.com)"
IMAGE_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
TIMEOUT = 45
PAUSE = 0.5

#: دسته‌های نمای بیرونی. «Quality images» یعنی داور انسانی کیفیت عکس را تأیید
#: کرده؛ همین باعث می‌شود به جای اسکن بایگانی، عکس واقعی بگیریم.
EXTERIOR_POOLS: tuple[str, ...] = tuple(
    f"Category:Quality images of houses in {country}"
    for country in (
        "Germany", "Netherlands", "Spain", "Portugal", "France", "Poland",
        "Belgium", "Czech Republic", "Russia", "United States", "Iran",
        "the United Kingdom", "Austria", "Switzerland", "Italy", "Sweden",
        "Norway", "Denmark", "Finland", "Hungary", "Sweden",
    )
)

#: دسته‌های فضای داخلی، تفکیک‌شده بر پایهٔ *اتاق*. کلید هر مدخل همان «نوع
#: فضا»یی است که جای‌گاه‌های رابط به آن ارجاع می‌دهند.
INTERIOR_POOLS: dict[str, tuple[str, ...]] = {
    "living": ("Category:Living rooms", "Category:Family rooms"),
    "kitchen": ("Category:Kitchens in residential buildings",
                "Category:Home kitchens", "Category:Kitchens"),
    "bedroom": ("Category:Bedrooms", "Category:Children's rooms"),
    "dining": ("Category:Dining rooms",),
    "office": ("Category:Home offices",),
    "hall": ("Category:Entryrooms in residential units",),
    "bathroom": ("Category:Bathrooms in residential buildings",
                 "Category:Bathrooms"),
}

#: واژهٔ اجباری هر استخر داخلی در **عنوان**. تناسب موضوع از نام اتاق می‌آید؛
#: بدون این شرط، یک عکس «آشپزخانه» در جای‌گاه «اتاق خواب» می‌نشیند.
#: کوئری‌های جست‌وجو برای فضای داخلی — "جست‌وجوی مدرن" استخر دسته‌ای را
#: تکمیل می‌کند، چون دسته‌ها بیشتر عکس مستند از ساختمان‌های قدیمی دارند.
INTERIOR_QUERIES: dict[str, tuple[str, ...]] = {
    "living": ("modern living room interior design", "living room apartment interior",
               "bright living room sofa"),
    "kitchen": ("modern kitchen interior design", "modern kitchen apartment",
                "kitchen interior wood counter"),
    "bedroom": ("modern bedroom interior design", "bedroom apartment interior",
                "bedroom interior bed window"),
    "dining": ("modern dining room interior", "dining room apartment furniture"),
    "office": ("home office interior design", "study room interior desk"),
    "hall": ("modern hallway interior home", "apartment entryway interior"),
    "bathroom": ("modern bathroom interior design", "bathroom apartment tiles"),
}

#: واژهٔ اجباری هر استخر داخلی در **عنوان**. تناسب موضوع از نام اتاق می‌آید؛
#: بدون این شرط، یک عکس «آشپزخانه» در جای‌گاه «اتاق خواب» می‌نشیند.
ROOM_WORDS: dict[str, tuple[str, ...]] = {
    "living": ("living room", "living", "lounge", "family room", "salon"),
    "kitchen": ("kitchen",),
    "bedroom": ("bedroom", "bed room"),
    "dining": ("dining",),
    "office": ("office", "study"),
    "hall": ("hall", "entry", "staircase", "stairs", "corridor"),
    "bathroom": ("bath", "shower"),
}

#: جای‌گاه‌های رابط. ترتیب همان ترتیب نمایش است و `want` وزن موضوعی می‌دهد.
SLOTS: tuple[dict, ...] = (
    {"kind": "exterior", "want": ("modern", "contemporary", "villa")},
    {"kind": "exterior", "want": ("modern", "new", "design")},
    {"kind": "exterior", "want": ("villa", "pool", "modern")},
    {"kind": "exterior", "want": ("house", "garden", "modern")},
    {"kind": "exterior", "want": ("apartment", "building", "modern")},
    {"kind": "exterior", "want": ("apartment", "tower", "modern")},
    {"kind": "exterior", "want": ("balcony", "apartment", "modern")},
    {"kind": "exterior", "want": ("facade", "glass", "modern")},
    {"kind": "exterior", "want": ("townhouse", "modern", "row")},
    {"kind": "exterior", "want": ("terrace", "modern", "house")},
    {"kind": "exterior", "want": ("residential", "complex", "modern")},
    {"kind": "exterior", "want": ("architecture", "modern", "design")},
    {"kind": "exterior", "want": ("house", "modern", "white")},
    {"kind": "exterior", "want": ("building", "modern", "window")},
    {"kind": "exterior", "want": ("villa", "modern", "luxury")},
    {"kind": "exterior", "want": ("residential", "building", "modern")},
    {"kind": "exterior", "want": ("house", "modern", "stone")},
    {"kind": "exterior", "want": ("apartment", "modern", "block")},
    {"kind": "exterior", "want": ("house", "modern", "city")},
    {"kind": "exterior", "want": ("house", "garden", "country")},
    {"kind": "interior", "pool": "living", "want": ("modern", "sofa", "living")},
    {"kind": "interior", "pool": "living", "want": ("bright", "large", "room")},
    {"kind": "interior", "pool": "kitchen", "want": ("modern", "kitchen", "white")},
    {"kind": "interior", "pool": "kitchen", "want": ("kitchen", "wood", "counter")},
    {"kind": "interior", "pool": "bedroom", "want": ("bedroom", "bed", "modern")},
    {"kind": "interior", "pool": "bedroom", "want": ("bedroom", "window", "room")},
    {"kind": "interior", "pool": "dining", "want": ("dining", "table", "room")},
    {"kind": "interior", "pool": "office", "want": ("office", "desk", "study")},
    {"kind": "interior", "pool": "hall", "want": ("hall", "entry", "stair")},
    {"kind": "interior", "pool": "bathroom", "want": ("bathroom", "tile", "modern")},
)

#: کمینهٔ پهنای واقعی فایل. عکسی که از این کوچک‌تر باشد در صفحهٔ ملک محو
#: می‌شود، حتی اگر فراداده چیز دیگری بگوید.
MIN_WIDTH = 1200
#: اندازهٔ یکسان خروجی — گالری نباید عکس‌های ناهماندازه داشته باشد.
OUTPUT_SIZE = (1280, 800)

#: کوئری‌های جست‌وجو برای عکس‌های *امروزی*. دسته‌های «Quality images»
#: تضمین کیفیت عکاسی می‌دهند ولی بیشترشان خانه‌های تاریخی‌اند؛ این کوئری‌ها
#: نمای مدرن را هم به مجموعه اضافه می‌کنند تا حق انتخاب واقعی باشد.
MODERN_QUERIES: tuple[str, ...] = (
    "modern house exterior", "modern villa exterior", "contemporary house design",
    "modern residential building", "modern apartment building exterior",
    "modern architecture house", "new detached house exterior",
    "modern townhouse exterior",
)

#: واژه‌هایی که یعنی عکس به «مسکن» مربوط است.
POSITIVE = (
    "house", "home", "apartment", "building", "villa", "condo", "tower",
    "residence", "residential", "facade", "balcon", "living room", "bedroom",
    "kitchen", "dining", "bathroom", "interior", "room", "real estate",
    "architecture", "flat", "loft", "penthouse", "property", "estate",
    "housing", "townhouse", "terrace", "hallway", "entry",
)
#: واژه‌هایی که یعنی اثر، عکس نیست یا موضوعش ملک نیست. این صافی فقط روی
#: **عنوان** اعمال می‌شود؛ توضیح عکس‌ها اغلب نشانی پستی دارد و واژهٔ «street»
#: در آن، عکس سالم را بی‌دلیل رد می‌کند.
NEGATIVE = (
    # --- اثر غیرعکسی ---
    "plan", "drawing", "sketch", "engraving", "lithograph", "etching", "painting",
    "manuscript", "map", "diagram", "logo", "coat of arms", "flag", "seal",
    "stamp", "poster", "illustration", "cartoon", "clipart", "vector",
    "silhouette", "icon", "graph", "chart", "watercolour", "watercolor",
    "gouache", "woodcut", "aquatint", "monochrome", "black and white",
    "grayscale", "greyscale", "sepia", "bw", "duotone", "catalogue", "catalog",
    # --- بنای غیرمسکونی ---
    "cathedral", "church", "chapel", "mosque", "synagogue", "temple", "abbey",
    "castle", "palace", "museum", "gallery", "ruins", "monument", "memorial",
    "cemetery", "grave", "tomb", "fort", "fortress", "lighthouse", "palace",
    "hospital", "clinic", "school", "university", "college", "library",
    "institute", "academy", "seminary", "convent", "monastery", "dormitory",
    "embassy", "office building", "office block", "corporate office",
    "bank", "hotel", "motel", "hostel", "restaurant", "cafe", "coffee",
    "eatery", "diner", "bistro", "tavern", "pub", "bar", "grill", "brewery",
    "shop", "store", "mall", "outlet",
    "supermarket", "market", "factory", "warehouse", "industrial", "prison",
    "theater", "theatre", "cinema", "stadium", "arena", "station", "airport",
    "harbor", "harbour", "railway", "tram", "subway", "metro", "bridge",
    "dam", "barn", "silo", "hangar", "bunker", "garage", "parking",
    "opera", "observatory", "planetarium",
    # --- بنا و نمای نامناسب برای نمونه‌کار ---
    "abandoned", "derelict", "dilapidated", "ruin", "slum", "shanty", "squat",
    "demolish", "construction site", "scaffold", "soviet", "barracks",
    "asylum", "military", "communal", "prefab", "graffiti", "vandal",
    "collapse", "restoration", "renovation", "heritage", "historic",
    "historical", "victorian", "georgian", "edwardian", "colonial", "medieval",
    "gothic", "baroque", "neoclassical", "ancient", "antique", "vintage",
    "retro", "century", "farmhouse", "cottage", "cabin", "hut", "tribal",
    "vernacular", "chateau", "château", "schloss", "manor", "palace",
    # --- سوژهٔ انسانی و طبیعت بدون بنا ---
    "portrait", "people", "person", "man ", "woman", "child", "family",
    "crowd", "wedding", "parade", "concert", "festival", "ceremony",
    "protest", "selfie", "model", "fashion", "sport", "football", "car",
    "vehicle", "landscape", "mountain", "beach", "sunset", "sunrise",
    "forest", "desert", "field", "farm", "cattle", "animal", "bird",
    "garden path", "sky", "cloud", "panorama", "cityscape", "night sky",
    "snow", "road", "street", "avenue", "boulevard", "highway", "sidewalk",
    "crosswalk", "junction", "intersection", "traffic", "bus stop", "tree",
    "woodland", "meadow", "flower",
    # --- نام‌گذاری بایگانی ---
    "untitled", "unknown", "headquarters", "town hall", "city hall",
    "courthouse", "parliament", "ministry", "roof tile", "brick wall",
    "wall detail", "door detail", "fence", "gate", "ladder", "chimney",
    "interior in art", "in art", "postcard", "aerial",
    # --- نمای داخلی در استخر بیرونی ---
    "ceiling", "room at", "interior of", "inside", "stairs", "staircase",
    # --- املاک اشرافی و بافت روستایی در هر زبان ---
    "estate", "hall house", "manor", "priory", "rectory", "vicarage",
    "abbey house", "mill house", "lodge", "workers", "tenement",
    "histórica", "historica", "historisch", "historique", "maison de",
    "hacienda", "quinta", "palazzetto", "palazzo", "cortijo",
    # --- فضای داخلی که مسکن نیست ---
    "amtrak", "superliner", "train", "railway", "tram", "aircraft",
    "airplane", "airline", "cruise", "ship", "yacht", "boat", "cabin class",
    "first class", "second class", "compartment", "carriage", "berth",
    "museum", "show house", "mystery house", "exhibition", "pavilion",
    "office cubicle", "cubicle", "waiting room", "lobby", "reception",
    "cutting board", "food", "nuts", "herb", "dish", "meal", "recipe",
    "cake", "bread", "coffee cup", "play area", "restroom", "public",
    "cave", "soldiers", "soldier", "barracks room", "dorm", "hostel room",
    "pod", "cubicle", "classroom", "office desk", "institutional",
)
#: عنوانی که «سال بایگانی» دارد (مثل «American homes and gardens (1910)»)
#: اسکن است، نه عکس امروزی.
ARCHIVE_YEAR = re.compile(r"\((1[6-9]\d{2}|20[0-1]\d)\)")


# ------------------------------------------------------------------ دسته‌ها
def _api(params: dict) -> dict:
    """یک فراخوانی API ویکی‌انبار با تلاش دوباره."""
    url = f"{COMMONS_API}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url, headers={"User-Agent": API_UA, "Accept": "application/json"})
    last: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                return json.loads(response.read().decode("utf-8", "replace"))
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.5 * (attempt + 1))
    print(f"    ! API: {type(last).__name__}: {last}")
    return {}


def _cached(name: str, producer) -> object:
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, re.sub(r"[^a-z0-9]+", "-", name.lower())[:90] + ".json")
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError):
            pass
    value = producer()
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False)
    return value


def category_files(category: str, limit: int = 60) -> list[str]:
    """عنوان فایل‌های یک دسته (فقط فایل، نه زیردسته)."""
    def produce() -> list[str]:
        payload = _api({
            "action": "query", "format": "json", "list": "categorymembers",
            "cmtitle": category, "cmlimit": str(limit), "cmtype": "file",
        })
        rows = (payload.get("query") or {}).get("categorymembers") or []
        return [row["title"] for row in rows]

    return _cached(f"cat-{category}-{limit}", produce)  # type: ignore[return-value]


def image_info(titles: list[str]) -> list[dict]:
    """فرادادهٔ دسته‌ای — تا ۵۰ عنوان در هر درخواست."""
    out: list[dict] = []
    for start in range(0, len(titles), 50):
        batch = titles[start:start + 50]

        def produce(batch: list[str] = batch) -> list[dict]:
            payload = _api({
                "action": "query", "format": "json", "titles": "|".join(batch),
                "prop": "imageinfo", "iiprop": "url|size|extmetadata",
                "iiurlwidth": "1920",
            })
            rows = []
            for page in ((payload.get("query") or {}).get("pages") or {}).values():
                info = (page.get("imageinfo") or [{}])[0]
                meta = info.get("extmetadata") or {}
                rows.append({
                    "title": (page.get("title") or "").replace("File:", ""),
                    "width": int(info.get("width") or 0),
                    "height": int(info.get("height") or 0),
                    "url": info.get("thumburl") or "",
                    "landing": info.get("descriptionurl") or "",
                    "license": (meta.get("LicenseShortName") or {}).get("value") or "—",
                    "author": _plain((meta.get("Artist") or {}).get("value") or ""),
                    "description": _plain(
                        (meta.get("ImageDescription") or {}).get("value") or ""),
                })
            return rows

        out.extend(_cached(f"info-{'|'.join(batch)[:120]}", produce))  # type: ignore[arg-type]
        time.sleep(PAUSE)
    return out


def _plain(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()[:140]


# ------------------------------------------------------------------- صافی‌ها
def on_topic(item: dict, *, strict: bool) -> bool:
    """آیا این کاندید عکس واقعی و مرتبط با مسکن است؟

    ``strict`` برای نماهای بیرونی روشن است و یک واژهٔ *قوی* را هم در عنوان
    می‌خواهد؛ وگرنه صحنهٔ خیابان و بافت تاریخی هم از صافی رد می‌شوند چون
    توصیفشان واژهٔ ساختمانی دارد.
    """
    title = item["title"].lower()
    if not title or not item["url"]:
        return False
    if ARCHIVE_YEAR.search(title):
        return False
    for bad in NEGATIVE:
        if re.search(rf"(?<![a-z]){re.escape(bad)}(?:e?s)?(?![a-z])", title):
            return False
    text = f"{title} {item.get('description', '')}".lower()
    if not any(good in text for good in POSITIVE):
        return False
    if strict:
        return any(strong in title for strong in (
            "house", "houses", "home", "homes", "villa", "apartment",
            "apartments", "building", "buildings", "residence", "residences",
            "residential", "facade", "facades", "tower", "towers",
            "condominium", "condo", "housing", "townhouse", "dwelling"))
    return True


def shape_ok(item: dict) -> bool:
    """قاب نزدیک به دوربین و تفکیک‌پذیری کافی."""
    width, height = item["width"], item["height"]
    if width < MIN_WIDTH or not height:
        return False
    aspect = width / height
    return 1.05 <= aspect <= 2.2


def style_score(item: dict, slot: dict) -> float:
    """امتیاز موضوعی: چند واژه از واژه‌های خواستهٔ جای‌گاه در عنوان هست."""
    title = item["title"].lower()
    wanted = sum(1 for word in slot.get("want", ()) if word in title)
    # تفکیک‌پذیری سود محدودی دارد؛ بدون سقف، یک عکس عظیم همه را کنار می‌زند.
    resolution = min(item["width"], 2200) * min(item["height"], 1400)
    return resolution * (1.0 + 0.55 * wanted)


# ------------------------------------------------------------------ دانلود
def fetch_full_size(item: dict) -> bytes | None:
    """فایل واقعی — با بررسی پهنای *واقعی* پس از رمزگشایی."""
    from PIL import Image

    try:
        request = urllib.request.Request(item["url"], headers={"User-Agent": IMAGE_UA})
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            raw = response.read()
    except Exception:                      # کاندید بعدی امتحان می‌شود
        return None
    if len(raw) < 20_000:                  # صفحهٔ خطا، نه تصویر
        return None
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            if probe.width < MIN_WIDTH or probe.format not in ("JPEG", "PNG", "WEBP"):
                return None
    except Exception:
        return None
    return raw


def normalize_image(raw: bytes, *, size: tuple[int, int]) -> bytes:
    """برش میانی + تغییر اندازه + فشرده‌سازی — بدون بالا‌نمایی."""
    from PIL import Image

    with Image.open(io.BytesIO(raw)) as source:
        img = source.convert("RGB")
        target_w, target_h = size
        scale = min(max(target_w / img.width, target_h / img.height), 1.0)
        width = max(1, round(img.width * scale))
        height = max(1, round(img.height * scale))
        resized = img.resize((width, height), Image.LANCZOS)
        crop_w, crop_h = min(target_w, width), min(target_h, height)
        left, top = (width - crop_w) // 2, (height - crop_h) // 2
        cropped = resized.crop((left, top, left + crop_w, top + crop_h))
        buffer = io.BytesIO()
        cropped.save(buffer, format="JPEG", quality=82, optimize=True, progressive=True)
        return buffer.getvalue()


def clean_title(title: str) -> str:
    """عنوان قابل نمایش در جدول اعتبارها (بدون کد دوربین و پسوند فایل)."""
    text = re.sub(r"\.(jpe?g|png|webp|tiff?)$", "", title or "", flags=re.I)
    text = re.sub(r"^[A-Z]{2,5}[-_]?\d{3,6}\s+", "", text).strip()
    return re.sub(r"\s+", " ", text)[:90] or "عکس آزاد املاک"


def slug(index: int, kind: str, title: str) -> str:
    stem = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:34]
    return f"{kind}-{index:02d}-{stem or 'property'}.jpg"


# ------------------------------------------------------------------ خروجی‌ها
def credits_markdown(manifest: list[dict]) -> str:
    lines = [
        "# اعتبار تصاویر",
        "",
        "همهٔ عکس‌های این پوشه از",
        "[ویکی‌انبار](https://commons.wikimedia.org) — مخزن رسانهٔ ویکی‌پدیا —",
        "برداشته شده‌اند. بیشترشان از دستهٔ «Quality images of houses» هستند که",
        "داوران انسانی ویکی‌انبار کیفیت عکاسی آن‌ها را تأیید کرده‌اند. مجوز هر",
        "فایل و نام پدیدآورنده در جدول زیر آمده است؛ در نمایش عمومی این پروژه هم",
        "اعتبار تصویر در صفحهٔ جزئیات ملک و در صفحهٔ «روش‌شناسی» ذکر می‌شود.",
        "",
        "**تصاویر نمادین‌اند.** هر ملک در این پروژه سینتتیک است و عکس واقعی آن ملک",
        "وجود ندارد؛ این تصاویر فقط برای نمایش کیفیت رابط کاربری انتخاب شده‌اند و",
        "نباید به‌عنوان عکس یک آگهی واقعی یا نشانهٔ وضعیت آن ملک تلقی شوند.",
        "",
        "| فایل | موضوع | منبع | مجوز | پدیدآورنده | صفحهٔ اثر |",
        "|---|---|---|---|---|---|",
    ]
    for item in manifest:
        lines.append(
            f"| `{item['file']}` | {item['title']} | {item['provider']} | "
            f"{item['license']} | {item['author'] or '—'} | "
            f"[مشاهده]({item['landing']}) |")
    return "\n".join(lines) + "\n"


def write_outputs(manifest: list[dict]) -> None:
    """نوشتن فهرست و فایل اعتبارها — قابل فراخوانی در میان اجرا."""
    with open(os.path.join(OUT_DIR, "manifest.json"), "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
    with open(os.path.join(OUT_DIR, "CREDITS.md"), "w", encoding="utf-8") as handle:
        handle.write(credits_markdown(manifest))


# --------------------------------------------------------------------- اجرا
def search_modern(query: str) -> list[dict]:
    """جست‌وجوی متن‌کامل برای نمای امروزی (فراداده به شکل استخر بالا)."""
    def produce() -> list[dict]:
        payload = _api({
            "action": "query", "format": "json", "generator": "search",
            "gsrsearch": f"filetype:bitmap {query}", "gsrnamespace": "6",
            "gsrlimit": "40", "prop": "imageinfo",
            "iiprop": "url|size|extmetadata", "iiurlwidth": "1920",
        })
        rows = []
        for page in ((payload.get("query") or {}).get("pages") or {}).values():
            info = (page.get("imageinfo") or [{}])[0]
            meta = info.get("extmetadata") or {}
            rows.append({
                "title": (page.get("title") or "").replace("File:", ""),
                "width": int(info.get("width") or 0),
                "height": int(info.get("height") or 0),
                "url": info.get("thumburl") or "",
                "landing": info.get("descriptionurl") or "",
                "license": (meta.get("LicenseShortName") or {}).get("value") or "—",
                "author": _plain((meta.get("Artist") or {}).get("value") or ""),
                "description": _plain(
                    (meta.get("ImageDescription") or {}).get("value") or ""),
            })
        return rows

    return _cached(f"search-{query}", produce)  # type: ignore[return-value]


def gather_pools() -> tuple[list[dict], dict[str, list[dict]]]:
    """ساخت مجموعهٔ کاندیدهای نما و فضای داخلی."""
    titles = []
    for category in EXTERIOR_POOLS:
        titles.extend(category_files(category))
    quality = [item for item in image_info(sorted(set(titles)))
               if shape_ok(item) and on_topic(item, strict=True)]

    searched: list[dict] = []
    for query in MODERN_QUERIES:
        for item in search_modern(query):
            if shape_ok(item) and on_topic(item, strict=True):
                searched.append(item)
        time.sleep(PAUSE)

    seen: set[str] = set()
    exteriors: list[dict] = []
    for item in quality + searched:
        if item["title"] in seen:
            continue
        seen.add(item["title"])
        exteriors.append(item)
    print(f"  · نما: {len(quality)} از دستهٔ گزیده + {len(searched)} از جست‌وجو")

    interiors: dict[str, list[dict]] = {}
    for pool, categories in INTERIOR_POOLS.items():
        pool_titles: list[str] = []
        for category in categories:
            pool_titles.extend(category_files(category, limit=50))
        rows = image_info(sorted(set(pool_titles)))
        for query in INTERIOR_QUERIES.get(pool, ()):
            rows.extend(search_modern(query))
            time.sleep(PAUSE)
        rooms = []
        seen: set[str] = set()
        for item in rows:
            if item["title"] in seen:
                continue
            seen.add(item["title"])
            if not shape_ok(item) or not on_topic(item, strict=False):
                continue
            if not _has_room_word(item["title"], pool):
                continue
            item["pool"] = pool
            rooms.append(item)
        interiors[pool] = rooms
        print(f"  · استخر «{pool}»: {len(rooms)} کاندید")
    return exteriors, interiors


def series_key(title: str) -> str:
    """کلید «سری» عکس‌ها: چند واژهٔ نخست پس از حذف شماره و عدد.

    عکس‌های یک بنا از زاویه‌های مختلف، کلید یکسان می‌گیرند تا همه در گالری
    تکرار نشوند. عددها حذف می‌شوند چون شمارهٔ نسخه‌اند، نه موضوع.
    """
    words = re.sub(r"[^a-z\s]+", " ", (title or "").lower()).split()
    return " ".join(words[:3])


def _has_room_word(title: str, pool: str) -> bool:
    """آیا نام همان اتاق در عنوان هست؟ (شرط دقت برای فضای داخلی)"""
    text = title.lower()
    return any(word in text for word in ROOM_WORDS[pool])


def main() -> int:
    parser = argparse.ArgumentParser(description="جمع‌آوری عکس‌های واقعی و آزاد املاک")
    parser.add_argument("--dry-run", action="store_true",
                        help="فقط انتخاب‌ها را گزارش کن، چیزی دانلود نکن")
    args = parser.parse_args()

    print("دریافت کاندیدها از ویکی‌انبار…")
    exteriors, interiors = gather_pools()
    print(f"  · نماها: {len(exteriors)} کاندید")
    if not exteriors and not any(interiors.values()):
        print("هیچ کاندیدی پیدا نشد.")
        return 1

    # هر جای‌گاه بهترین کاندیدِ هنوزنبرداشته را می‌گیرد. این انتساب
    # «طمع‌کارانه» است و تضمین می‌کند یک عکس در دو جای‌گاه تکرار نشود.
    used_titles: set[str] = set()
    used_series: set[str] = set()
    plan: list[dict] = []
    for slot in SLOTS:
        source = exteriors if slot["kind"] == "exterior" else interiors.get(slot.get("pool", ""), [])
        ranked = sorted((item for item in source if item["title"] not in used_titles),
                        key=lambda item: -style_score(item, slot))
        # یک عمارت از هفت زاویه، هفت عکس جدا نیست. عکس‌های یک «سری»
        # (نام بنای یکسان) فقط یک بار برداشته می‌شوند تا گالری تکراری نشود.
        ranked = [item for item in ranked if series_key(item["title"]) not in used_series]
        if not ranked:
            ranked = sorted((item for item in source if item["title"] not in used_titles),
                            key=lambda item: -style_score(item, slot))[:1]
        if not ranked:
            print(f"  ✗ جای‌گاه بی‌کاندید: {slot['kind']}/{slot.get('pool')}")
            continue
        chosen = ranked[0]
        used_titles.add(chosen["title"])
        used_series.add(series_key(chosen["title"]))
        plan.append({"kind": slot["kind"], "item": chosen,
                     "alternates": ranked[1:], "slot": slot})
        print(f"  · {slot['kind']}: {clean_title(chosen['title'])[:52]} "
              f"[{chosen['width']}px، {len(ranked) - 1} جانشین]")

    exteriors_count = sum(1 for entry in plan if entry["kind"] == "exterior")
    print(f"\n{len(plan)} جای‌گاه پر شد — {exteriors_count} نما، "
          f"{len(plan) - exteriors_count} داخل.")

    if args.dry_run:
        print("(حالت آزمایشی — چیزی نوشته نشد.)")
        return 0
    if not plan:
        return 1

    os.makedirs(OUT_DIR, exist_ok=True)
    manifest: list[dict] = []
    for index, entry in enumerate(plan, start=1):
        saved = False
        for item in [entry["item"], *entry["alternates"][:12]]:
            raw = fetch_full_size(item)
            if raw is None:
                continue
            type_ = "exterior" if entry["kind"] == "exterior" else "interior"
            name = slug(index, type_, item["title"])
            try:
                with open(os.path.join(OUT_DIR, name), "wb") as handle:
                    handle.write(normalize_image(raw, size=OUTPUT_SIZE))
            except Exception as exc:       # یک عکس خراب کل کار را نمی‌خواباند
                print(f"    ✗ {name}: {type(exc).__name__}: {exc}")
                continue
            manifest.append({
                "file": name, "kind": type_,
                "title": clean_title(item["title"]),
                "provider": "Wikimedia Commons",
                "license": item["license"],
                "author": item["author"],
                "landing": item["landing"],
                "source_url": item["url"],
            })
            print(f"  ✓ {name}  ({item['width']}×{item['height']})")
            saved = True
            break
        if not saved:
            print(f"    ✗ جای‌گاه {index}: هیچ کاندیدی فایل کامل نداد")
        write_outputs(manifest)           # فهرست پس از هر عکس نوشته می‌شود
        time.sleep(0.3)

    manifest = drop_duplicate_files(manifest)
    write_outputs(manifest)
    print(f"\n{len(manifest)} عکس ذخیره شد → {OUT_DIR}")
    return 0


def drop_duplicate_files(manifest: list[dict]) -> list[dict]:
    """حذف عکس‌های تکراری بر پایهٔ *محتوای* فایل.

    عنوان‌های ویکی‌انبار همیشه یک بنا را یکسان نام نمی‌دهند، پس صافی عنوان
    کافی نیست؛ مقایسهٔ درهم‌سازی محتوا تضمین می‌کند دو آگهی عکس یکسان نگیرند.
    """
    import hashlib

    seen: dict[str, str] = {}
    kept: list[dict] = []
    for item in manifest:
        path = os.path.join(OUT_DIR, item["file"])
        try:
            with open(path, "rb") as handle:
                digest = hashlib.sha256(handle.read()).hexdigest()
        except OSError:
            continue
        if digest in seen:
            os.remove(path)
            print(f"  − حذف تکراری: {item['file']} (همان {seen[digest]})")
            continue
        seen[digest] = item["file"]
        kept.append(item)
    return kept


if __name__ == "__main__":
    sys.exit(main())
