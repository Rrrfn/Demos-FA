# -*- coding: utf-8 -*-
"""آزمون‌های پروفایل — مرزهای تطبیق مهارت و انتخاب نمونه‌کار.

تطبیق مهارت با الگوی زیررشته‌ای، امتیاز را بی‌دلیل بالا می‌برد («ai» داخل
«email»). اینجا همان مرزها قفل می‌شوند، چون یک خطای کوچک در این لایه به‌طور
مستقیم روی عدد نهایی همهٔ آگهی‌ها اثر می‌گذارد.
"""
from __future__ import annotations

from karino.core.text import search_key
from karino.profile import (CATEGORIES, PORTFOLIO, PORTFOLIO_BY_ID, SKILLS,
                            TOTAL_WEIGHT, fa_names, match_skills,
                            relevant_projects, skills_by_category)


# ---------------------------------------------------------------- ساختار پروفایل


def test_every_skill_is_well_formed():
    for key, spec in SKILLS.items():
        assert spec.key == key
        assert spec.fa and spec.category
        assert 1 <= spec.weight <= 10
        assert spec.patterns


def test_every_skill_category_has_a_persian_label():
    for spec in SKILLS.values():
        assert spec.category in CATEGORIES
        assert CATEGORIES[spec.category]


def test_total_weight_is_the_sum_of_skills():
    assert TOTAL_WEIGHT == sum(s.weight for s in SKILLS.values())


def test_portfolio_ids_are_unique_and_indexed():
    ids = [p.id for p in PORTFOLIO]
    assert len(ids) == len(set(ids))
    assert set(PORTFOLIO_BY_ID) == set(ids)


def test_portfolio_projects_only_reference_known_skills():
    """نمونه‌کار نمی‌تواند به مهارتی استناد کند که در پروفایل نیست."""
    for project in PORTFOLIO:
        assert project.skills
        assert set(project.skills) <= set(SKILLS)


# ---------------------------------------------------------------- تطبیق مهارت


def test_match_skills_finds_python_and_flask():
    matched, _ = match_skills(search_key("توسعه‌دهنده پایتون با Flask و SQLite"))
    assert {"python", "flask", "sql"} <= set(matched)


def test_sql_matches_database_names_not_the_bare_word():
    """پروفایل نام رسمی دیتابیس‌ها را می‌شناسد، نه فقط یک «sql» بی‌بافت."""
    for text in ("MySQL", "PostgreSQL", "sqlite3", "دیتابیس فروشگاهی"):
        matched, _ = match_skills(search_key(text))
        assert "sql" in matched, text


def test_plural_apis_matches_the_rest_skill():
    """«REST APIs» رایج‌ترین شکل نوشتن این نیاز است و باید شناسایی شود."""
    for text in ("Develop REST APIs", "طراحی API", "RESTful service"):
        matched, _ = match_skills(search_key(text))
        assert "rest_api" in matched, text


def test_match_skills_returns_every_skill_as_matched_or_missing():
    matched, missing = match_skills(search_key("python flask"))
    assert set(matched) | set(missing) == set(SKILLS)
    assert not set(matched) & set(missing)


def test_latin_patterns_respect_word_boundaries():
    """«ai» نباید داخل «email» پیدا شود — وگرنه امتیاز دروغین ساخته می‌شود."""
    matched, _ = match_skills(search_key("کارشناس ایمیل مارکتینگ"))
    assert "llm" not in matched

    matched_standalone, _ = match_skills(search_key("ai engineer for chatbot"))
    assert "llm" in matched_standalone


def test_persian_patterns_still_match_substrings():
    """فارسی فاصله‌گذاری مبهم دارد؛ تطبیق زیررشته‌ای درست است."""
    for text, key in (("وب‌اسکرپینگ", "scraping"),
                      ("اتوماسیون اداری", "automation"),
                      ("ربات تلگرام فروشگاهی", "telegram_bot")):
        matched, _ = match_skills(search_key(text))
        assert key in matched, text


def test_match_skills_on_empty_text_matches_nothing():
    matched, missing = match_skills("")
    assert matched == []
    assert set(missing) == set(SKILLS)


# ---------------------------------------------------------------- نمایش


def test_fa_names_preserves_order_and_skips_unknown():
    assert fa_names(["python", "nope", "flask"]) == ["پایتون", "Flask"]


def test_fa_names_honours_limit():
    assert len(fa_names(list(SKILLS), 3)) == 3


def test_skills_by_category_groups_and_skips_unknown():
    grouped = skills_by_category(["python", "pandas", "unknown_key"])
    assert "پایتون" in grouped["backend"]
    assert "تحلیل داده (pandas)" in grouped["data"]
    assert all("unknown_key" not in values for values in grouped.values())


# ---------------------------------------------------------------- انتخاب نمونه‌کار


def test_relevant_projects_ranks_by_overlap():
    """قوی‌ترین هم‌پوشانی اول می‌آید و پروژهٔ بی‌ربط کلاً نمی‌آید."""
    projects = relevant_projects(["python", "flask", "nlp"])
    assert projects
    assert {p.id for p in projects[:2]} == {"support", "karino"}   # سه مهارت مشترک
    assert "parfum" not in {p.id for p in projects}


def test_relevant_projects_returns_nothing_for_unknown_skills():
    assert relevant_projects([]) == []
    assert relevant_projects(["key_that_does_not_exist"]) == []


def test_relevant_projects_order_is_stable_across_calls():
    first = [p.id for p in relevant_projects(["python", "automation", "excel"])]
    second = [p.id for p in relevant_projects(["python", "automation", "excel"])]
    assert first == second


def test_relevant_projects_respects_limit():
    assert len(relevant_projects(["python", "flask", "sql", "nlp"], limit=2)) == 2


def test_relevant_projects_never_invents_projects():
    projects = relevant_projects(["python", "flask"])
    assert all(project in PORTFOLIO for project in projects)
