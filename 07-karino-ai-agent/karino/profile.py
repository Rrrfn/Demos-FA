# -*- coding: utf-8 -*-
"""پروفایل تخصصی و سبد نمونه‌کار — ورودی موتور تطبیق و نویسندهٔ پیشنهاد.

این فایل تنها منبع حقیقت دربارهٔ «من چه می‌دانم» و «چه ساخته‌ام» است.
هیچ مهارت یا نمونه‌کاری جای دیگری hard-code نمی‌شود؛ موتور امتیازدهی و
نویسندهٔ پیشنهاد هر دو از همین‌جا می‌خوانند تا توضیح‌ها با مدرک‌ها یکی باشند.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Skill:
    """یک مهارت با وزن، نام فارسی و الگوهای متنی."""

    key: str
    fa: str
    weight: int          # ۱..۱۰ — ۱۰ یعنی تخصص اصلی
    category: str
    aliases: tuple[str, ...] = ()

    @property
    def patterns(self) -> tuple[str, ...]:
        return self.aliases or (self.key,)


def _s(key: str, fa: str, weight: int, category: str, *aliases: str) -> Skill:
    return Skill(key=key, fa=fa, weight=weight, category=category, aliases=tuple(aliases))


#: دستهٔ مهارت‌ها برای نمایش گروهی در پروفایل و تحلیل تطابق
CATEGORIES = {
    "backend": "بک‌اند و API",
    "data": "داده و تحلیل",
    "ai": "هوش مصنوعی",
    "automation": "اتوماسیون و اسکرپینگ",
    "frontend": "فرانت‌اند",
    "infra": "زیرساخت و دواپس",
    "platform": "پلتفرم و ابزار",
}

SKILLS: dict[str, Skill] = {
    # --- بک‌اند ---
    "python": _s("python", "پایتون", 10, "backend", "python", "پایتون", "py3"),
    "flask": _s("flask", "Flask", 9, "backend", "flask", "فلسک"),
    "django": _s("django", "Django", 7, "backend", "django", "جنگو"),
    # "apis" جداگانه آمده چون تطبیق با مرز واژه انجام می‌شود و الگوی "api"
    # جمع را نمی‌گیرد؛ در حالی که «REST APIs» رایج‌ترین شکل نوشتن این مهارت است.
    "rest_api": _s("rest_api", "طراحی REST API", 9, "backend",
                   "rest api", "apis", "restful", "api", "وب سرویس", "webservice", "endpoint"),
    # نام رسمی دیتابیس‌ها هم می‌آید: "PostgreSQL" با الگوی "postgres" تطبیق
    # نمی‌شود، وگرنه یکی از رایج‌ترین نیازهای آگهی‌های پایتون از دست می‌رفت.
    "sql": _s("sql", "دیتابیس SQL", 7, "backend",
              "mysql", "postgresql", "postgres", "sqlite3", "sqlite", "mssql",
              "sql server", "database", "دیتابیس"),
    "graphql": _s("graphql", "GraphQL", 4, "backend", "graphql"),
    # --- داده و تحلیل ---
    "pandas": _s("pandas", "تحلیل داده (pandas)", 8, "data",
                 "pandas", "dataframe", "تحلیل داده", "data analysis", "numpy"),
    "visualization": _s("visualization", "داشبورد و مصورسازی", 7, "data",
                        "dashboard", "chart", "visualization", "داشبورد", "نمودار", "power bi", "powerbi", "tableau"),
    "excel": _s("excel", "اکسل و گزارش‌سازی", 6, "data",
                "excel", "اکسل", "report", "گزارش", "csv", "spreadsheet"),
    # --- هوش مصنوعی ---
    "ml": _s("ml", "یادگیری ماشین", 7, "ai",
             "machine learning", "یادگیری ماشین", "scikit", "sklearn", "xgboost", "مدل پیش بینی", "regression", "classification"),
    "nlp": _s("nlp", "پردازش زبان طبیعی", 7, "ai",
              "nlp", "زبان طبیعی", "text mining", "tokeniz", "tf-idf", "tfidf", "embedding", "sentiment"),
    "llm": _s("llm", "کار با LLM و چت‌بات", 8, "ai",
              "llm", "gpt", "openai", "chatbot", "چت بات", "چت‌بات", "rag", "prompt", "agent", "هوش مصنوعی", "ai "),
    "telegram_bot": _s("telegram_bot", "ربات تلگرام", 9, "automation",
                       "telegram", "تلگرام", "aiogram", "python-telegram-bot", "بات تلگرام"),
    # --- اتوماسیون ---
    "scraping": _s("scraping", "وب‌اسکرپینگ", 9, "automation",
                   "scraping", "scraper", "crawl", "spider", "beautifulsoup", "bs4", "playwright",
                   "اسکرپ", "خزنده", "کراول", "استخراج داده", "جمع اوری داده"),
    "automation": _s("automation", "اتوماسیون و زمان‌بندی", 8, "automation",
                     "automation", "اتوماسیون", "خودکارسازی", "script", "اسکریپت",
                     "selenium", "cron", "scheduler", "زمان بندی"),
    "etl": _s("etl", "ETL و پایپ‌لاین داده", 7, "data",
              "etl", "pipeline", "airflow", "ingest", "data pipeline", "پایپ لاین", "خط لوله داده"),
    # --- فرانت‌اند ---
    "web_dev": _s("web_dev", "توسعه وب (HTML/CSS/JS)", 7, "frontend",
                  "html", "css", "javascript", "frontend", "فرانت", "ریسپانسیو", "responsive"),
    "react": _s("react", "React", 3, "frontend", "react", "next.js", "nextjs", "ری اکت"),
    # --- زیرساخت ---
    "docker": _s("docker", "داکر و کانتینر", 5, "infra", "docker", "dockerfile", "container", "داکر"),
    "devops": _s("devops", "CI/CD و دواپس", 5, "infra",
                 "ci/cd", "cicd", "devops", "deployment", "دواپس", "استقرار"),
    # --- پلتفرم ---
    "wordpress": _s("wordpress", "وردپرس / ووکامرس", 4, "platform",
                    "wordpress", "وردپرس", "woocommerce", "ووکامرس"),
    "git": _s("git", "گیت", 6, "platform", "git", "github", "gitlab", "گیت"),
}

#: وزن کل پروفایل — مخرج سهم مهارت‌ها
TOTAL_WEIGHT = sum(s.weight for s in SKILLS.values())

#: سقف واقع‌بینانهٔ وزن منطبق؛ فرض نمی‌کنیم آگهی کل پروفایل را بخواهد.
#: ۴۲ یعنی پوشش حدود دو تخصص اصلی + یک ابزار، که در عمل «تطابق کامل» است.
SKILL_TARGET_WEIGHT = 42


@dataclass(frozen=True)
class PortfolioProject:
    """نمونه‌کار زنده — به‌عنوان مدرک در پیشنهاد استناد می‌شود."""

    id: str
    title: str
    summary: str
    stack: tuple[str, ...]
    skills: tuple[str, ...]
    metric: str = ""


#: سبد نمونه‌کار — هر پروژه فقط به مهارت‌هایی وصل است که واقعاً در آن هست
PORTFOLIO: tuple[PortfolioProject, ...] = (
    PortfolioProject(
        id="parfum",
        title="فروشگاه نیچ عطر «نافه»",
        summary="فروشگاه اینترنتی ۳۱ صفحه‌ای با سبد خرید پایدار، فیلتر و جست‌وجوی زنده و تسویه اعتبارسنجی‌شده",
        stack=("HTML", "CSS", "JavaScript"),
        skills=("web_dev", "rest_api", "sql"),
        metric="۳۱ صفحه، سبد خرید با ذخیره‌سازی محلی",
    ),
    PortfolioProject(
        id="support",
        title="پلتفرم پشتیبانی هوشمند «همیار»",
        summary="کنسول پشتیبانی با موتور بازیابی TF-IDF، آستانهٔ اطمینان، پاسخ خودکار و پنل مدیریت دانش",
        stack=("Python", "Flask", "SQLite"),
        skills=("python", "flask", "nlp", "rest_api", "llm"),
        metric="۱۴۸ تست، پوشش دسته‌بندی و لاگ گفتگو",
    ),
    PortfolioProject(
        id="ghemat",
        title="ربات پایش بازار «قیمت‌یار»",
        summary="ربات تلگرام با دادهٔ زندهٔ طلا/ارز/رمزارز، موتور هشدار آستانه‌ای و حالت وب‌هوک برای تولید",
        stack=("Python", "aiogram", "SQLite"),
        skills=("python", "telegram_bot", "automation", "sql", "rest_api"),
        metric="۲۳۹ تست، ۲۵ دارایی، کشف دادهٔ کهنه",
    ),
    PortfolioProject(
        id="market",
        title="داشبورد هوش بازار «چشم‌باز»",
        summary="داشبورد ترمینال تیره روی دادهٔ واقعی، سری زمانی ۱ تا ۹۰ روز، رتبه‌بندی نوسان و موتور هشدار",
        stack=("Python", "Flask", "SQLite", "SVG"),
        skills=("python", "flask", "visualization", "etl", "automation", "sql"),
        metric="۱۸۹ تست، بدون دادهٔ ساختگی در نمودار",
    ),
    PortfolioProject(
        id="karino",
        title="پلتفرم هوش استخدام «کارینو»",
        summary="خط لولهٔ جمع‌آوری آگهی از منابع چندگانه، تطبیق امتیازدهی شفاف و پیشنهادنویس خودکار",
        stack=("Python", "Flask", "SQLite"),
        skills=("python", "flask", "scraping", "nlp", "etl", "rest_api"),
        metric="همین سامانه — خط لولهٔ زنده از چند منبع",
    ),
    PortfolioProject(
        id="scraper",
        title="جمع‌آورندهٔ داده با زمان‌بندی",
        summary="اسکریپت جمع‌آوری داده از منابع چندگانه با تلاش مجدد، تشخیص داده کهنه و گزارش‌سازی اکسل",
        stack=("Python", "requests", "pandas"),
        skills=("python", "scraping", "automation", "pandas", "excel", "etl"),
        metric="اجرای زمان‌بندی‌شده با لاگ کامل",
    ),
    PortfolioProject(
        id="predict",
        title="مدل پیش‌بینی با scikit-learn",
        summary="آماده‌سازی دیتاست، آموزش مدل، اعتبارسنجی و گزارش شاخص‌های دقت",
        stack=("Python", "scikit-learn"),
        skills=("python", "ml", "pandas"),
        metric="گزارش MAE و مقایسهٔ مدل‌ها",
    ),
    PortfolioProject(
        id="automate",
        title="اتوماسیون کارهای تکراری اداری",
        summary="خودکارسازی ورود داده و تولید گزارش دوره‌ای، با لاگ و هشدار خطا",
        stack=("Python", "Selenium", "pandas"),
        skills=("python", "automation", "excel", "pandas"),
        metric="کاهش کار دستی تکراری",
    ),
)

PORTFOLIO_BY_ID = {p.id: p for p in PORTFOLIO}


@dataclass(frozen=True)
class Preferences:
    """ترجیحات کاری — در امتیازدهی به‌صورت امتیاز یا کسر اثر می‌گذارند."""

    #: سطح ارشدیت هدف؛ آگهی هم‌سطح امتیاز کامل می‌گیرد
    target_seniority: str = "senior"
    #: نوع همکاری ترجیحی
    preferred_engagement: tuple[str, ...] = ("freelance", "fulltime")
    #: نامطلوب — آگهی این‌گونه امتیاز از دست می‌دهد
    disliked_engagement: tuple[str, ...] = ("internship",)
    #: دورکاری ترجیح دارد
    prefers_remote: bool = True
    #: منطقهٔ مطلوب برای کار حضوری (نام‌های یکسان‌شده)
    preferred_locations: tuple[str, ...] = ("تهران", "ایران", "remote", "anywhere", "worldwide", "anywhere in the world")
    #: علامت‌های «کارفرمای جدی» که امتیاز مشتری می‌دهند
    client_signal_words: tuple[str, ...] = (
        "استخدام", "همکاری", "تیم", "شرکت", "هلدینگ", "پروژه", "محصول",
        "hiring", "team", "company", "product", "startup", "سابقه", "قرارداد",
    )


PREFS = Preferences()

#: آستانهٔ ورود به فهرست «پیشنهاد ویژه» در داشبورد
TOP_SCORE_THRESHOLD = 72


def skill(key: str) -> Skill | None:
    return SKILLS.get(key)


def fa_names(keys: list[str], limit: int | None = None) -> list[str]:
    """نام‌های فارسی مهارت‌ها، با حفظ ترتیب و حذف ناشناخته‌ها."""
    out = [SKILLS[k].fa for k in keys if k in SKILLS]
    return out[:limit] if limit else out


def skills_by_category(keys: list[str]) -> dict[str, list[str]]:
    """گروه‌بندی نام‌های فارسی بر اساس دسته — برای نمایش تحلیل تطابق."""
    grouped: dict[str, list[str]] = {}
    for key in keys:
        spec = SKILLS.get(key)
        if not spec:
            continue
        grouped.setdefault(spec.category, []).append(spec.fa)
    return grouped


def match_skills(text: str) -> tuple[list[str], list[str]]:
    """مهارت‌های منطبق و غایب بر اساس الگوهای پروفایل (متن از قبل یکسان‌شده)."""
    haystack = " " + (text or "").lower() + " "
    matched: list[str] = []
    missing: list[str] = []
    for key, spec in SKILLS.items():
        if any(_pattern_hit(haystack, p) for p in spec.patterns):
            matched.append(key)
        else:
            missing.append(key)
    return matched, missing


def _pattern_hit(haystack: str, pattern: str) -> bool:
    """تطبیق الگو با مرز واژه برای عبارت‌های لاتین، و تطبیق ساده برای فارسی.

    بدون مرز واژه، «ai» داخل «email» و «maintenance» پیدا می‌شود و امتیاز را
    بی‌دلیل بالا می‌برد؛ ولی مهارت‌های فارسی چون فاصله‌گذاری‌شان مبهم است
    با تطبیق زیررشته‌ای سنجیده می‌شوند.
    """
    p = pattern.lower().strip()
    if not p:
        return False
    if p.isascii() and any(ch.isalnum() for ch in p):
        import re

        # عبارت‌های چندواژه‌ای و کوتاه هم مرز واژه می‌خواهند
        return re.search(rf"(?<![a-z0-9]){re.escape(p)}(?![a-z0-9])", haystack) is not None
    return p in haystack


def relevant_projects(matched: list[str], limit: int = 3) -> list[PortfolioProject]:
    """نمونه‌کارهای مرتبط، مرتب‌شده بر اساس هم‌پوشانی مهارت با آگهی.

    این تابع همان چیزی است که پیشنهاد را «مدرک‌محور» می‌کند: به‌جای فهرست
    ثابت، هر آگهی نمونه‌کارهای متناسب خودش را می‌گیرد.
    """
    matched_set = set(matched)
    scored: list[tuple[int, PortfolioProject]] = []
    for project in PORTFOLIO:
        overlap = len(matched_set.intersection(project.skills))
        if overlap:
            scored.append((overlap, project))
    scored.sort(key=lambda pair: (-pair[0], -sum(SKILLS[s].weight for s in pair[1].skills if s in SKILLS)))
    return [project for _, project in scored[:limit]]
