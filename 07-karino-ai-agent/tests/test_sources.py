# -*- coding: utf-8 -*-
"""آزمون‌های لایهٔ منابع — مقاومت شبکه، هر کانکتور، و ورودی خراب.

تمرکز اصلی روی حالت‌های شکست است: پاسخ خراب، فید خالی، کد ۴۰۳، و متن
غیر-JSON. این‌ها همان چیزهایی هستند که در عمل پیش می‌آیند و اگر مدیریت
نشوند، خط لوله را می‌خوابانند.
"""
from __future__ import annotations

import pytest

from karino.core.errors import SourceError
from karino.sources import (ArbeitnowSource, CustomFeedSource,
                            HackersNewsJobsSource, HttpClient, JobVisionSource,
                            RemoteOKSource, RemotiveSource, WeWorkRemotelySource,
                            build_sources)
from karino.sources.base import SourceConnector

from .fakes import (FakeTransport, arbeitnow_payload, remoteok_payload,
                    remotive_payload, rss_feed)


# ---------------------------------------------------------------- کلاینت


def test_client_retries_then_succeeds(settings):
    """دو شکست شبکه، سپس موفقیت — با عقب‌نشینی و بدون بالا آوردن خطا."""
    transport = FakeTransport().add("example.com", rss_feed([{"title": "x"}])).fail("example.com", 2)
    client = HttpClient(timeout=2, retries=3, backoff=0.0, transport=transport)

    raw = client.get("https://example.com/feed")
    assert b"<rss" in raw
    assert len(transport.calls) == 3


def test_client_gives_up_after_retries(settings):
    """شکست ماندگار باید ``SourceError`` بدهد، نه استثنای خام شبکه."""
    transport = FakeTransport().add("example.com", b"ok").fail("example.com", 99)
    client = HttpClient(timeout=2, retries=2, backoff=0.0, transport=transport)

    with pytest.raises(SourceError) as excinfo:
        client.get("https://example.com/feed")
    assert "detail" in excinfo.value.to_dict()
    assert len(transport.calls) == 3          # ۱ تلاش + ۲ تکرار


def test_client_does_not_retry_client_errors(settings):
    """کد ۴۰۳ تلاش مجدد را توجیه نمی‌کند — باید بی‌درنگ خطا بدهد."""
    transport = FakeTransport().add("blocked.example", b"no", status=403)
    client = HttpClient(timeout=2, retries=3, backoff=0.0, transport=transport)

    with pytest.raises(SourceError):
        client.get("https://blocked.example/feed")
    assert len(transport.calls) == 1


def test_client_reports_non_json(settings):
    transport = FakeTransport().add("api.example", b"<html>not json</html>")
    client = HttpClient(timeout=2, retries=0, backoff=0.0, transport=transport)

    with pytest.raises(SourceError) as excinfo:
        client.get_json("https://api.example/x")
    assert "JSON" in excinfo.value.message


# ---------------------------------------------------------------- کانکتورهای RSS


def test_jobvision_parses_persian_feed(settings):
    transport = FakeTransport().add("jobvision", rss_feed([
        {"title": "برنامه‌نویس پایتون", "guid": "v1", "link": "https://jobvision.ir/jobs/1",
         "summary": "دورکاری با Flask", "author": "شرکت الف"},
    ]))
    source = JobVisionSource(client=HttpClient(transport=transport))
    jobs = source.fetch()

    assert len(jobs) == 1
    assert jobs[0].source == "jobvision"
    assert "پایتون" in jobs[0].title
    assert jobs[0].external_id == "v1"


def test_empty_feed_returns_no_jobs(settings):
    """فید معتبر ولی خالی خطا نیست؛ منبع با صفر آگهی سالم است."""
    transport = FakeTransport().add("jobvision", rss_feed([]))
    jobs = JobVisionSource(client=HttpClient(transport=transport)).fetch()
    assert jobs == []


