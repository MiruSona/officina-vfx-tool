"""레시피 단계 규칙(설계 8-1) — 규칙마다 걸리는 판 하나씩."""

import json

import pytest
from PIL import Image

from conftest import DATA, PROFILE_PATH, RECIPE_PATH
from vfxtool.errors import VfxError
from vfxtool.recipe.check import run_check


def _check(recipe, **kwargs):
    kwargs.setdefault("input_root", DATA)
    return run_check(recipe, RECIPE_PATH, **kwargs)


def _rules(result, severity=None):
    return [item["rule"] for item in result.issues if severity is None or item["severity"] == severity]


def _profile(tmp_path, **fields):
    data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    data.update(fields)
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_example_passes_clean(recipe):
    result = _check(recipe)
    assert result.issues == []
    assert result.resolved is not None


def test_profile_outside_root_is_paths_error(recipe):
    result = run_check(recipe, RECIPE_PATH)
    assert _rules(result) == ["recipe.paths"]
    assert "--input-root" in result.issues[0]["detail"] and "--input-root" in result.issues[0]["hint"]
    assert result.resolved is None


def test_profile_flag_bypasses_jail(recipe):
    assert run_check(recipe, RECIPE_PATH, profile_path=PROFILE_PATH).issues == []


def test_empty_palette_is_exit2_error(recipe, tmp_path):
    with pytest.raises(VfxError):
        _check(recipe, profile_path=_profile(tmp_path, palette=[]))


def test_schema_error_stops_before_rules(recipe, layer):
    layer["main"]["startSize"] = 3
    layer["mainn"] = {}
    assert _rules(_check(recipe)) == ["recipe.schema"]


def test_pixel_size(recipe, layer):
    layer["main"]["startSize"] = 3
    assert _rules(_check(recipe)) == ["recipe.pixel_size"]
    layer["main"]["startSize"] = 1
    layer["sizeOverLifetime"]["size"] = {"from": 2, "to": 1}
    assert _rules(_check(recipe)) == ["recipe.pixel_size"]


def test_pixel_size_missing_start_size_is_unity_default(recipe, layer):
    del layer["main"]["startSize"]
    assert _rules(_check(recipe)) == ["recipe.pixel_size"]


def test_step_off_warns(recipe, layer):
    layer["sizeOverLifetime"]["size"]["step"] = False
    assert _rules(_check(recipe), "warn") == ["recipe.pixel_size"]


def test_rotation_only_when_profile_blocks(recipe, layer, tmp_path):
    layer["rotationOverLifetime"] = {"z": 90}
    assert _check(recipe).issues == []
    result = _check(recipe, profile_path=_profile(tmp_path, allow_rotation=False))
    assert _rules(result) == ["recipe.rotation"]


def test_alpha_steps(recipe, layer, tmp_path):
    layer["colorOverLifetime"]["color"]["mode"] = "blend"
    layer["main"]["startColor"] = "#FFE08A80"
    assert _rules(_check(recipe)) == ["recipe.alpha_steps", "recipe.alpha_steps"]
    assert _check(recipe, profile_path=_profile(tmp_path, alpha_steps="free")).issues == []


def test_gradient_keys(recipe, layer):
    layer["colorOverLifetime"]["color"]["gradient"]["alpha"] = [[i / 10, 1] for i in range(9)]
    assert _rules(_check(recipe)) == ["recipe.gradient_keys"]


def test_palette_and_max_colors(recipe, layer):
    layer["main"]["startColor"] = {"random": ["#123456", "#FFFFFF"]}
    layer["colorOverLifetime"]["color"]["gradient"]["color"] = [[0, "p0"], [0.3, "p1"], [0.6, "p2"], [0.9, "p3"]]
    result = _check(recipe)
    assert _rules(result, "warn") == ["recipe.palette", "recipe.max_colors", "recipe.color_multiply"]
    assert result.resolved is not None


def test_color_multiply_warns_only_when_both_colored(recipe, layer):
    assert "recipe.color_multiply" not in _rules(_check(recipe), "warn")  # 색 키가 흰색
    layer["colorOverLifetime"]["color"]["gradient"]["color"] = [[0, "p0"], [0.5, "p3"]]
    found = [i for i in _check(recipe).issues if i["rule"] == "recipe.color_multiply"]
    assert len(found) == 1 and found[0]["hint"] == ["main.startColor", "colorOverLifetime.color"]
    layer["main"]["startColor"] = "#FFFFFF"
    assert "recipe.color_multiply" not in _rules(_check(recipe), "warn")


def test_palette_index_out_of_range_is_error(recipe, layer):
    layer["main"]["startColor"] = "p9"
    assert _rules(_check(recipe)) == ["recipe.palette"]
    assert _check(recipe).resolved is None


def test_additive_is_info(recipe, layer):
    layer["blend"] = "additive"
    assert _rules(_check(recipe)) == ["recipe.additive"]
    assert _check(recipe).resolved is not None


def test_blend_and_lit_light(recipe, layer):
    layer["material"] = "lit"
    layer["blend"] = "additive"
    recipe["light"] = "none"
    assert sorted(_rules(_check(recipe))) == ["recipe.additive", "recipe.blend", "recipe.lit_light"]


def test_max_particles(recipe, layer):
    layer["main"]["maxParticles"] = 300
    assert _rules(_check(recipe)) == ["recipe.max_particles"]
    del layer["main"]["maxParticles"]
    assert _rules(_check(recipe)) == ["recipe.max_particles"]


def test_unsupported(recipe, layer):
    layer["collision"] = {}
    assert _rules(_check(recipe)) == ["recipe.unsupported"]


def test_bloom_later_warns(recipe):
    recipe["bloom"] = True
    assert _rules(_check(recipe), "warn") == ["recipe.bloom_later"]


def test_texture_paths(recipe, layer, tmp_path):
    layer["texture"] = "../../../outside.png"
    assert _rules(_check(recipe)) == ["recipe.paths"]
    layer["texture"] = "missing.png"
    assert _rules(_check(recipe)) == ["recipe.paths"]


def test_unknown_template_is_template_missing(recipe):
    recipe["layers"].append({"name": "dust", "template": "no_such_template", "params": {"count": 6}})
    result = _check(recipe)
    assert _rules(result) == ["recipe.template_missing"]
    assert result.issues[0]["layer"] == "dust"


def _flipbook_recipe(recipe, tmp_path, size, tiles, fps):
    Image.new("RGBA", size).save(tmp_path / "sheet.png")
    layer = recipe["layers"][0]
    layer["texture"] = "sheet.png"
    layer["textureSheet"] = {"tiles": tiles, "fps": fps}
    # 시트 층에 크기 곡선은 recipe.lib_size error 라 기본 레시피의 곡선을 뗀다.
    layer.pop("sizeOverLifetime", None)
    return run_check(recipe, tmp_path / "recipe.json", profile_path=PROFILE_PATH)


def test_flipbook_ok(recipe, tmp_path):
    result = _flipbook_recipe(recipe, tmp_path, (32, 8), [4, 1], 12)
    assert result.issues == []
    assert result.resolved["layers"][0]["texture"].endswith("/sheet.png")


def test_flipbook_bad_tiles_and_fps(recipe, tmp_path):
    result = _flipbook_recipe(recipe, tmp_path, (30, 8), [4, 1], 30)
    assert _rules(result) == ["recipe.flipbook", "recipe.flipbook"]


def test_flipbook_without_sheet(recipe, layer):
    layer["textureSheet"] = {"tiles": [2, 2]}
    assert _rules(_check(recipe)) == ["recipe.flipbook"]
