"""템플릿 층 — 다섯 템플릿 golden · 값 순서 · fixed · when · 더한 폴더 · 템플릿 check."""

import json

import pytest

from conftest import DATA
from vfxtool.errors import VfxError
from vfxtool.material_lib import LIB_DIR
from vfxtool.paths import dump_json
from vfxtool.recipe.check import run_check
from vfxtool.recipe.profile_view import load_profile
from vfxtool.template import expand, frame_checks, load_all

TEMPLATES = ("hit_sparks", "land_dust", "sparkle", "ambient_motes", "heal_rise")
RECIPES = DATA / "recipes"


def _recipe(name):
    return json.loads((RECIPES / f"tpl_{name}.json").read_text(encoding="utf-8"))


def _check(recipe, **kwargs):
    kwargs.setdefault("input_root", DATA)
    return run_check(recipe, RECIPES / "x.json", **kwargs)


def _rules(result):
    return [item["rule"] for item in result.issues]


def _layer(layers, short):
    """펼친 층 목록에서 템플릿 층 이름(점 뒤)으로 찾는다."""
    return next(layer for layer in layers if layer["name"].split(".")[-1] == short)


def _call(**fields):
    layer = {"name": "hit", "template": "hit_sparks"}
    layer.update(fields)
    recipe = _recipe("hit_sparks")
    recipe["layers"] = [layer]
    return recipe


@pytest.mark.parametrize("name", TEMPLATES)
def test_template_golden(name):
    result = _check(_recipe(name))
    assert all(item["severity"] == "info" for item in result.issues), result.issues
    text = dump_json(result.resolved).replace(DATA.resolve().as_posix(), "<DATA>").replace(LIB_DIR.resolve().as_posix(), "<LIB>")
    golden = (DATA / "golden" / f"{name}.resolved.json").read_text(encoding="utf-8")
    assert text == golden


def test_builtin_five_listed():
    assert set(TEMPLATES) <= set(load_all())


def test_order_default_preset_params():
    profile = load_profile(DATA / "profile.json")
    expanded, issues = expand(_call(preset="small", params={"count": 7}), profile)
    main = _layer(expanded["layers"], "sparks")
    assert issues == []
    assert main["emission"]["bursts"] == [[0, 7]]
    assert main["main"]["startSpeed"] == {"random": [27.0, 60]}
    assert main["main"]["gravityModifier"] == 0.6


def test_override_merges_by_template_layer():
    result = _check(_call(override={"sparks": {"main": {"gravityModifier": 1.5}}}))
    assert _layer(result.resolved["layers"], "sparks")["main"]["gravityModifier"] == 1.5


def test_override_on_fixed_is_error():
    assert _rules(_check(_call(override={"sparks": {"blend": "additive"}}))) == ["recipe.fixed"]


def test_bad_params_and_preset():
    result = _check(_call(params={"cout": 3, "speed": 999}, preset="huge"))
    assert _rules(result) == ["recipe.params"] * 3
    assert "'count'" in " ".join(item["detail"] for item in result.issues)


def test_unknown_template_and_extra_call_field():
    assert _rules(_check(_call(template="nope"))) == ["recipe.template_missing"]
    assert _rules(_check(_call(sortOrder=3))) == ["recipe.schema"]


def test_sparkle_sheet_defaults_to_lib_star4():
    # sheet 는 이제 필수가 아니다 — 기본 lib:star4, 파일 시트도 그대로 받는다.
    recipe = _recipe("sparkle")
    twinkle = _check(recipe).resolved["layers"][0]
    assert twinkle["texture"].endswith("/lib/star4.png")
    assert twinkle["blend"] == "additive" and "startFrame" not in twinkle["textureSheet"]
    recipe["layers"][0]["params"] = {"sheet": "sparkle_sheet.png", "size": 5}
    result = _check(recipe)
    assert not [i for i in result.issues if i["severity"] == "error"], result.issues
    assert result.resolved["layers"][0]["texture"].endswith("recipes/sparkle_sheet.png")


def test_when_false_drops_layer():
    recipe = _recipe("heal_rise")
    recipe["layers"][0]["params"]["glow"] = False
    names = [layer["name"] for layer in _check(recipe).resolved["layers"]]
    assert names == ["heal.dots", "heal.rest"]


def test_template_recipe_rules():
    recipe = _recipe("hit_sparks")
    recipe["duration"] = 0.9
    assert _rules(_check(recipe)) == ["template.max_duration"]
    recipe = _recipe("ambient_motes")
    recipe["loop"] = False
    assert _rules(_check(recipe)) == ["template.loop"]


def test_offset_goes_to_every_layer():
    recipe = _recipe("heal_rise")
    recipe["layers"][0]["offset"] = [0, 32]
    layers = _check(recipe).resolved["layers"]
    assert [layer["offset"] for layer in layers] == [[0.0, 1.0]] * 3


