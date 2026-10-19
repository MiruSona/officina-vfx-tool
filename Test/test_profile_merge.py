"""profile/style.py · merge.py — 화풍 조각 대응과 이기는 순서(기본값 < PNG < 화풍 조각 < 손 덮기)."""
import json
from pathlib import Path

import pytest

from vfxtool.errors import VfxError
from vfxtool.profile.common import DEFAULTS
from vfxtool.profile.merge import merge
from vfxtool.profile.style import map_style

DATA = Path(__file__).parent / "data" / "profile"
PNG_FIELDS = {"palette": ["#E04020", "#F0C040"], "pixel_size": [2]}


def _load(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def test_defaults_match_design_table():
    profile = merge({}, {}, None)["profile"]
    assert profile["allow_rotation"] is True
    assert profile["seq_tolerance"] == {"ratio": 0.5, "run": 3}
    assert profile["ppu"] == 32
    assert profile["pixel_size"] == [1, 2]
    assert profile["fx_extra"] == ["#FFFFFF"]
    assert set(profile["source"].values()) == {"default"}
    assert list(profile)[1:-1] == list(DEFAULTS)


def test_style_reads_known_keys_and_ignores_rest():
    mapped = map_style(_load("style.json"))
    assert mapped["fields"]["palette"] == ["#E04020", "#F0C040", "#FFFFFF", "#402010", "#112233"]
    assert mapped["fields"]["ppu"] == 16
    assert mapped["fields"]["fps"] == 10
    assert "outline" not in mapped["fields"]
    assert [issue["rule"] for issue in mapped["issues"]] == ["profile.style_value"]
    assert mapped["ignored"] == ["lighting", "name"]


def test_style_fps_beats_frame_ms_and_palette_object_form():
    mapped = map_style({"frame_ms": 50, "fps": 14, "palette": {"colors": ["#010203"]}, "pixels_per_unit": 8})
    assert mapped["fields"] == {"palette": ["#010203"], "ppu": 8, "fps": 14}


def test_bad_style_value_is_warn_not_error():
    mapped = map_style({"ppu": "big", "palette": ["red"]})
    assert mapped["fields"] == {}
    assert len(mapped["issues"]) == 2


def test_order_default_png_style_override():
    style = map_style(_load("style.json"))["fields"]
    merged = merge(PNG_FIELDS, style, _load("hand.json"))
    profile = merged["profile"]
    source = profile["source"]

    assert profile["pixel_size"] == [2] and source["pixel_size"] == "png"
    assert profile["palette"][-1] == "#112233" and source["palette"] == "style"
    assert profile["fps"] == 10 and source["fps"] == "style"
    assert profile["ppu"] == 24 and source["ppu"] == "override"
    assert profile["allow_rotation"] is False and source["allow_rotation"] == "override"
    assert profile["seq_tolerance"] == {"ratio": 0.5, "run": 4}
    assert profile["fx_extra"] == ["#FFFFFF", "#FFF0C0"]
    assert profile["max_colors"] == 4 and source["max_colors"] == "default"
    # style 의 frame_ms 100 → fps 10 이 기본 fps_range [12, 16] 밖이라 warn 이 하나 더 붙는다.
    assert [issue["rule"] for issue in merged["issues"]] == ["profile.unknown_key", "profile.fps_range"]


def test_override_with_previous_profile_keys_passes():
    previous = merge(PNG_FIELDS, {}, None)["profile"]
    profile = merge({}, {}, previous)["profile"]
    assert profile["palette"] == PNG_FIELDS["palette"]
    assert profile["source"]["palette"] == "override"


@pytest.mark.parametrize("override", [
    {"ppu": 0},
    {"allow_rotation": "yes"},
    {"seq_tolerance": {"ratio": 2}},
    {"seq_tolerance": {"len": 3}},
    {"palette": ["#12345"]},
    {"outline": "black"},
    {"fps_range": [16, 12]},
    {"alpha_steps": "half"},
])
def test_bad_override_value_is_error(override):
    with pytest.raises(VfxError):
        merge({}, {}, override)


def test_override_must_be_object():
    with pytest.raises(VfxError):
        merge({}, {}, ["ppu"])
