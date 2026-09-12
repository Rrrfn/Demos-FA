# -*- coding: utf-8 -*-
"""سیستم طراحی — پوستهٔ «آژانس املاک لوکس» روی Streamlit.

Streamlit به‌صورت پیش‌فرض ظاهر یک داشبورد خام دارد. این ماژول با CSS یک زبان
بصری منسجم می‌سازد: کاغذ کرم، مرکب تیره، یک لهجهٔ برنزی، و تایپوگرافی با
سلسله‌مراتب روشن. همهٔ اجزا از متغیرهای همین‌جا رنگ می‌گیرند تا هیچ‌جا رنگ
سرخود تعریف نشود و ظاهر یکدست بماند.

قلم‌ها داخل ``static/fonts`` هستند و از همان مسیر سرو می‌شوند؛ هیچ درخواستی به
سرویس بیرونی زده نمی‌شود.
"""
from __future__ import annotations

import streamlit as st

FONT_DIR = "/app/static/fonts"

#: پالت. نام‌ها فارسی‌اند تا در ادامهٔ کد معلوم باشد هر رنگ کجاست.
PALETTE = {
    "ink": "#12100E",
    "ink_soft": "#3C362F",
    "muted": "#6F675C",
    "line": "#E6DED1",
    "ivory": "#FAF7F2",
    "white": "#FFFFFF",
    "bronze": "#A8854E",
    "bronze_dark": "#8A6B3B",
    "bronze_soft": "#F4EBDC",
    "up": "#2F6B4F",
    "down": "#A4453A",
}

#: رنگ نمودارها — هم‌خانواده با پالت، نه رنگ‌های اشباع پیش‌فرض.
CHART_COLORS = {
    "bronze": "#A8854E",
    "ink": "#3C362F",
    "muted": "#B9AE9C",
    "up": "#2F6B4F",
    "down": "#A4453A",
    "grid": "#EAE3D8",
}

FONT_FACE = "\n".join(
    f"""@font-face {{
  font-family: 'Vazirmatn';
  src: url('{FONT_DIR}/Vazirmatn-{weight}.woff2') format('woff2');
  font-weight: {css_weight};
  font-display: swap;
}}"""
    for weight, css_weight in (("Regular", 400), ("Bold", 700), ("Black", 900))
)


