# -*- coding: utf-8 -*-
"""آزمون لایهٔ وب — خواندن ورودی، وضعیت نشست، شکل نمایش و نسخه‌های کم‌حجم.

سه چیز اینجا سنجیده می‌شود که به‌سختی با آزمون صفحه‌ها گرفته می‌شوند:

* **ورودی نامعتبر** باید به مقدار پیش‌فرض بدل شود، نه به خطای ۵۰۰.
* **وضعیت نشست** باید بین درخواست‌ها بماند و سقفش رعایت شود.
* **نسخه‌های کم‌حجم** باید همان ابعاد واقعی را اعلام کنند، چون عدد نادرست
  باعث انتخاب غلط مرورگر و پرش چیدمان می‌شود.
"""
from __future__ import annotations

import dataclasses
import json
import os

import pytest

from khoneyab import photos
from khoneyab.web import params, presenters
from khoneyab.web import session as store


# ------------------------------------------------------------------ ورودی‌ها
@pytest.mark.parametrize("raw,expected", [
    ("15", 15_000_000_000),
    ("15.5", 15_500_000_000),
    ("۱۵", 15_000_000_000),   # رقم فارسی هم خوانده می‌شود
    ("abc", None),
    ("", None),
    ("-3", None),
    ("99999", None),
])
def test_billions_parses_only_plausible_values(raw, expected):
    assert params.billions(raw) == expected


def test_billions_rejects_an_absurd_amount():
    """عدد بیرون از دامنهٔ ممکن باید رد شود، نه‌این‌که به میلیارد تبدیل شود."""
    assert params.billions("5000") is None
    assert params.billions("0") is None


@pytest.mark.parametrize("raw,expected", [
    ("5", 5), ("0", 0), ("", None), ("abc", None), ("12.5", None),
])
def test_integer_parses_only_whole_numbers(raw, expected):
    assert params.integer(raw) == expected


@pytest.mark.parametrize("raw", ["-1", "9999"])
def test_integer_respects_the_bounds_it_is_given(raw):
    assert params.integer(raw, low=0, high=400) is None


def test_integer_list_keeps_only_allowed_and_unique():
    values = params.integer_list(["1", "2", "2", "99", "x"], allowed=(1, 2, 3))
    assert values == (1, 2)


def test_checkbox_absent_means_unchecked_for_a_submitted_form():
    """جعبهٔ تیک‌نخورده در HTML هیچ پارامتری تولید نمی‌کند."""
    features = params.estimate_features({"f": "1", "area": "100"})
    assert features["parking"] == 0
    assert features["area"] == 100


def test_defaults_apply_before_the_form_is_submitted():
    features = params.estimate_features({})
    assert features["parking"] == 1
    assert features == params.default_features()


def test_out_of_range_estimate_input_falls_back_not_crashes():
    features = params.estimate_features({"f": "1", "district": "999", "area": "5000",
                                         "age": "-4", "floor": "99"})
    assert features["district"] == params.default_features()["district"]
    assert features["area"] == params.default_features()["area"]
    assert features["age"] == params.default_features()["age"]


def test_search_query_clamps_and_normalises():
    query = params.search_query({"sort": "چیز نامعتبر", "page": "-3", "age": "999"})
    assert query.sort == "تازه‌ترین"
    assert query.page == 1
    assert query.age_max is None


def test_ids_are_split_and_deduplicated():
    assert params.ids("a,b , a") == ["a", "b"]
    assert params.ids("") == []
    assert params.ids(None) == []


# ------------------------------------------------------------------ نشست
def test_compare_toggle_adds_then_removes(client):
    first = client.post("/compare/toggle/KH-1001",
                        headers={"X-Requested-With": "fetch"}).get_json()
    assert first["in_compare"] is True and first["count"] == 1

    second = client.post("/compare/toggle/KH-1001",
                         headers={"X-Requested-With": "fetch"}).get_json()
    assert second["in_compare"] is False and second["count"] == 0


def test_compare_refuses_more_than_the_limit(client):
    identifiers = ["KH-1001", "KH-1002", "KH-1003", "KH-1004", "KH-1005"]
    results = [
        client.post(f"/compare/toggle/{identifier}",
                    headers={"X-Requested-With": "fetch"}).get_json()
        for identifier in identifiers
    ]
    assert results[3]["count"] == 4
    assert results[4]["in_compare"] is False
    assert results[4]["reason"] == "full"


