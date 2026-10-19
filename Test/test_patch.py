"""patch — Merge Patch 규칙 · 층 이름 열쇠 · patch 명령."""

import json

import pytest

from conftest import DATA, RECIPE_PATH
from test_cli import _run
from vfxtool.errors import VfxError
from vfxtool.recipe.patch import apply, merge_patch


def test_merge_patch_rfc_rules():
    target = {"a": {"b": 1, "c": [1, 2]}, "d": 4}
    assert merge_patch(target, {"a": {"b": None, "c": [3]}, "e": 5}) == {"a": {"c": [3]}, "d": 4, "e": 5}
    assert target == {"a": {"b": 1, "c": [1, 2]}, "d": 4}


def test_layers_by_name(recipe):
    patched, issues = apply(recipe, {
        "duration": 0.45,
        "layers": {"sparks": {"emission": {"bursts": [[0, 12]]}, "main": {"startSpeed": {"random": [30, 70]}}}},
    })
    layer = patched["layers"][0]
    assert issues == []
    assert patched["duration"] == 0.45
    assert layer["emission"] == {"rateOverTime": 0, "bursts": [[0, 12]]}
    assert layer["main"]["startSpeed"] == {"random": [30, 70]}
    assert layer["main"]["startSize"] == 1


def test_layer_delete_and_add(recipe):
    patched, issues = apply(recipe, {"layers": {"sparks": None, "glow": {"blend": "additive", "main": {}}}})
    assert patched["layers"] == [{"blend": "additive", "main": {}, "name": "glow"}]
    assert [(i["rule"], i["severity"]) for i in issues] == [("patch.new_layer", "warn")]


def _rules(issues):
    return [(i["rule"], i["severity"]) for i in issues]


def test_fixed_fields_and_layers_array_are_refused(recipe):
    for key, value in (("profile", "other.json"), ("name", "x"), ("version", 2)):
        patched, issues = apply(recipe, {key: value})
        assert patched is None and _rules(issues) == [("patch.fixed_field", "error")]
    same, issues = apply(recipe, {"name": recipe["name"]})  # 같은 값은 바꾸기가 아니다
    assert same is not None and issues == []
    patched, issues = apply(recipe, {"layers": [{"name": "x"}]})
    assert patched is None and _rules(issues) == [("patch.layers_array", "error")]


def test_new_layer_needs_main_and_no_dot(recipe):
    patched, issues = apply(recipe, {"layers": {"glow": {"blend": "additive"}}})
    assert patched is None and _rules(issues) == [("patch.new_layer", "error")]
    patched, issues = apply(recipe, {"layers": {"heal.glow": {"main": {}}}})
    assert patched is None and _rules(issues) == [("patch.new_layer", "error")]


def test_bad_patch_is_error(recipe):
    with pytest.raises(VfxError):
        apply(recipe, {"layers": {"sparks": 3}})
    with pytest.raises(VfxError):
        apply(recipe, [1])


def test_patch_command(tmp_path):
    patch = tmp_path / "patch.json"
    patch.write_text(json.dumps({"layers": {"sparks": {"main": {"startSize": 3}}}}), encoding="utf-8")
    out = tmp_path / "round_2" / "recipe.json"
    code, stdout, _ = _run("patch", str(RECIPE_PATH), str(patch), "--out", str(out), "--profile", str(DATA / "profile.json"))
    report = json.loads(stdout)
    assert code == 1
    assert report["issues"][0]["rule"] == "recipe.pixel_size"
    assert json.loads(out.read_text(encoding="utf-8"))["layers"][0]["main"]["startSize"] == 3
