# -*- coding: utf-8 -*-
"""آزمون‌های چرخهٔ عمر اپ — راه‌اندازی یک‌بارهٔ پروسه و سطح فرمان خط فرمان.

این ماژول یک ``app`` سطح ماژول برای WSGI می‌سازد و ``python -m karino serve``
هم اپ خودش را. اگر محافظ راه‌اندازی در سطح اپ باشد، یک اجرای توسعه دو بار
پایگاه داده می‌سازد، دو بار جمع‌آوری می‌کند و دو ردیف «راه‌اندازی» می‌گذارد.
"""
from __future__ import annotations

from dataclasses import replace

from karino.storage import activity


def boots() -> list[dict]:
    return [event for event in activity.grouped(limit=50) if event["kind"] == "boot"]


def test_bootstrap_runs_once_per_process(settings, db):
    from karino import webapp

    tuned = replace(settings, collect_on_boot=False, enable_scheduler=False)
    webapp.reset_bootstrap_flag()
    activity.clear()          # فقط ردیف‌های همین دو فراخوانی شمرده شوند

    first = webapp.create_app(bootstrap=True, start_scheduler=False, settings=tuned)
    second = webapp.create_app(bootstrap=True, start_scheduler=False, settings=tuned)

    assert len(boots()) == 1

    # اپ دوم هم باید کامل کار کند، نه اینکه نیمه‌ساخته بماند
    for app in (first, second):
        app.config["TESTING"] = True
        with app.test_client() as client:
            assert client.get("/health").get_json()["status"] == "ok"


def test_scheduler_is_not_started_when_disabled(settings, db):
    from karino import webapp
    from karino import scheduler

    tuned = replace(settings, collect_on_boot=False, enable_scheduler=False)
    webapp.reset_bootstrap_flag()
    webapp.create_app(bootstrap=True, start_scheduler=False, settings=tuned)

    assert scheduler.is_running() is False


def test_cli_exposes_the_documented_commands():
    from karino.__main__ import build_parser

    for argv in (["check"], ["ingest"], ["serve", "--no-scheduler"]):
        args = build_parser().parse_args(argv)
        assert callable(args.func)

    # در نبود زیرفرمان، سرو باید اجرا شود
    default = build_parser().parse_args([])
    assert default.command is None
    assert default.func is not None
    assert default.scheduler is True


def test_serve_reuses_the_wsgi_app(settings, db, monkeypatch):
    """``serve`` نباید اپ دومی بسازد که محافظ راه‌اندازی را دور بزند."""
    from karino import __main__ as cli
    from karino import webapp

    created = {"calls": 0}
    real_create = webapp.create_app

    def counting_create(*args, **kwargs):
        created["calls"] += 1
        return real_create(*args, **kwargs)

    monkeypatch.setattr(webapp, "create_app", counting_create)

    ran = {}

    class _Stop(Exception):
        pass

    def fake_run(self, **kwargs):
        ran["kwargs"] = kwargs
        raise _Stop

    monkeypatch.setattr("flask.Flask.run", fake_run)

    args = cli.build_parser().parse_args(["serve", "--port", "8199", "--no-scheduler"])
    try:
        cli.cmd_serve(args)
    except _Stop:
        pass

    assert created["calls"] == 0              # اپ تازه‌ای ساخته نشد
    assert ran["kwargs"]["port"] == 8199
    assert ran["kwargs"]["use_reloader"] is False