def test_compare_state_survives_between_requests(client):
    client.post("/compare/toggle/KH-1002", headers={"X-Requested-With": "fetch"})
    body = client.get("/compare").get_data(as_text=True)
    assert "KH-۱۰۰۲" in body


def test_compare_clear_empties_the_list(client):
    client.post("/compare/toggle/KH-1001", headers={"X-Requested-With": "fetch"})
    payload = client.post("/compare/clear",
                          headers={"X-Requested-With": "fetch"}).get_json()
    assert payload["count"] == 0
    assert "اضافه نشده" in client.get("/compare").get_data(as_text=True)


def test_saved_toggle_round_trips(client):
    first = client.post("/saved/toggle/KH-1007",
                        headers={"X-Requested-With": "fetch"}).get_json()
    assert first["saved"] is True
    assert "KH-۱۰۰۷" in client.get("/saved").get_data(as_text=True)

    second = client.post("/saved/toggle/KH-1007",
                         headers={"X-Requested-With": "fetch"}).get_json()
    assert second["saved"] is False


def test_toggle_without_javascript_redirects(client):
    response = client.post("/compare/toggle/KH-1001", data={"next": "/search"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/search")


def test_redirect_never_leaves_the_site(client):
    """``next`` نباید به دامنهٔ بیرونی بازگرداند."""
    response = client.post("/compare/toggle/KH-1001",
                           data={"next": "https://evil.example/x"})
    assert response.status_code == 302
    assert "evil.example" not in response.headers["Location"]


def test_toggling_an_unknown_listing_is_404(client):
    assert client.post("/compare/toggle/KH-000000").status_code == 404


# ------------------------------------------------------------------ نمایش
def test_card_view_is_complete(env):
    card = presenters.card_view(env["all"][0])
    for key in ("id", "url", "title", "price", "price_per_m2", "image", "amenities"):
        assert key in card
    assert card["url"].startswith("/listing/")
    # عدد نمایشی باید رقم فارسی داشته باشد، نه لاتین.
    assert not any(character.isdigit() and character.isascii()
                   for character in card["price"] + card["price_per_m2"])


def test_estimate_view_is_gap_free(env):
    from khoneyab import services

    explanation = services.explanation_for_listing(env["all"][0])
    view = presenters.estimate_view(explanation, "خلاصه")
    assert view["low"] <= view["price"] <= view["high"]
    assert view["factors"]
    assert view["summary"] == "خلاصه"


def test_gallery_view_handles_a_listing_without_photos(env):
    """آگهی بی‌عکس نباید قالب را بشکند — باید جای خالی را نشان دهد."""
    empty = photos.PhotoLibrary([])
    listing = dataclasses.replace(env["all"][0], gallery=())
    view = presenters.gallery_view(listing)
    assert view["main"] is None
    assert view["sides"] == []
    assert empty.total == 0


# --------------------------------------------------------- نسخه‌های کم‌حجم
@pytest.fixture()
def thumb_workspace(tmp_path):
    """کارگاه جدا برای ساخت نسخهٔ کم‌حجم.

    ابزار ساخت نسخه‌ها مسیرش را در زمان import می‌گیرد؛ اگر آزمون آن را عوض
    نکند، فایل آزمایشی داخل پوشهٔ واقعی پروژه نوشته می‌شود و همان‌جا می‌ماند.
    این فیکسچر هر دو مسیر (ابزار و لایهٔ عکس) را به پوشهٔ موقت می‌برد.
    """
    from PIL import Image

    from tools import make_thumbs

    source_dir = tmp_path / "properties"
    thumb_dir = source_dir / "thumbs"
    thumb_dir.mkdir(parents=True)

    name = "sample-photo.jpg"
    Image.new("RGB", (1600, 1000), (96, 84, 70)).save(str(source_dir / name), "JPEG")
    for variant, width, quality in make_thumbs.VARIANTS:
        Image.new("RGB", (min(width, 1600), int(min(width, 1600) * 0.625)),
                  (110, 95, 78)).save(str(thumb_dir / f"sample-photo.{variant}.jpg"), "JPEG")

    dimensions = {
        "source": {name: [1600, 1000]},
        "tiny": {name: [200, 125]},
        "card": {name: [640, 400]},
        "hero": {name: [1500, 937]},
    }
    dimensions_file = thumb_dir / "dimensions.json"
    dimensions_file.write_text(json.dumps(dimensions), encoding="utf-8")

    saved = (photos.PHOTO_DIR, photos.THUMB_DIR, photos.DIMENSIONS_PATH,
             photos._dimensions_cache, make_thumbs.THUMB_DIR,
             make_thumbs.DIMENSIONS_PATH)
    photos.PHOTO_DIR = str(source_dir)
    photos.THUMB_DIR = str(thumb_dir)
    photos.DIMENSIONS_PATH = str(dimensions_file)
    photos._dimensions_cache = None
    make_thumbs.THUMB_DIR = str(thumb_dir)
    make_thumbs.DIMENSIONS_PATH = str(dimensions_file)
    try:
        yield {"name": name, "stem": "sample-photo", "source_dir": str(source_dir),
               "thumb_dir": str(thumb_dir)}
    finally:
        (photos.PHOTO_DIR, photos.THUMB_DIR, photos.DIMENSIONS_PATH,
         photos._dimensions_cache, make_thumbs.THUMB_DIR,
         make_thumbs.DIMENSIONS_PATH) = saved


def test_sized_prefers_the_thumbnail_with_its_real_size(env, thumb_workspace):
    entry = photos.sized(thumb_workspace["name"], "card")
    assert "thumbs/" in entry["src"]
    assert entry["src"].endswith(".card.jpg")
    assert (entry["width"], entry["height"]) == (640, 400)


def test_sized_falls_back_when_a_variant_is_missing(env, thumb_workspace):
    """نبودِ یک نسخه نباید عکس را بشکند — باید به فایل اصلی برگردد."""
    os.remove(os.path.join(thumb_workspace["thumb_dir"], "sample-photo.hero.jpg"))
    photos._dimensions_cache = None
    entry = photos.sized(thumb_workspace["name"], "hero")
    assert "thumbs/" not in entry["src"]
    assert entry["src"].endswith(".jpg")


def test_sized_returns_a_placeholder_for_a_missing_name(env):
    entry = photos.sized("never-existed.jpg", "card")
    assert entry["src"].startswith("/static/img/properties/")
    assert "thumbs" not in entry["src"]
    assert entry["width"] > 0


def test_sized_returns_nothing_for_no_name(env):
    entry = photos.sized(None, "card")
    assert entry["exists"] is False
    assert entry["src"] == ""


def test_thumbnails_never_claim_a_size_they_do_not_have(env, tmp_path):
    """عدد اعلامی باید با فایل واقعی بخواند، وگرنه چیدمان می‌پرد."""
    from PIL import Image

    from tools import make_thumbs

    source = tmp_path / "measured.jpg"
    Image.new("RGB", (1600, 1000), (120, 100, 80)).save(source, "JPEG")
    with Image.open(source) as opened:
        assert make_thumbs.measure(str(source)) == [opened.width, opened.height]


def test_dimension_manifest_matches_the_real_files():
    """جدول ابعاد آرشیو واقعی نباید از خود فایل‌ها جدا بیفتد.

    این آزمون عمداً از فیکسچر ``env`` استفاده نمی‌کند: آن فیکسچر مسیر عکس‌ها را
    به پوشهٔ موقت می‌برد، ولی اینجا قرار است همان آرشیو و همان فایل ابعادی
    سنجیده شود که در استقرار سرو می‌شود. اگر آرشیو محلی ساخته نشده باشد،
    آزمون رد می‌شود نه شکست.
    """
    from PIL import Image

    from khoneyab import config

    manifest = os.path.join(config.THUMB_DIR, "dimensions.json")
    if not os.path.exists(manifest):
        pytest.skip("فایل ابعاد آرشیو ساخته نشده است")

    with open(manifest, encoding="utf-8") as handle:
        table = json.load(handle)

    assert set(table) >= {"source", "card", "hero"}
    checked = 0
    for variant, entries in table.items():
        for name, pair in entries.items():
            if variant == "source":
                path = os.path.join(config.PHOTO_DIR, name)
            else:
                stem = os.path.splitext(name)[0]
                path = os.path.join(config.THUMB_DIR, f"{stem}.{variant}.jpg")
            if not os.path.exists(path):
                continue
            with Image.open(path) as image:
                assert list(pair) == [image.width, image.height], f"{variant}/{name}"
            checked += 1
    assert checked > 0, "هیچ فایلی برای بررسی نبود"


def test_license_family_hides_version_numbers():
    assert photos.license_family("CC BY-SA 4.0") == "CC BY-SA"
    assert photos.license_family("CC0") == "مالکیت عمومی"
    assert photos.license_family(None) == "نامشخص"
    assert not any(character.isascii() and character.isdigit()
                   for character in photos.license_family("CC BY 4.0"))
