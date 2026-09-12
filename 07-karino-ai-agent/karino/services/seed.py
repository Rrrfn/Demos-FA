# -*- coding: utf-8 -*-
"""دانهٔ نمونهٔ آفلاین — فقط برای محیطی که هیچ منبع واقعی در دسترس نیست.

این داده‌ها **واقعی نیستند** و به‌عنوان آگهی زنده هم نمایش داده نمی‌شوند:
منبعشان ``seed`` است و در رابط با نشان «نمونهٔ آفلاین» و رنگ متفاوت می‌آید.
هدفش فقط این است که وقتی شبکهٔ خروجی بسته است، صفحه خالی و بی‌توضیح نماند.

در حالت عادی هرگز اجرا نمی‌شود: هم باید ``KARINO_SEED_DEMO=1`` باشد و هم
همهٔ منابع واقعی باید شکست خورده باشند.
"""
from __future__ import annotations

import time

from ..core.models import RawJob
from ..core.text import detect_engagement, search_key, strip_html

#: (عنوان، شرکت، شرح، برچسب‌ها، ساعت پیش، نوع همکاری)
_SAMPLES: tuple[tuple[str, str, str, tuple[str, ...], int, str], ...] = (
    ("برنامه‌نویس پایتون برای ساخت ربات تلگرام فروشگاهی", "فروشگاه آنلاین مهر",
     "به یک متخصص پایتون و بات تلگرام نیاز داریم. اتصال به درگاه پرداخت و دیتابیس "
     "MySQL. دورکاری کامل، قرارداد پروژه‌ای.",
     ("python", "telegram", "mysql", "rest api"), 4, "freelance"),
    ("جمع‌آوری قیمت محصولات از چند فروشگاه اینترنتی", "تیم داده پارس",
     "نیاز به اسکریپت پایتون برای استخراج دادهٔ چند سایت، خروجی اکسل و اجرای "
     "زمان‌بندی‌شدهٔ روزانه. آشنایی با requests و BeautifulSoup. پروژه‌ای و دورکاری.",
     ("python", "scraping", "excel", "automation"), 9, "freelance"),
    ("توسعه‌دهنده Django برای پنل مدیریت داخلی", "هلدینگ آرمان",
     "توسعهٔ وب‌اپلیکیشن با Django و PostgreSQL، طراحی REST API و پیاده‌سازی "
     "احراز هویت. حضور در دفتر تهران، تمام‌وقت.",
     ("django", "rest api", "postgres", "python"), 22, "fulltime"),
    ("دیتاآنالیست با پایتون و داشبورد مدیریتی", "شرکت سرمایه‌گذاری نو",
     "تحلیل دادهٔ فروش با pandas، ساخت داشبورد و گزارش ماهانه. دورکاری نسبی.",
     ("python", "pandas", "dashboard"), 27, "fulltime"),
    ("توسعهٔ چت‌بات پشتیبانی مشتریان", "اپلیکیشن سبدخرید",
     "چت‌بات فارسی برای پاسخ به پرسش‌های متداول و اتصال به سیستم تیکتینگ. "
     "تجربهٔ NLP یا رویکرد قاعده‌محور. پروژه‌ای.",
     ("python", "nlp", "chatbot", "llm"), 40, "freelance"),
    ("مهندس یادگیری ماشین — پیش‌بینی تقاضا", "زنجیره تأمین سبز",
     "پیاده‌سازی مدل پیش‌بینی فروش با scikit-learn، آماده‌سازی دیتاست و "
     "گزارش‌دهی شاخص‌های دقت. دورکاری کامل.",
     ("python", "machine learning", "sklearn", "pandas"), 63, "freelance"),
    ("ساخت API برای سرویس پیامکی", "پیام‌گستر رضوی",
     "طراحی REST API با Flask و SQLite، مستندات Swagger و تست واحد. امکان دورکاری.",
     ("python", "flask", "rest api", "sqlite"), 88, "freelance"),
    ("خودکارسازی ورود داده با Selenium", "بیمه آینده",
     "خودکارسازی فرم‌های تکراری اپراتورها با selenium، مستندسازی اسکریپت‌ها و "
     "گزارش خطا. پروژه‌ای دو هفته‌ای.",
     ("python", "automation", "selenium"), 110, "freelance"),
    ("توسعهٔ وب‌سایت شرکتی با HTML/CSS/JS", "مبلمان کوروش",
     "پیاده‌سازی سایت ریسپانسیو، انیمیشن اسکرول و بهینه‌سازی سرعت بارگذاری.",
     ("html", "css", "javascript", "responsive"), 150, "freelance"),
    ("کانتینرسازی و استقرار سرویس‌های پایتونی", "کلاد بوم",
     "Docker و CI/CD برای میکروسرویس‌ها، مانیتورینگ و لودبالانس. تمام‌وقت.",
     ("docker", "devops", "python", "ci/cd"), 190, "fulltime"),
)


def sample_jobs(*, now: int | None = None) -> list[RawJob]:
    """آگهی‌های نمونه با نشانهٔ صریح ``seed`` در شناسه و برچسب."""
    now = int(now if now is not None else time.time())
    jobs: list[RawJob] = []
    for index, (title, company, description, tags, hours_ago, employment) in enumerate(_SAMPLES, start=1):
        jobs.append(RawJob(
            source="seed",
            external_id=f"seed-{index:02d}",
            title=title,
            company=company,
            url="",
            description=strip_html(description),
            tags=list(tags) + ["نمونهٔ آفلاین"],
            location="ایران" if "دورکاری" not in description else "دورکاری",
            remote="دورکاری" in description,
            employment=employment or detect_engagement(search_key(description)),
            published_ts=now - hours_ago * 3600,
        ))
    return jobs