def test_extra_folder_wins(tmp_path):
    data = json.loads((DATA.parent.parent / "src" / "vfxtool" / "templates" / "hit_sparks.json").read_text(encoding="utf-8"))
    data["title"] = "게임 쪽"
    (tmp_path / "hit_sparks.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    found = load_all([tmp_path])
    assert found["hit_sparks"]["data"]["title"] == "게임 쪽"
    assert found["hit_sparks"]["source"] == str(tmp_path)
    with pytest.raises(VfxError):
        load_all([tmp_path / "missing"])


def test_frame_checks_listed_for_measure():
    items = frame_checks(_recipe("heal_rise"))
    assert {"rule": "max_luma", "layer": "heal.glow", "args": {"max": 0.95}, "template": "heal_rise"} in items


def test_dotted_recipe_layer_name_finds_template_layers():
    recipe = _call(name="hit.a", override={"sparks": {"emission": {"rateOverTime": 5}}})
    assert _rules(_check(recipe)) == ["template.burst_only"]


def test_override_body_must_be_object():
    assert _rules(_check(_call(override={"sparks": 3}))) == ["recipe.schema"]


def test_int_param_times_factor_stays_int():
    profile = load_profile(DATA / "profile.json")
    expanded, _ = expand(_call(params={"speed": 60}), profile)
    low = _layer(expanded["layers"], "sparks")["main"]["startSpeed"]["random"][0]
    assert low == 27 and isinstance(low, int)


def test_tiles_param_rejects_bool():
    from vfxtool.template_values import type_problem
    assert type_problem({"type": "tiles"}, [True, 2]) is not None


@pytest.mark.parametrize("check", ["oops", [{"rule": 3}], [{"rule": "loop", "args": []}], [{"rule": "loop", "x": 1}]])
def test_bad_template_check_shape(tmp_path, check):
    data = json.loads((DATA.parent.parent / "src" / "vfxtool" / "templates" / "hit_sparks.json").read_text(encoding="utf-8"))
    data["check"] = check
    (tmp_path / "hit_sparks.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(VfxError):
        load_all([tmp_path])


def test_one_color_palette_falls_back_glow_color_to_color(tmp_path):
    # 팔레트가 한 색이면 heal_rise glow_color 기본 p1 이 없다 — color(p0) 로 떨어져 check 가 막히지 않는다.
    profile = tmp_path / "one.json"
    profile.write_text(json.dumps({"version": 1, "palette": ["#80FF80"], "ppu": 32, "pixel_size": [1], "max_colors": 4}), encoding="utf-8")
    result = _check(_recipe("heal_rise"), profile_path=profile)
    assert [i for i in result.issues if i["severity"] == "error"] == [], result.issues
    colors_used = {layer["name"]: layer["main"]["startColor"] for layer in result.resolved["layers"]}
    assert colors_used == {"heal.dots": "#80FF80", "heal.glow": "#80FF80", "heal.rest": "#80FF80"}
    # 레시피가 직접 p1 을 고르면 바꾸지 않고 error 로 알린다.
    recipe = _recipe("heal_rise")
    recipe["layers"][0]["params"]["glow_color"] = "p1"
    assert "recipe.palette" in _rules(_check(recipe, profile_path=profile))


def test_fallback_follows_recipe_color_not_template_default(tmp_path):
    # 1색 팔레트에 레시피가 color 를 직접 고르면 glow_color 도 그 색을 따라간다(템플릿 기본 p0 아님).
    profile = tmp_path / "one.json"
    profile.write_text(json.dumps({"version": 1, "palette": ["#80FF80"], "ppu": 32, "pixel_size": [1], "max_colors": 4}), encoding="utf-8")
    recipe = _recipe("heal_rise")
    recipe["layers"] = [{"name": "heal", "template": "heal_rise", "params": {"color": "#112233"}}]
    result = _check(recipe, profile_path=profile)
    colors_used = {layer["name"]: layer["main"]["startColor"] for layer in result.resolved["layers"]}
    assert colors_used["heal.glow"] == "#112233", result.issues


@pytest.mark.parametrize("fallback", ["glow_color", "nope", "count", 3])
def test_bad_template_fallback(tmp_path, fallback):
    # fallback 은 자기 아닌, 있는 color 파라미터여야 한다.
    data = json.loads((DATA.parent.parent / "src" / "vfxtool" / "templates" / "heal_rise.json").read_text(encoding="utf-8"))
    data["params"]["glow_color"]["fallback"] = fallback
    (tmp_path / "heal_rise.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(VfxError):
        load_all([tmp_path])


def test_hit_sparks_core_off_by_default():
    names = [layer["name"].split(".")[-1] for layer in _check(_call()).resolved["layers"]]
    assert "core" not in names and {"flash", "ring", "sparks"} <= set(names)


def test_hit_sparks_core_color_splits_from_sparks_and_ring_sits_above_core():
    layers = _check(_call(params={"core": True})).resolved["layers"]
    core, ring, sparks, flash = (_layer(layers, n) for n in ("core", "ring", "sparks", "flash"))
    assert core["main"]["startColor"] == "#F0A040" and sparks["main"]["startColor"] == "#FFE08A"
    assert flash["sortOrder"] > ring["sortOrder"] > core["sortOrder"]
    # 칸 가운데 시각((i+0.5)/12) 에서도 0~3 칸이 다 보이게 0 장부터, 수명 = 4장 ÷ 12fps(다시 0 장으로 안 돈다).
    assert ring["textureSheet"]["startFrame"] == 0 and ring["main"]["startLifetime"] == 0.333
    # core_color 를 주면 그 색, 같은 색으로 맞추고 싶으면 color 와 같은 값을 준다.
    picked = _check(_call(params={"core": True, "core_color": "p2"})).resolved["layers"]
    assert _layer(picked, "core")["main"]["startColor"] == "#C04020"


@pytest.mark.parametrize("name", TEMPLATES)
def test_presets_differ_from_defaults(name):
    # 프리셋은 기본값과 다른 칸이 적어도 하나 — 기본과 같은 프리셋은 고르나 마나다.
    template = load_all()[name]["data"]
    defaults = {key: spec["default"] for key, spec in template["params"].items() if "default" in spec}
    for preset, values in template.get("presets", {}).items():
        assert any(defaults.get(key) != value for key, value in values.items()), (name, preset)