def test_malformed_feed_raises_source_error(settings):
    """پاسخ غیر XML باید ``SourceError`` بدهد، نه استثنای کتابخانهٔ فید."""
    transport = FakeTransport().add("jobvision", b"this is not xml at all")
    source = JobVisionSource(client=HttpClient(transport=transport, retries=0))

    with pytest.raises(SourceError) as excinfo:
        source.fetch()
    assert "فید" in str(excinfo.value) or "خواندن" in str(excinfo.value)


def test_weworkremotely_splits_company_from_title(settings):
    transport = FakeTransport().add("weworkremotely", rss_feed([
        {"title": "Acme Corp: Backend Engineer", "guid": "w1", "author": ""},
    ]))
    jobs = WeWorkRemotelySource(client=HttpClient(transport=transport)).fetch()
    assert jobs[0].company == "Acme Corp"
    assert jobs[0].title == "Acme Corp: Backend Engineer"


def test_hn_hiring_connector(settings):
    transport = FakeTransport().add("hnrss.org", rss_feed([
        {"title": "Zep AI Is Hiring a Head of Engineering", "guid": "h1"},
    ]))
    jobs = HackersNewsJobsSource(client=HttpClient(transport=transport)).fetch()
    assert len(jobs) == 1
    assert jobs[0].source == "hn_hiring"


# ---------------------------------------------------------------- کانکتورهای JSON


def test_remotive_parses_and_extracts_salary(settings):
    transport = FakeTransport().add("remotive.com", remotive_payload([
        {"id": 11, "title": "Python Developer", "company_name": "Acme",
         "url": "https://remotive.com/jobs/11", "description": "<p>Build APIs</p>",
         "tags": ["python"], "category": "Software Development",
         "job_type": "full_time", "publication_date": "2026-09-08T10:00:00",
         "candidate_required_location": "Worldwide", "salary": "OTE $25k - $35k"},
    ]))
    jobs = RemotiveSource(client=HttpClient(transport=transport)).fetch()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.company == "Acme"
    assert job.remote is True
    assert job.published_ts is not None
    assert job.salary_min == 25000 and job.salary_max == 35000
    assert "Software Development" in job.tags
    assert "<p>" not in job.description          # HTML پاک شده


def test_remotive_rejects_unexpected_shape(settings):
    transport = FakeTransport().add("remotive.com", b'{"unexpected": true}')
    with pytest.raises(SourceError):
        RemotiveSource(client=HttpClient(transport=transport, retries=0)).fetch()


def test_remoteok_skips_legal_notice_and_reads_salary(settings):
    """عنصر نخست RemoteOK اطلاعیهٔ حقوقی است و نباید آگهی شمرده شود."""
    transport = FakeTransport().add("remoteok.com", remoteok_payload([
        {"id": 7, "position": "Senior Python Engineer", "company": "Acme",
         "tags": ["python"], "location": "", "salary_min": 90000,
         "salary_max": 120000, "epoch": 1_789_000_000,
         "apply_url": "https://remoteok.com/7", "description": "APIs"},
    ]))
    jobs = RemoteOKSource(client=HttpClient(transport=transport)).fetch()

    assert len(jobs) == 1
    assert jobs[0].title == "Senior Python Engineer"
    assert jobs[0].salary_min == 90000
    assert "legal" not in jobs[0].title.lower()


def test_remoteok_ignores_records_without_title(settings):
    transport = FakeTransport().add("remoteok.com", remoteok_payload([
        {"id": 8, "company": "No Title Inc", "tags": []},
        {"id": 9, "position": "Valid Job", "company": "Acme", "tags": [], "epoch": 1_789_000_000},
    ]))
    jobs = RemoteOKSource(client=HttpClient(transport=transport)).fetch()
    assert [j.title for j in jobs] == ["Valid Job"]


