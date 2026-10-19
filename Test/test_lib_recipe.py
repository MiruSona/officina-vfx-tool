"""레시피의 `lib:` — 풀기(절대 경로 · tiles 채움) · recipe.lib · row 꼴 · lib_size · flipbook_life ·
render 재검사 감옥 예외 · measure 지표 palette_out · flicker · lib CLI."""

import json
import os
import subprocess
import sys

import numpy as np

from conftest import DATA, RECIPE_PATH, SRC
from vfxtool import material_lib, measure_metrics
from vfxtool.recipe.check import run_check
from vfxtool.unity.guard import texture_issues


def _check(recipe):
    return run_check(recipe, RECIPE_PATH, input_root=DATA)


def _rules(result, severity=None):
    return [i["rule"] for i in result.issues if severity is None or i["severity"] == severity]


def _lib_layer(layer, texture, size, sheet=None, life=0.3):
    layer["texture"] = texture
    layer["main"]["startSize"] = size
    layer["main"]["startLifetime"] = life
    layer.pop("sizeOverLifetime", None)
    if sheet is not None:
        layer["textureSheet"] = sheet


# ── resolve ──

def test_lib_ring_resolves_to_abs_path_and_fills_tiles(recipe, layer):
    _lib_layer(layer, "lib:ring", 15, {"fps": 12})
    result = _check(recipe)
    assert _rules(result, "error") == [] and _rules(result, "warn") == [], result.issues
    resolved = result.resolved["layers"][0]
    assert resolved["texture"] == material_lib.path("ring").as_posix()
    assert resolved["textureSheet"] == {"tiles": [4, 1], "fps": 12}


def test_lib_without_sheet_fills_tiles_and_profile_fps(recipe, layer):
    _lib_layer(layer, "lib:star4", 7)
    sheet = _check(recipe).resolved["layers"][0]["textureSheet"]
    assert sheet == {"tiles": [4, 1], "fps": 12}


def test_single_grain_gets_no_sheet(recipe, layer):
    _lib_layer(layer, "lib:disc", 7)
    assert "textureSheet" not in _check(recipe).resolved["layers"][0]


def test_row_resolves_in_schema_order(recipe, layer):
    _lib_layer(layer, "lib:shard", 5, {"row": "random"})
    assert _check(recipe).resolved["layers"][0]["textureSheet"] == {"tiles": [1, 3], "row": "random"}
    layer["textureSheet"] = {"row": 2}
    assert _check(recipe).resolved["layers"][0]["textureSheet"] == {"tiles": [1, 3], "row": 2}


# ── recipe.lib · row 꼴 ──

def test_unknown_lib_name_is_error(recipe, layer):
    _lib_layer(layer, "lib:nope", 5)
    assert _rules(_check(recipe), "error") == ["recipe.lib"]


def test_tiles_differ_from_meta_is_error(recipe, layer):
    _lib_layer(layer, "lib:ring", 15, {"tiles": [2, 2]})
    assert _rules(_check(recipe), "error") == ["recipe.lib"]


def test_row_out_of_range_is_error(recipe, layer):
    _lib_layer(layer, "lib:dot", 3, {"row": 3})
    assert _rules(_check(recipe), "error") == ["recipe.lib"]


def test_variant_grain_without_row_warns(recipe, layer):
    _lib_layer(layer, "lib:dot", 3)
    assert "recipe.lib" in _rules(_check(recipe), "warn")


def test_row_shape_checked(recipe, layer):
    for bad in ("abc", -1, 1.5, True):
        _lib_layer(layer, "lib:dot", 3, {"row": bad})
        assert _rules(_check(recipe), "error") == ["recipe.schema"], bad


def test_file_sheet_row_out_of_range(recipe, layer):
    layer["texture"] = "sparkle_sheet.png"
    recipe_path = DATA / "recipes" / "x.json"
    layer["main"]["startSize"] = 5
    layer.pop("sizeOverLifetime")
    layer["textureSheet"] = {"tiles": [4, 1], "row": 1}
    result = run_check(recipe, recipe_path, input_root=DATA)
    assert _rules(result, "error") == ["recipe.flipbook"]


# ── lib_size · flipbook_life ──

