# -*- coding: utf-8 -*-
"""آزمون کاتالوگ آگهی‌ها."""
from __future__ import annotations

import re

from khoneyab.config import FEATURES, LUXURY_AREA_THRESHOLD, N_LISTINGS
from khoneyab.listings import all_listings, by_id, listings_frame

LATIN_DIGITS = re.compile(r"[0-9]")


def test_catalogue_matches_the_configured_size(env):
    assert len(env["all"]) == min(env["listings"].N_LISTINGS, len(env["frame"]))


def test_identifiers_are_unique_and_stable(env):
    ids = [item.id for item in env["all"]]
    assert len(set(ids)) == len(ids)
    assert all(identifier.startswith("KH-") for identifier in ids)
    assert env["listings"].all_listings() is env["all"]     # کش‌شده، نه بازساخته


def test_features_follow_the_declared_order(env):
    for listing in env["all"][:40]:
        assert list(listing.as_features()) == list(FEATURES)


def test_listing_derivations(env):
    for listing in env["all"][:40]:
        assert listing.price_per_m2 == int(listing.price / listing.area)
        assert listing.is_luxury == (listing.area >= LUXURY_AREA_THRESHOLD)
        assert listing.district_label.startswith("منطقه")
        assert listing.cover == (listing.gallery[0] if listing.gallery else None)


def test_amenities_are_labelled_in_persian(env):
    listing = next(item for item in env["all"]
                   if item.parking and item.storage and item.elevator)
    assert listing.amenities == ("پارکینگ", "انباری", "آسانسور")
    bare = next(item for item in env["all"]
                if not item.parking and not item.storage and not item.elevator)
    assert bare.amenities == ()


def test_titles_and_descriptions_are_persian(env):
    listing = env["all"][0]
    assert LATIN_DIGITS.search(listing.title) is None
    assert LATIN_DIGITS.search(listing.description) is None
    assert "مترمربع" in listing.description


def test_days_ago_stays_inside_the_window(env):
    assert all(0 <= item.days_ago <= 90 for item in env["all"])


def test_lookup_by_id(env):
    listing = env["all"][12]
    assert by_id(listing.id) is listing
    assert by_id("KH-0000") is None


def test_frame_mirrors_the_catalogue(env):
    frame = listings_frame()
    assert len(frame) == len(env["all"])
    assert set(frame.columns) >= {"id", "district", "price", "price_per_m2", "days_ago"}
    assert frame["id"].is_unique
    row = frame.iloc[0]
    assert row["id"] == env["all"][0].id
    assert row["price"] == env["all"][0].price


def test_cache_can_be_rebuilt(env):
    env["listings"].clear_cache()
    rebuilt = env["listings"].all_listings()
    assert len(rebuilt) == len(env["all"])
    assert [item.id for item in rebuilt] == [item.id for item in env["all"]]