def css() -> str:
    """کل CSS رابط."""
    p = PALETTE
    return f"""
<style>
{FONT_FACE}

:root {{
  --ink: {p['ink']};
  --ink-soft: {p['ink_soft']};
  --muted: {p['muted']};
  --line: {p['line']};
  --ivory: {p['ivory']};
  --white: {p['white']};
  --bronze: {p['bronze']};
  --bronze-dark: {p['bronze_dark']};
  --bronze-soft: {p['bronze_soft']};
  --up: {p['up']};
  --down: {p['down']};
  --shadow: 0 1px 2px rgba(18,16,14,.04), 0 14px 30px -22px rgba(18,16,14,.45);
  --radius: 14px;
}}

/* ــ پایه ــ */
html, body, [class*="css"] {{
  font-family: 'Vazirmatn', -apple-system, 'Segoe UI', sans-serif;
}}
.stApp {{ background: var(--ivory); }}
.block-container {{
  padding-top: 2.2rem; padding-bottom: 4rem;
  max-width: 1180px; direction: rtl;
}}
[data-testid="stSidebar"] {{ background: var(--white); border-left: 1px solid var(--line); }}
[data-testid="stSidebar"] .block-container {{ padding-top: 1.4rem; }}
header[data-testid="stHeader"] {{ background: transparent; height: 0; }}
#MainMenu, footer {{ visibility: hidden; }}

h1, h2, h3, h4 {{ font-family: 'Vazirmatn', sans-serif; color: var(--ink); letter-spacing: -.01em; }}
h1 {{ font-weight: 900; font-size: 2.35rem; line-height: 1.25; margin: 0 0 .35rem; }}
h2 {{ font-weight: 900; font-size: 1.55rem; margin: 1.4rem 0 .5rem; }}
h3 {{ font-weight: 700; font-size: 1.14rem; margin: 0 0 .4rem; }}
p, li, label, .stMarkdown {{ color: var(--ink-soft); line-height: 1.85; font-size: .95rem; }}
a {{ color: var(--bronze-dark); text-decoration: none; }}
a:hover {{ color: var(--bronze); }}

/* ــ اجزای تایپوگرافی ــ */
.kh-eyebrow {{
  font-size: .7rem; font-weight: 700; letter-spacing: .18em;
  text-transform: uppercase; color: var(--bronze-dark);
  display: block; margin-bottom: .5rem;
}}
.kh-serif {{ font-family: Georgia, 'Times New Roman', serif; letter-spacing: .12em; }}
.kh-lead {{ font-size: 1.02rem; color: var(--muted); line-height: 1.95; max-width: 62ch; }}
.kh-muted {{ color: var(--muted); font-size: .86rem; }}
.kh-rule {{ height: 1px; background: var(--line); border: 0; margin: 1.6rem 0; }}
.kh-hr-tight {{ margin: .9rem 0; }}

/* ــ برچسب‌ها ــ */
.kh-badge {{
  display: inline-block; padding: .22rem .6rem; border-radius: 999px;
  font-size: .72rem; font-weight: 700; line-height: 1.6;
  border: 1px solid var(--line); color: var(--ink-soft); background: var(--white);
}}
.kh-badge-bronze {{ background: var(--bronze-soft); border-color: #E3D3B6; color: var(--bronze-dark); }}
.kh-badge-up {{ background: #EAF2ED; border-color: #CFE2D6; color: var(--up); }}
.kh-badge-down {{ background: #F7ECEA; border-color: #EBD6D2; color: var(--down); }}
.kh-badge-ink {{ background: var(--ink); border-color: var(--ink); color: #F6F1E6; }}
.kh-badges {{ display: flex; flex-wrap: wrap; gap: .35rem; }}

/* ــ کارت ملک ــ */
.kh-card {{
  background: var(--white); border: 1px solid var(--line); border-radius: var(--radius);
  overflow: hidden; height: 100%; display: flex; flex-direction: column;
  transition: box-shadow .22s ease, transform .22s ease, border-color .22s ease;
}}
.kh-card:hover {{
  box-shadow: var(--shadow); transform: translateY(-3px); border-color: #D9CDB9;
}}
.kh-card-link {{ display: block; color: inherit; text-decoration: none; }}
.kh-card-link:hover {{ color: inherit; }}
.kh-card-more {{ font-size: .78rem; color: var(--bronze-dark); font-weight: 700; }}
.kh-card-media {{ position: relative; background: var(--bronze-soft); }}
.kh-card-media img {{ width: 100%; height: 208px; object-fit: cover; display: block; }}
.kh-card-media .kh-card-tag {{
  position: absolute; top: .6rem; inset-inline-start: .6rem;
  background: rgba(18,16,14,.78); color: #F6F1E6; border: 0;
  padding: .2rem .55rem; border-radius: 999px; font-size: .7rem; font-weight: 700;
}}
.kh-card-body {{ padding: .95rem 1.05rem 1.1rem; display: flex; flex-direction: column; gap: .5rem; flex: 1; }}
.kh-card-title {{ font-size: 1rem; font-weight: 700; color: var(--ink); line-height: 1.6; margin: 0; }}
.kh-card-meta {{ color: var(--muted); font-size: .82rem; }}
.kh-card-price {{ font-size: 1.16rem; font-weight: 900; color: var(--ink); margin-top: auto; }}
.kh-card-unit {{ font-size: .8rem; color: var(--muted); font-weight: 400; }}

/* ــ شاخص‌ها ــ */
.kh-kpi {{
  background: var(--white); border: 1px solid var(--line); border-radius: var(--radius);
  padding: .95rem 1.05rem; height: 100%;
}}
.kh-kpi-label {{ font-size: .74rem; color: var(--muted); font-weight: 700; letter-spacing: .04em; }}
.kh-kpi-value {{ font-size: 1.5rem; font-weight: 900; color: var(--ink); margin: .25rem 0 .1rem; }}
.kh-kpi-note {{ font-size: .76rem; color: var(--muted); }}

/* ــ قهرمان صفحهٔ خانه ــ */
.kh-hero {{
  position: relative; border-radius: 18px; overflow: hidden;
  border: 1px solid var(--line); background: var(--ink);
  min-height: 340px; display: flex; align-items: flex-end;
}}
.kh-hero img {{ position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; opacity: .5; }}
.kh-hero-veil {{
  position: absolute; inset: 0;
  background: linear-gradient(90deg, rgba(18,16,14,.9) 12%, rgba(18,16,14,.35) 100%);
}}
.kh-hero-body {{ position: relative; padding: 2.2rem 2rem; max-width: 46rem; }}
.kh-hero-body h1 {{ color: #FBF8F1; font-size: 2.5rem; margin-bottom: .5rem; }}
.kh-hero-body p {{ color: #D9D0C1; font-size: 1rem; line-height: 1.95; margin: 0; }}
.kh-hero-body .kh-eyebrow {{ color: #D8C29A; }}

/* ــ قیمت بزرگ (صفحهٔ برآورد) ــ */
.kh-price-hero {{
  background: var(--white); border: 1px solid var(--line);
  border-radius: var(--radius); padding: 1.4rem 1.5rem;
}}
.kh-price-value {{ font-size: 2.15rem; font-weight: 900; color: var(--ink); line-height: 1.3; }}
.kh-price-sub {{ color: var(--muted); font-size: .9rem; margin-top: .2rem; }}
.kh-band {{
  margin-top: .9rem; padding-top: .8rem; border-top: 1px dashed var(--line);
  color: var(--ink-soft); font-size: .88rem;
}}

/* ــ گالری ــ */
.kh-gallery {{ display: grid; grid-template-columns: 2fr 1fr; gap: .5rem; }}
.kh-gallery img {{ width: 100%; height: 100%; object-fit: cover; border-radius: 12px; display: block; }}
.kh-gallery-main {{ grid-row: span 2; }}
.kh-gallery-main img {{ height: 420px; }}
.kh-gallery-side img {{ height: 206px; }}

/* ــ جدول مشخصات ــ */
.kh-specs {{ width: 100%; border-collapse: collapse; font-size: .9rem; }}
.kh-specs td {{ padding: .6rem .2rem; border-bottom: 1px solid var(--line); }}
.kh-specs td:first-child {{ color: var(--muted); width: 42%; }}
.kh-specs td:last-child {{ color: var(--ink); font-weight: 700; }}

/* ــ عوامل اثرگذار ــ */
.kh-factor {{ display: grid; grid-template-columns: 1fr auto; gap: .3rem .8rem; margin-bottom: .55rem; }}
.kh-factor-head {{ display: flex; justify-content: space-between; font-size: .86rem; }}
.kh-factor-name {{ color: var(--ink-soft); }}
.kh-factor-amount {{ font-weight: 700; font-variant-numeric: tabular-nums; }}
.kh-factor-amount.up {{ color: var(--up); }}
.kh-factor-amount.down {{ color: var(--down); }}
.kh-bar {{ grid-column: 1 / -1; height: 6px; background: #EFE9DF; border-radius: 99px; overflow: hidden; }}
.kh-bar span {{ display: block; height: 100%; border-radius: 99px; }}
.kh-bar span.up {{ background: var(--bronze); }}
.kh-bar span.down {{ background: var(--down); }}

/* ــ سایر ــ */
.kh-note {{
  background: var(--bronze-soft); border: 1px solid #E7DAC1;
  border-radius: 12px; padding: .8rem 1rem; font-size: .85rem; color: #6B573A;
}}
.kh-warn {{
  background: #FBF3E6; border: 1px solid #EBD9B4; border-radius: 12px;
  padding: .8rem 1rem; font-size: .85rem; color: #6B5528;
}}
.kh-empty {{
  border: 1px dashed var(--line); border-radius: var(--radius); background: var(--white);
  padding: 2.2rem 1.2rem; text-align: center; color: var(--muted);
}}

/* ــ ویجت‌های Streamlit ــ */
.stButton > button {{
  border-radius: 10px; border: 1px solid var(--ink); background: var(--ink);
  color: #F8F4EC; font-weight: 700; font-family: 'Vazirmatn', sans-serif;
  padding: .45rem 1rem; transition: background .18s ease, color .18s ease;
}}
.stButton > button:hover {{ background: var(--bronze-dark); border-color: var(--bronze-dark); color: #FFF; }}
.stButton > button[kind="secondary"] {{ background: transparent; color: var(--ink); }}
.stButton > button[kind="secondary"]:hover {{ background: var(--bronze-soft); color: var(--bronze-dark); border-color: var(--bronze); }}
[data-testid="stSidebarNav"] {{ display: none; }}
[data-testid="stSidebar"] a {{ color: var(--ink-soft); }}
[data-testid="stSidebar"] a:hover {{ color: var(--bronze-dark); }}
div[data-baseweb="select"] > div, .stTextInput input, .stNumberInput input {{
  border-radius: 10px; border-color: var(--line); background: var(--white);
}}
.stSlider [data-baseweb="slider"] div[role="slider"] {{ background: var(--bronze); }}
.stTabs [data-baseweb="tab-list"] {{ gap: .4rem; border-bottom: 1px solid var(--line); }}
.stTabs [data-baseweb="tab"] {{ font-family: 'Vazirmatn', sans-serif; font-weight: 700; color: var(--muted); }}
.stTabs [aria-selected="true"] {{ color: var(--ink); }}
[data-testid="stMetricValue"] {{ font-family: 'Vazirmatn', sans-serif; font-weight: 900; color: var(--ink); }}
[data-testid="stDataFrame"] {{ border: 1px solid var(--line); border-radius: 12px; }}

/* ــ موبایل ــ */
@media (max-width: 900px) {{
  .block-container {{ padding-left: 1rem; padding-right: 1rem; }}
  h1 {{ font-size: 1.85rem; }}
  .kh-hero {{ min-height: 280px; }}
  .kh-hero-body {{ padding: 1.4rem 1.1rem; }}
  .kh-hero-body h1 {{ font-size: 1.7rem; }}
  .kh-gallery {{ grid-template-columns: 1fr; }}
  .kh-gallery-main {{ grid-row: auto; }}
  .kh-gallery-main img, .kh-gallery-side img {{ height: 220px; }}
  .kh-card-media img {{ height: 180px; }}
  .kh-price-value {{ font-size: 1.6rem; }}
}}
</style>
"""


def inject() -> None:
    """افزودن پوسته به صفحه. در هر اجرا یک بار صدا زده می‌شود."""
    st.markdown(css(), unsafe_allow_html=True)
