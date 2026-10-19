"""칸 표 검사 — 모르는 칸 제안 · 필수 칸 · 2차 모듈 · 꼴."""

import pytest
from vfxtool.recipe import fields, schema


def _rules(found):
    return [item["rule"] for item in found]


def test_example_recipe_has_no_schema_issue(recipe):
    assert fields.check_top(recipe) == []
    assert fields.check_layers(recipe) == []


def test_unknown_top_field_suggests_name(recipe):
    recipe["durration"] = 1
    found = fields.check_top(recipe)
    assert _rules(found) == ["recipe.schema"]
    assert "'duration'" in found[0]["detail"]


def test_missing_required_and_bad_version(recipe):
    del recipe["seed"]
    recipe["version"] = 2
    details = " ".join(item["detail"] for item in fields.check_top(recipe))
    assert "'seed'" in details and "판" in details


def test_name_pattern_and_layer_count(recipe):
    recipe["name"] = "Hit-Sparks"
    assert _rules(fields.check_top(recipe)) == ["recipe.schema"]
    recipe["name"] = "ok"
    recipe["name"] = "fx\n"
    assert _rules(fields.check_top(recipe)) == ["recipe.schema"]  # $ 가 끝 줄바꿈을 받던 구멍
    recipe["name"] = "ok"
    recipe["layers"] = [dict(recipe["layers"][0], name=f"l{i}") for i in range(7)]
    assert _rules(fields.check_top(recipe)) == []  # 층 수는 펼친 뒤에 본다
    assert _rules(fields.check_layers(recipe)) == ["recipe.schema"]


@pytest.mark.parametrize("name", ["a..b", "a.", ".a", "con", "COM1.x", "x" * 41, "sparks\n", "a b"])
def test_bad_layer_names(name):
    assert schema.layer_name_problem(name) is not None


@pytest.mark.parametrize("name", ["sparks", "heal.glow", "A-1_b", "x" * 40, "console"])
def test_good_layer_names(name):
    assert schema.layer_name_problem(name) is None


def test_hex_and_palette_reject_trailing_newline():
    from vfxtool.recipe import colors
    from vfxtool.profile import common

    assert not colors.is_hex("#FFFFFF\n") and not colors.is_ref("p1\n")
    with pytest.raises(ValueError):
        common.normalize("palette", ["#FFFFFF\n"], [])


def test_duplicate_layer_name(recipe):
    recipe["layers"].append(dict(recipe["layers"][0]))
    found = fields.check_top(recipe)
    assert found[0]["layer"] == "sparks"


def test_unknown_module_field_suggests(layer, recipe):
    layer["main"]["startSpeeed"] = 3
    found = fields.check_layers(recipe)
    assert found[0]["rule"] == "recipe.schema"
    assert "'startSpeed'" in found[0]["detail"]


def test_unknown_module_suggests(layer, recipe):
    layer["emision"] = {}
    assert "'emission'" in fields.check_layers(recipe)[0]["detail"]


def test_later_module_is_unsupported(layer, recipe):
    layer["trails"] = {"ratio": 1}
    layer["shape"]["type"] = "Mesh"
    layer["renderer"] = {"renderMode": "Stretch"}
    assert _rules(fields.check_layers(recipe)) == ["recipe.unsupported"] * 3


def test_field_kinds(layer, recipe):
    layer["main"]["maxParticles"] = 1.5
    layer["shape"]["angle"] = 120
    layer["shape"]["rotation"] = [0, 90]
    layer["emission"]["bursts"] = [[0, -1]]
    layer["main"]["startSpeed"] = {"random": [1]}
    layer["main"]["startColor"] = "orange"
    found = fields.check_layers(recipe)
    assert len(found) == 6
    assert all(item["severity"] == "error" for item in found)


def test_burst_object_form(layer, recipe):
    layer["emission"]["bursts"] = [{"t": 0, "n": 4, "cycles": 2, "interval": 0.1}, [0.2, 3]]
    assert fields.check_layers(recipe) == []
    layer["emission"]["bursts"] = [{"t": 0, "n": 4, "cycles": 0}]
    assert _rules(fields.check_layers(recipe)) == ["recipe.schema"]
    for bad in ({"t": -0.1, "n": 4}, {"t": 0, "n": -1}):
        layer["emission"]["bursts"] = [bad]
        assert _rules(fields.check_layers(recipe)) == ["recipe.schema"]


def test_length_table_is_single_place():
    assert schema.is_length("main", "startSize")
    assert schema.is_length("shape", "position")
    assert not schema.is_length("sizeOverLifetime", "size")
    assert not schema.is_length("main", "startLifetime")
    assert not schema.is_length("main", "gravityModifier")
