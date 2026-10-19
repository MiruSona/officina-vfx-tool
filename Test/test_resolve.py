"""resolved.json — 단위 · 팔레트 · 곡선 펼치기 · golden 바이트 비교."""

from conftest import DATA, RECIPE_PATH
from vfxtool.paths import write_json
from vfxtool.recipe.check import run_check
from vfxtool.profile.common import DEFAULTS

GOLDEN = DATA / "golden" / "hit_sparks_a.resolved.json"


def _resolved(recipe):
    result = run_check(recipe, RECIPE_PATH, input_root=DATA)
    assert result.resolved is not None, result.issues
    return result.resolved


def test_golden_bytes(recipe, tmp_path):
    out = write_json(tmp_path / "resolved.json", _resolved(recipe))
    assert out.read_bytes() == GOLDEN.read_bytes()


def test_texels_become_units(recipe):
    layer = _resolved(recipe)["layers"][0]
    assert layer["main"]["startSize"] == 0.03125
    assert layer["main"]["startSpeed"] == {"random": [1.25, 2.8125]}
    assert layer["shape"]["radius"] == 0.03125
    assert layer["main"]["startLifetime"] == {"random": [0.25, 0.45]}
    assert layer["shape"]["rotation"] == [-90, 0, 0]
    assert layer["main"]["gravityModifier"] == 0.6


def test_size_curve_defaults_to_step_and_is_not_scaled(recipe):
    size = _resolved(recipe)["layers"][0]["sizeOverLifetime"]["size"]
    assert size == {"curve": [[0, 2], [0.4, 1]], "mult": 1, "step": True}


def test_palette_resolved_to_hex(recipe):
    layer = _resolved(recipe)["layers"][0]
    assert layer["main"]["startColor"] == "#FFE08A"
    assert layer["colorOverLifetime"]["color"]["gradient"]["color"] == [[0, "#FFFFFF"]]
    assert layer["colorOverLifetime"]["color"]["mode"] == "fixed"


def test_ease_becomes_curve(recipe):
    recipe["layers"][0]["main"]["startSpeed"] = {"from": 64, "to": 0, "ease": "linear"}
    speed = _resolved(recipe)["layers"][0]["main"]["startSpeed"]
    assert speed == {"curve": [[0.0, 2.0], [0.25, 1.5], [0.5, 1.0], [0.75, 0.5], [1.0, 0.0]], "mult": 1, "step": False}


def test_rotation_degrees_become_radians(recipe):
    layer = recipe["layers"][0]
    layer["main"]["startRotation"] = {"random": [0, 180]}
    layer["rotationOverLifetime"] = {"z": 90}
    resolved = _resolved(recipe)["layers"][0]
    assert resolved["main"]["startRotation"] == {"random": [0.0, 3.141593]}
    assert resolved["rotationOverLifetime"]["z"] == 1.570796
    assert resolved["shape"]["rotation"] == [-90, 0, 0]
    assert resolved["shape"]["angle"] == 35


def test_defaults_from_profile(recipe):
    del recipe["canvas"]
    resolved = _resolved(recipe)
    assert resolved["canvas"] == {"texels": [64, 64], "scale": 4}
    assert resolved["fps"] == DEFAULTS["fps"]
    assert resolved["light"] == "none"
    assert resolved["ppu"] == 32
    assert resolved["layers"][0]["offset"] == [0.0, 0.0]


def test_lit_layer_defaults_light_global(recipe):
    recipe["layers"][0]["material"] = "lit"
    assert _resolved(recipe)["light"] == "global"


def test_bursts_normalized(recipe):
    recipe["layers"][0]["emission"]["bursts"] = [[0, 18], {"t": 0.1, "n": 2, "cycles": 3}]
    bursts = _resolved(recipe)["layers"][0]["emission"]["bursts"]
    assert bursts == [
        {"t": 0, "n": 18, "cycles": 1, "interval": 0.01},
        {"t": 0.1, "n": 2, "cycles": 3, "interval": 0.01},
    ]