def test_lib_size_errors_when_not_cell_multiple(recipe, layer):
    _lib_layer(layer, "lib:cross", 6, {"row": 0})
    assert "recipe.lib_size" in _rules(_check(recipe), "error")
    layer["main"]["startSize"] = 10
    assert "recipe.lib_size" not in _rules(_check(recipe))
    layer["main"]["startSize"] = 5
    layer["sizeOverLifetime"] = {"size": {"curve": [[0, 1], [0.5, 1.4], [1, 1]]}}
    assert "recipe.lib_size" in _rules(_check(recipe), "error")


def test_lib_size_curve_errors_even_on_whole_keys(recipe, layer):
    # 키가 1 → 2 로 정수 배여도 사이 값(1.5 배)에서 깨지므로 곡선 자체가 error.
    _lib_layer(layer, "lib:cross", 5, {"row": 0})
    layer["sizeOverLifetime"] = {"size": {"curve": [[0, 1], [1, 2]]}}
    assert _rules(_check(recipe), "error") == ["recipe.lib_size"]
    layer["sizeOverLifetime"] = {"size": 2}
    assert "recipe.lib_size" not in _rules(_check(recipe))


def test_file_sheet_size_curve_is_error(recipe, layer):
    layer["texture"] = "sparkle_sheet.png"
    layer["main"]["startSize"] = 5
    layer["textureSheet"] = {"tiles": [4, 1]}
    layer["sizeOverLifetime"] = {"size": {"curve": [[0, 1], [0.5, 2], [1, 1]]}}
    result = run_check(recipe, DATA / "recipes" / "x.json", input_root=DATA)
    assert "recipe.lib_size" in _rules(result, "error")
    layer.pop("sizeOverLifetime")
    result = run_check(recipe, DATA / "recipes" / "x.json", input_root=DATA)
    assert "recipe.lib_size" not in _rules(result)


def test_flipbook_life_warns_when_longer_than_frames(recipe, layer):
    _lib_layer(layer, "lib:burst16", 16, {"fps": 12}, life=0.416)
    assert "recipe.flipbook_life" not in _rules(_check(recipe))
    layer["main"]["startLifetime"] = {"random": [0.3, 0.6]}
    assert "recipe.flipbook_life" in _rules(_check(recipe), "warn")


def test_grain_row_never_flipbook_life(recipe, layer):
    _lib_layer(layer, "lib:shard", 5, {"row": 1}, life=2.0)
    assert "recipe.flipbook_life" not in _rules(_check(recipe))


# ── render 재검사 감옥 ──

def test_render_guard_lets_lib_png_outside_root(tmp_path):
    resolved = {"layers": [
        {"name": "a", "texture": material_lib.path("ring").as_posix()},
        {"name": "b", "texture": (tmp_path.parent / "elsewhere.png").as_posix()},
        {"name": "c", "texture": "lib:ring"},
    ]}
    found = texture_issues(resolved, tmp_path)
    assert [(i["layer"], i["rule"]) for i in found] == [("b", "recipe.paths"), ("c", "recipe.lib")]


# ── measure 지표 ──

def test_palette_out_by_hand():
    tex = np.zeros((2, 4, 4), dtype=np.uint8)
    tex[0, 0] = (255, 255, 255, 255)
    tex[0, 1] = (255, 255, 255, 255)
    tex[0, 2] = (10, 20, 30, 255)
    tex[1, 3] = (255, 255, 255, 255)
    dist, dist_map = measure_metrics.palette_distance(tex, [(255, 255, 255)])
    assert dist > 0
    assert measure_metrics.palette_out(dist_map, measure_metrics.covered_mask(tex)) == 0.25
    empty = np.zeros((2, 2, 4), dtype=np.uint8)
    _, empty_map = measure_metrics.palette_distance(empty, [(255, 255, 255)])
    assert measure_metrics.palette_out(empty_map, measure_metrics.covered_mask(empty)) == 0.0


def test_flicker_by_hand():
    assert measure_metrics.flicker([0, 5, 9, 9, 4, 0]) == 1
    assert measure_metrics.flicker([0, 5, 2, 6, 1, 0]) == 3
    assert measure_metrics.flicker([3, 3, 3]) == 0
    assert measure_metrics.flicker([]) == 0


