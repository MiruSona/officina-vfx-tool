"""판별 프로필 사본 — palette(· max_colors · fx_extra)만 다름 · {value, source} 꼴 · 모르는 칸 보존 · 레시피 profile 칸."""

import json

from conftest import write_set
from vfxtool.variant_dict import load_all
from vfxtool.variant_expand import expand_set, profile_copy

RAW = {
    "version": 1,
    "palette": {"value": ["#111111", "#222222"], "source": "png:hero.png"},
    "ppu": 32,
    "max_colors": 2,
    "fx_extra": ["#FFFFFF"],
    "game_note": {"keep": True},
}


def test_only_palette_changes():
    fire = load_all()["fire"]["data"]
    copied = profile_copy(RAW, fire)
    assert copied["palette"] == {"value": fire["palette"], "source": "variant:fire"}
    rest = {key: value for key, value in copied.items() if key != "palette"}
    assert rest == {key: value for key, value in RAW.items() if key != "palette"}
    assert list(copied) == list(RAW)
    assert RAW["palette"]["value"] == ["#111111", "#222222"]


def test_max_colors_and_fx_extra_when_given():
    attr = {"name": "x", "palette": ["#ABCDEF"], "max_colors": 6, "fx_extra": ["#FFFFFF", "#FFFF00"]}
    copied = profile_copy(RAW, attr)
    assert copied["max_colors"] == 6
    assert copied["fx_extra"] == ["#FFFFFF", "#FFFF00"]
    assert copied["game_note"] == {"keep": True}


def test_base_is_plain_copy():
    assert profile_copy(RAW, None) == RAW


def test_unknown_field_kept_and_recipe_points_to_copy(tmp_path):
    path = write_set(tmp_path / "in", attrs=["ice"], tiers=["mid"], seeds=1)
    base = json.loads((tmp_path / "in" / "profile.json").read_text(encoding="utf-8"))
    base["game_note"] = "그대로"
    (tmp_path / "in" / "profile.json").write_text(json.dumps(base), encoding="utf-8")
    expand_set(path, tmp_path / "work")
    variant = tmp_path / "work" / "hit" / "hit_ice_mid"
    copied = json.loads((variant / "profile.json").read_text(encoding="utf-8"))
    assert copied["game_note"] == "그대로"
    assert copied["palette"] == load_all()["ice"]["data"]["palette"]
    assert json.loads((variant / "recipe.json").read_text(encoding="utf-8"))["profile"] == "profile.json"