def test_arbeitnow_parses_remote_flag_and_epoch(settings):
    transport = FakeTransport().add("arbeitnow.com", arbeitnow_payload([
        {"slug": "a-1", "title": "Data Engineer", "company_name": "Beta GmbH",
         "description": "ETL pipelines", "remote": True, "tags": ["Data"],
         "job_types": ["full_time"], "location": "Berlin", "created_at": 1_789_000_000,
         "url": "https://arbeitnow.com/a-1"},
    ]))
    jobs = ArbeitnowSource(client=HttpClient(transport=transport)).fetch()

    assert jobs[0].remote is True
    assert jobs[0].location == "Berlin"
    assert jobs[0].employment == "full_time"
    assert jobs[0].published_ts == 1_789_000_000


def test_arbeitnow_millisecond_timestamp_normalized(settings):
    """برخی منابع زمان را میلی‌ثانیه می‌دهند؛ باید به ثانیه برگردد."""
    transport = FakeTransport().add("arbeitnow.com", arbeitnow_payload([
        {"slug": "a-2", "title": "Job", "created_at": 1_789_000_000_000},
    ]))
    jobs = ArbeitnowSource(client=HttpClient(transport=transport)).fetch()
    assert jobs[0].published_ts == 1_789_000_000


# ---------------------------------------------------------------- فیدهای دلخواه


def test_custom_feeds_merge_multiple_sources(settings):
    transport = (FakeTransport()
                 .add("feed-one.example", rss_feed([{"title": "Job A", "guid": "a"}]))
                 .add("feed-two.example", rss_feed([{"title": "Job B", "guid": "b"}])))
    source = CustomFeedSource(["https://feed-one.example/rss", "https://feed-two.example/rss"],
                              client=HttpClient(transport=transport))
    jobs = source.fetch()

    assert {j.title for j in jobs} == {"Job A", "Job B"}
    # شناسه‌ها بین دو فید قاطی نمی‌شوند
    assert len({j.external_id for j in jobs}) == 2


def test_custom_feed_one_bad_feed_does_not_kill_others(settings):
    """یک فید خراب نباید فیدهای سالم دیگر را از کار بیندازد."""
    transport = (FakeTransport()
                 .add("good.example", rss_feed([{"title": "Healthy Job", "guid": "g"}]))
                 .add("bad.example", b"not xml"))
    source = CustomFeedSource(["https://bad.example/rss", "https://good.example/rss"],
                              client=HttpClient(transport=transport, retries=0))
    jobs = source.fetch()

    assert [j.title for j in jobs] == ["Healthy Job"]


def test_custom_feed_all_broken_raises(settings):
    transport = FakeTransport().add("bad.example", b"not xml")
    source = CustomFeedSource(["https://bad.example/rss"],
                              client=HttpClient(transport=transport, retries=0))
    with pytest.raises(SourceError):
        source.fetch()


# ---------------------------------------------------------------- ساخت منابع


def test_build_sources_default_includes_all_registry(settings):
    keys = [s.key for s in build_sources(settings)]
    assert "jobvision" in keys and "remotive" in keys and "remoteok" in keys
    assert "hn_hiring" in keys
    assert len(keys) == 6


def test_build_sources_respects_selection_and_ignores_unknown(settings):
    from dataclasses import replace

    tuned = replace(settings, enabled_sources=["jobvision", "not_a_source"])
    keys = [s.key for s in build_sources(tuned)]
    assert keys == ["jobvision"]


def test_build_sources_adds_custom_feeds_when_configured(settings):
    from dataclasses import replace

    tuned = replace(settings, enabled_sources=["jobvision"],
                    extra_feeds=["https://example.com/rss"])
    keys = [s.key for s in build_sources(tuned)]
    assert "custom_feeds" in keys


def test_every_connector_declares_identity(settings):
    """هر کانکتور باید کلید، برچسب و نوع داشته باشد — پیش‌شرط گزارش منابع."""
    for cls in (JobVisionSource, RemotiveSource, RemoteOKSource, ArbeitnowSource,
                WeWorkRemotelySource, HackersNewsJobsSource):
        instance = cls(client=HttpClient(transport=FakeTransport()))
        assert instance.key and instance.label and instance.kind
        assert isinstance(instance, SourceConnector)
