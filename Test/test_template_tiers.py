"""템플릿 tiers 칸 · file 파라미터 짝 키(size · tiles · color) 검사(변형묶음설계 3-3 · 3-5 · 5절)."""

import json

import pytest

from vfxtool.errors import VfxError
from vfxtool.template import BUILTIN_DIR, load_all

TEMPLATES = ("hit_sparks", "land_dust", "ambient_motes", "heal_rise", "sparkle")


def _data(name):
    return json.loads((BUILTIN_DIR / f"{name}.json").read_text(encoding="utf-8"))


def _load_changed(tmp_path, change):
    data = _data("hit_sparks")
    change(data)
    (tmp_path / "hit_sparks.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return load_all([tmp_path])


@pytest.mark.parametrize("name", TEMPLATES)
def test_tiers_shape(name):
    tiers = load_all()[name]["data"]["tiers"]
    assert list(tiers) == ["weak", "mid", "strong"]
    assert tiers["mid"] == {"mul": {}}
    for body in tiers.values():
        assert body.get("scale", 1) == 1


@pytest.mark.parametrize("name", TEMPLATES)
def test_every_sheet_layer_texture_and_size_are_params(name):
    data = load_all()[name]["data"]
    params = data["params"]
    for layer in data["layers"]:
        texture = layer["texture"]
        assert texture.startswith("$"), (name, layer["name"])
        spec = params[texture[1:]]
        assert spec["type"] == "file" and "size" in spec
        assert layer["main"]["startSize"] == f"${spec['size']}"


def test_sparkle_life_not_multiplied():
    for body in load_all()["sparkle"]["data"]["tiers"].values():
        assert "life" not in body["mul"]


def test_left_right_layers_share_one_pair():
    layers = {layer["name"]: layer for layer in load_all()["land_dust"]["data"]["layers"]}
    for left, right in (("puff_l", "puff_r"), ("small_l", "small_r"), ("chips_l", "chips_r")):
        assert layers[left]["texture"] == layers[right]["texture"]
        assert layers[left]["main"]["startSize"] == layers[right]["main"]["startSize"]


def test_pair_must_point_to_right_kind(tmp_path):
    def change(data):
        data["params"]["sparks_tex"]["size"] = "color"
    with pytest.raises(VfxError, match="size 짝"):
        _load_changed(tmp_path, change)


def test_pair_needs_size_key(tmp_path):
    def change(data):
        del data["params"]["core_tex"]["size"]
    with pytest.raises(VfxError, match="size 가 없다"):
        _load_changed(tmp_path, change)


def test_color_pair_must_be_color(tmp_path):
    def change(data):
        data["params"]["ring_tex"]["color"] = "count"
    with pytest.raises(VfxError, match="color 짝"):
        _load_changed(tmp_path, change)


@pytest.mark.parametrize("body, words", [
    ({"mul": {"ring": 2}}, "int · float"),
    ({"mul": {"nope": 2}}, "int · float"),
    ({"mul": {"count": 0}}, "0 보다 큰"),
    ({"mul": {"count": True}}, "0 보다 큰"),
    ({"mul": {}, "scale": 0}, "scale"),
    ({"mul": {}, "scale": 1.5}, "scale"),
    ({"mul": {}, "extra": 1}, "칸은"),
])
def test_bad_tier_rejected(tmp_path, body, words):
    def change(data):
        data["tiers"]["strong"] = body
    with pytest.raises(VfxError, match=words):
        _load_changed(tmp_path, change)


def test_good_inline_style_tier_accepted(tmp_path):
    def change(data):
        data["tiers"]["huge"] = {"mul": {"count": 3}, "scale": 2}
    assert "huge" in _load_changed(tmp_path, change)["hit_sparks"]["data"]["tiers"]