# ── CLI ──

def _run(*args):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC)
    done = subprocess.run([sys.executable, "-m", "vfxtool", *args], capture_output=True, env=env, timeout=60)
    return done.returncode, json.loads(done.stdout.decode("utf-8"))


def test_cli_lib_list_show_build(tmp_path):
    code, report = _run("lib", "list")
    assert code == 0 and len(report["metrics"]["lib"]) == 10
    code, report = _run("lib", "show", "ring")
    assert code == 0 and report["metrics"]["meta"]["tiles"] == [4, 1]
    code, report = _run("lib", "build", "--only", "dot", "--out", str(tmp_path))
    assert code == 0 and report["metrics"]["written"] == ["dot"] and (tmp_path / "dot.png").is_file()
    code, _ = _run("lib", "show", "nope")
    assert code == 2


# ── 10-15 리뷰 고침 ──

def test_file_sheet_without_fps_gets_profile_fps(recipe, layer):
    # 파일 시트도 여러 장이면 fps 를 채운다 — C# 은 늘 FPS 모드라 안 주면 Unity 기본값으로 돈다.
    layer["texture"] = "sparkle_sheet.png"
    layer["main"]["startSize"] = 5
    layer.pop("sizeOverLifetime")
    layer["textureSheet"] = {"tiles": [4, 1]}
    result = run_check(recipe, DATA / "recipes" / "x.json", input_root=DATA)
    assert result.resolved["layers"][0]["textureSheet"] == {"tiles": [4, 1], "fps": 12}
    layer["textureSheet"] = {"tiles": [1, 1]}
    result = run_check(recipe, DATA / "recipes" / "x.json", input_root=DATA)
    assert "fps" not in result.resolved["layers"][0]["textureSheet"]


def test_lib_size_errors_on_random_start_size(recipe, layer):
    # 끝점 5 · 10 이 둘 다 칸(5)의 배수여도 사이 값(7 등)에서 깨진다.
    _lib_layer(layer, "lib:cross", {"random": [5, 10]}, {"row": 0})
    assert _rules(_check(recipe), "error") == ["recipe.lib_size"]
    layer["main"]["startSize"] = {"curve": [[0, 5], [1, 10]]}
    assert "recipe.lib_size" in _rules(_check(recipe), "error")
    layer["main"]["startSize"] = {"random": [10, 10]}
    assert "recipe.lib_size" not in _rules(_check(recipe))


def test_file_sheet_random_start_size_is_error(recipe, layer):
    layer["texture"] = "sparkle_sheet.png"
    layer["main"]["startSize"] = {"random": [4, 8]}
    layer.pop("sizeOverLifetime")
    layer["textureSheet"] = {"tiles": [4, 1]}
    result = run_check(recipe, DATA / "recipes" / "x.json", input_root=DATA)
    assert "recipe.lib_size" in _rules(result, "error")


def test_palette_out_is_none_without_palette():
    tex = np.zeros((2, 2, 4), dtype=np.uint8)
    tex[0, 0] = (10, 20, 30, 255)
    _, dist_map = measure_metrics.palette_distance(tex, [])
    assert measure_metrics.palette_out(dist_map, measure_metrics.covered_mask(tex), []) is None


def test_measure_reports_no_palette(tmp_path, monkeypatch):
    # 허용 색이 비면 palette_out 은 0 이 아니라 None(판정 불가) + measure.no_palette info.
    # 지금 프로필 읽기는 빈 palette 를 거절하므로 허용 색 셈만 비게 바꿔 본다(뒷길 방어).
    from vfxtool import measure as measure_mod
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"palette": ["#FFFFFF"], "source": {"palette": "png"}}), encoding="utf-8")
    monkeypatch.setattr(measure_mod, "allowed_colors", lambda _profile: [])
    report = measure_mod.measure(DATA / "frames" / "round_1", profile)
    assert report["metrics"]["palette_out_mean"] is None
    assert set(report["metrics"]["palette_out"]) == {None}
    assert any(i["rule"] == "measure.no_palette" and i["severity"] == "info" for i in report["issues"])
