# -*- coding: utf-8 -*-
"""آزمون کتابخانهٔ عکس — انتساب پایدار، اعتبار و نبود آرشیو."""
from __future__ import annotations

import json
import os

import pytest

from khoneyab import photos as ph


@pytest.fixture()
def empty_library(env):
    """آرشیو خالی — حالت پیش از دانلود عکس‌ها."""
    saved = ph.MANIFEST_PATH
    ph.MANIFEST_PATH = os.path.join(str(env["photo_dir"]), "absent.json")
    library = ph.PhotoLibrary()
    yield library
    ph.MANIFEST_PATH = saved


@pytest.fixture()
def library(env):
    """آرشیو نمونه با دو نما و دو عکس داخلی."""
    manifest = [
        {"file": "exterior-01-a.jpg", "kind": "exterior", "title": "نمای مدرن",
         "provider": "Wikimedia Commons", "license": "CC BY 4.0",
         "author": "A. Photographer", "landing": "https://example.org/1",
         "source_url": "https://example.org/1.jpg"},
        {"file": "exterior-02-b.jpg", "kind": "exterior", "title": "ویلا",
         "provider": "Wikimedia Commons", "license": "CC BY-SA 4.0",
         "author": "B. Photographer", "landing": "https://example.org/2",
         "source_url": "https://example.org/2.jpg"},
        {"file": "interior-03-c.jpg", "kind": "interior", "title": "نشیمن",
         "provider": "Wikimedia Commons", "license": "CC0", "author": "",
         "landing": "https://example.org/3", "source_url": "https://example.org/3.jpg"},
        {"file": "interior-04-d.jpg", "kind": "interior", "title": "آشپزخانه",
         "provider": "Wikimedia Commons", "license": "CC BY 4.0",
         "author": "D. Photographer", "landing": "https://example.org/4",
         "source_url": "https://example.org/4.jpg"},
    ]
    for entry in manifest:                      # فایل‌ها باید واقعاً وجود داشته باشند
        with open(os.path.join(str(env["photo_dir"]), entry["file"]), "wb") as handle:
            handle.write(b"\xff\xd8\xff\xe0" + entry["file"].encode())

    # نام فایل عمداً `manifest.json` نیست: بقیهٔ آزمون‌ها با همان نام پیش‌فرض
    # `PhotoLibrary()` می‌سازند و اگر اینجا آن نام را بنویسیم، فهرست ساختگی
    # به آزمون‌های بعدی نشت می‌کند.
    manifest_path = os.path.join(str(env["photo_dir"]), "library-fixture.json")
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False)

    saved = ph.MANIFEST_PATH
    ph.MANIFEST_PATH = manifest_path
    try:
        yield ph.PhotoLibrary(manifest)
    finally:
        ph.MANIFEST_PATH = saved
        if os.path.exists(manifest_path):
            os.remove(manifest_path)
        for entry in manifest:
            leftover = os.path.join(str(env["photo_dir"]), entry["file"])
            if os.path.exists(leftover):
                os.remove(leftover)


def test_missing_archive_is_reported_honestly(empty_library):
    assert empty_library.is_empty
    assert empty_library.total == 0
    assert empty_library.cover(0) is None
    assert empty_library.gallery(0) == ()
    assert empty_library.credit(None) == {}


def test_entries_are_split_by_kind(library):
    assert library.total == 4
    assert library.exteriors_count == 2
    assert library.interiors_count == 2
    assert not library.is_empty


def test_assignment_is_stable_for_a_listing(env, library):
    """یک آگهی همیشه همان عکس را می‌گیرد — انتساب نباید تصادفی بپرد."""
    for index in (0, 1, 5, 42):
        assert library.cover(index) == library.cover(index)
        assert library.gallery(index) == library.gallery(index)


def test_exteriors_are_used_as_cover(library):
    assert library.cover(0) in library.exteriors
    assert library.cover(1) in library.exteriors
    assert library.cover(2) == library.cover(0)      # چرخش روی استخر


def test_gallery_has_no_repeats(library):
    for index in range(12):
        gallery = library.gallery(index, size=3)
        assert len(gallery) <= 3
        assert len(set(gallery)) == len(gallery)
        assert gallery[0] == library.cover(index)


def test_gallery_falls_back_to_exteriors_without_interiors(env):
    entries = [entry for entry in library_entries(env) if entry["kind"] == "exterior"]
    fallback = ph.PhotoLibrary(entries)
    gallery = fallback.gallery(0, size=3)
    assert gallery
    assert all(name in fallback.exteriors for name in gallery)


def test_credit_lookup(library):
    credit = library.credit("exterior-01-a.jpg")
    assert credit["license"] == "CC BY 4.0"
    assert credit["author"] == "A. Photographer"
    assert library.credit("nope.jpg") == {}


def test_photo_url_is_absolute(env):
    url = ph.photo_url("exterior-01-a.jpg")
    assert url.startswith("/")                       # مسیر نسبی در صفحهٔ تودرتو می‌شکند
    assert url.endswith("exterior-01-a.jpg")
    assert ph.photo_url(None) == ""


def test_manifest_filters_missing_files(env, tmp_path):
    """ردیفی که فایلش نیست نباید در فهرست بماند."""
    manifest_path = os.path.join(str(env["photo_dir"]), "partial.json")
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump([{"file": "ghost.jpg", "kind": "exterior", "title": "ناموجود"}], handle)
    saved = ph.MANIFEST_PATH
    ph.MANIFEST_PATH = manifest_path
    try:
        assert ph.load_manifest() == []
    finally:
        ph.MANIFEST_PATH = saved


def test_broken_manifest_is_ignored(env):
    manifest_path = os.path.join(str(env["photo_dir"]), "broken.json")
    with open(manifest_path, "w", encoding="utf-8") as handle:
        handle.write("{ this is not json")
    saved = ph.MANIFEST_PATH
    ph.MANIFEST_PATH = manifest_path
    try:
        assert ph.load_manifest() == []
    finally:
        ph.MANIFEST_PATH = saved


def library_entries(env) -> list[dict]:
    """فهرست نمونهٔ همان فیکسچر `library` — برای آزمون جانشین."""
    return [
        {"file": "exterior-01-a.jpg", "kind": "exterior"},
        {"file": "exterior-02-b.jpg", "kind": "exterior"},
    ]
