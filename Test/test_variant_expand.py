"""변형 묶음 펼치기 — 결정성 · 이름 · 시드 · 실패 표시(자르지 않음) · 판 수 상한 · base · 게임 파일 텍스처."""

import json
import shutil

import pytest

from conftest import DATA, write_set
from vfxtool.errors import VfxError
from vfxtool.variant_expand import expand_set

TEMPLATES = ("hit_sparks", "land_dust", "ambient_motes", "heal_rise", "sparkle", "lightning_strike")


def _expand(tmp_path, variant_dirs=(), **fields):
    path = write_set(tmp_path / "in", **fields)
    return expand_set(path, tmp_path / "work", variant_dirs)


def _by_name(ledger):
    return {entry["name"]: entry for entry in ledger["variants"]}


def _recipe(tmp_path, set_name, variant):
    return json.loads((tmp_path / "work" / set_name / variant / "recipe.json").read_text(encoding="utf-8"))


def _dict_dir(tmp_path, name, palette, materials=None, params=None):
    folder = tmp_path / "dicts"
    folder.mkdir(exist_ok=True)
    data = {"version": 1, "name": name, "palette": palette, "materials": materials or {}}
    if params is not None:
        data["params"] = params
    (folder / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
    return folder


def _tree(folder):
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


def test_deterministic(tmp_path):
    path = write_set(tmp_path / "in")
    expand_set(path, tmp_path / "a")
    expand_set(path, tmp_path / "b")
    first, second = _tree(tmp_path / "a" / "hit"), _tree(tmp_path / "b" / "hit")
    assert len(first) == 1 + 12 * 2
    assert first == second


def test_names_and_seeds(tmp_path):
    ledger_path, ledger = _expand(tmp_path)
    names = [entry["name"] for entry in ledger["variants"]]
    assert names[:3] == ["hit_fire_weak_s0", "hit_fire_weak_s1", "hit_fire_mid_s0"]
    assert names[-1] == "hit_ice_strong_s1"
    for entry in ledger["variants"]:
        assert entry["seed"] == 1000 + entry["k"] * 16
        assert entry["state"] == "expanded", entry
        assert _recipe(tmp_path, "hit", entry["name"])["seed"] == entry["seed"]
    assert ledger_path.name == "set.json"


def test_one_seed_has_no_suffix(tmp_path):
    _, ledger = _expand(tmp_path, seeds=1)
    assert [entry["name"] for entry in ledger["variants"]][:2] == ["hit_fire_weak", "hit_fire_mid"]


def test_tier_values_and_mid_is_template_default(tmp_path):
    _, ledger = _expand(tmp_path, attrs=["base"], seeds=1)
    weak = _recipe(tmp_path, "hit", "hit_base_weak")["layers"][0]["params"]
    mid = _recipe(tmp_path, "hit", "hit_base_mid")["layers"][0]["params"]
    strong = _recipe(tmp_path, "hit", "hit_base_strong")["layers"][0]["params"]
    assert (weak["count"], weak["speed"], weak["life"]) == (3, 63.0, 0.4)
    assert mid == {"ring": True}
    assert (strong["count"], strong["speed"], strong["life"]) == (12, 117.0, 0.6)


def test_name_over_40_fails_only_that_variant(tmp_path):
    _, ledger = _expand(tmp_path, name="a" * 24, attrs=["lightning"], tiers=["weak", "strong"], seeds=1)
    entries = _by_name(ledger)
    long_name = "a" * 24 + "_lightning_strong"
    assert entries[long_name]["state"] == "failed"
    assert entries[long_name]["issues"][0]["rule"] == "variant.name"
    assert entries["a" * 24 + "_lightning_weak"]["state"] == "expanded"
    assert (tmp_path / "work" / ("a" * 24) / long_name / "recipe.json").is_file()


def test_duplicate_tier_name_exits(tmp_path):
    with pytest.raises(VfxError, match="겹친다"):
        _expand(tmp_path, tiers=["mid", {"name": "mid", "mul": {}}])
    assert not (tmp_path / "work").exists()


def test_too_many_variants_exits(tmp_path):
    tiers = ["weak", "mid", "strong", {"name": "huge", "mul": {"count": 3}}]
    with pytest.raises(VfxError, match="48"):
        _expand(tmp_path, attrs=["fire", "ice", "poison", "lightning"], tiers=tiers, seeds=4)


def test_tier_range_is_not_clipped(tmp_path):
    _, ledger = _expand(tmp_path, attrs=["fire"], tiers=[{"name": "huge", "mul": {"life": 1.5}}], seeds=1)
    entry = _by_name(ledger)["hit_fire_huge"]
    assert entry["state"] == "failed"
    assert entry["issues"][0]["rule"] == "variant.tier_range"
    assert "0.75" in entry["issues"][0]["detail"]
    assert _recipe(tmp_path, "hit", "hit_fire_huge")["layers"][0]["params"]["life"] == 0.75


def test_scale_multiplies_size_pairs(tmp_path):
    _, ledger = _expand(tmp_path, attrs=["fire"], tiers=[{"name": "big2", "mul": {}, "scale": 2}], seeds=1)
    params = _recipe(tmp_path, "hit", "hit_fire_big2")["layers"][0]["params"]
    assert params["sparks_tex"] == "lib:dot" and params["sparks_size"] == 6
    assert params["ring_size"] == 30 and params["flash_size"] == 14
    assert ledger["variants"][0]["state"] == "expanded", ledger["variants"][0]["issues"]


def test_palette_short(tmp_path):
    folder = _dict_dir(tmp_path, "mono", ["#FFFFFF"])
    _, ledger = _expand(tmp_path, [folder], template="land_dust", name="dust", duration=1.0, params={}, attrs=["mono"], tiers=["mid"], seeds=1)
    entry = ledger["variants"][0]
    assert entry["state"] == "failed"
    assert entry["issues"][0]["rule"] == "variant.palette_short"


@pytest.mark.parametrize("right", ["lib:ring", "lib:nope"])
def test_material_kind_tiles_or_unknown(tmp_path, right):
    folder = _dict_dir(tmp_path, "odd", ["#FFFFFF", "#888888"], {"lib:shard": right})
    _, ledger = _expand(tmp_path, [folder], attrs=["odd"], tiers=["mid"], seeds=1)
    entry = ledger["variants"][0]
    assert entry["state"] == "failed"
    assert entry["issues"][0]["rule"] == "variant.material"


def test_check_error_passes_through(tmp_path):
    _, ledger = _expand(tmp_path, attrs=["fire"], tiers=["mid"], seeds=1, duration=0.9)
    entry = ledger["variants"][0]
    assert entry["state"] == "failed"
    assert entry["issues"][0]["rule"] == "variant.check"
    assert any(item["rule"] == "template.max_duration" for item in entry["issues"][1:])


def test_base_keeps_profile_palette(tmp_path):
    _, ledger = _expand(tmp_path, attrs=["base"], tiers=["mid"], seeds=1)
    copied = json.loads((tmp_path / "work" / "hit" / "hit_base_mid" / "profile.json").read_text(encoding="utf-8"))
    assert copied == json.loads((DATA / "profile.json").read_text(encoding="utf-8"))
    assert ledger["variants"][0]["state"] == "expanded"


def test_unused_material_note(tmp_path):
    _, ledger = _expand(tmp_path, template="ambient_motes", name="motes", duration=1.0, params={}, attrs=["fire"], tiers=["mid"], seeds=1)
    entry = ledger["variants"][0]
    assert entry["state"] == "expanded", entry["issues"]
    assert [item["detail"] for item in entry["notes"]] == ["안 쓴 치환 lib:shard"]
    assert _recipe(tmp_path, "motes", "motes_fire_mid")["loop"] is True


@pytest.mark.parametrize("name", TEMPLATES)
def test_builtin_dicts_and_tiers_expand_clean(tmp_path, name):
    """기본 사전 넷 × 기본 세기 셋이 다섯 템플릿 모두에서 범위 · 소재 · check 를 통과한다. duration 은 안 적어 기본값을 쓴다."""
    path = write_set(tmp_path / "in", template=name, name="fx", params={}, attrs=["fire", "ice", "poison", "lightning"], seeds=1)
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["duration"]
    path.write_text(json.dumps(data), encoding="utf-8")
    _, ledger = expand_set(path, tmp_path / "work")
    failed = {entry["name"]: entry["issues"] for entry in ledger["variants"] if entry["state"] != "expanded"}
    assert failed == {}


def test_game_texture_copied(tmp_path):
    folder = tmp_path / "in"
    folder.mkdir()
    shutil.copyfile(DATA / "recipes" / "sparkle_sheet.png", folder / "my_sheet.png")
    fields = {"template": "sparkle", "name": "sp", "duration": 1.0, "attrs": ["fire"], "tiers": ["mid"], "seeds": 1,
              "params": {"sheet": "my_sheet.png", "tiles": [4, 1], "size": 5}}
    _, ledger = _expand(tmp_path, **fields)
    entry = ledger["variants"][0]
    assert entry["state"] == "expanded", entry["issues"]
    variant = tmp_path / "work" / "sp" / "sp_fire_mid"
    assert (variant / "tex" / "sheet.png").read_bytes() == (folder / "my_sheet.png").read_bytes()
    assert _recipe(tmp_path, "sp", "sp_fire_mid")["layers"][0]["params"]["sheet"] == "tex/sheet.png"


def test_game_texture_outside_root_exits(tmp_path):
    shutil.copyfile(DATA / "recipes" / "sparkle_sheet.png", tmp_path / "outside.png")
    with pytest.raises(VfxError, match="밖"):
        _expand(tmp_path, template="sparkle", name="sp", duration=1.0, params={"sheet": "../outside.png"}, tiers=["mid"])


def test_existing_folder_refused_without_force(tmp_path):
    path = write_set(tmp_path / "in")
    expand_set(path, tmp_path / "work")
    with pytest.raises(VfxError, match="--force"):
        expand_set(path, tmp_path / "work")


FIVE = ["#FFFFFF", "#DDDDDD", "#BBBBBB", "#999999", "#777777"]


def test_dict_params_applied(tmp_path):
    """기본 사전 params(color p2)가 판 레시피에 들어간다 — 템플릿 기본 p0 을 이긴다."""
    _, ledger = _expand(tmp_path, params={}, attrs=["fire"], tiers=["mid"], seeds=1)
    assert ledger["variants"][0]["state"] == "expanded", ledger["variants"][0]["issues"]
    assert _recipe(tmp_path, "hit", "hit_fire_mid")["layers"][0]["params"]["color"] == "p2"


def test_set_params_beat_dict_params(tmp_path):
    """겹침 순서 : 묶음 params > 사전 params > 템플릿 기본."""
    folder = _dict_dir(tmp_path, "grey", FIVE, params={"color": "p2", "count": 10})
    _, ledger = _expand(tmp_path, [folder], params={"color": "p4"}, attrs=["grey"], tiers=["mid"], seeds=1)
    assert ledger["variants"][0]["state"] == "expanded", ledger["variants"][0]["issues"]
    params = _recipe(tmp_path, "hit", "hit_grey_mid")["layers"][0]["params"]
    assert params["color"] == "p4"
    assert params["count"] == 10


def test_base_ignores_dict_params(tmp_path):
    _, ledger = _expand(tmp_path, params={}, attrs=["base"], tiers=["mid"], seeds=1)
    assert "color" not in _recipe(tmp_path, "hit", "hit_base_mid")["layers"][0]["params"]
    assert ledger["variants"][0]["notes"] == []


def test_unused_param_note(tmp_path):
    folder = _dict_dir(tmp_path, "grey", FIVE, params={"color": "p2", "glow_color": "p1"})
    _, ledger = _expand(tmp_path, [folder], params={}, attrs=["grey"], tiers=["mid"], seeds=1)
    entry = ledger["variants"][0]
    assert entry["state"] == "expanded", entry["issues"]
    assert [(item["rule"], item["severity"], item["detail"]) for item in entry["notes"]] == [("variant.unused_param", "info", "안 쓴 파라미터 glow_color")]


def test_dict_param_bad_value_fails_variant(tmp_path):
    folder = _dict_dir(tmp_path, "grey", FIVE, params={"color": 3})
    _, ledger = _expand(tmp_path, [folder], params={}, attrs=["grey"], tiers=["mid"], seeds=1)
    entry = ledger["variants"][0]
    assert entry["state"] == "failed"
    assert entry["issues"][0]["rule"] == "variant.param"


def test_interrupted_expand_leaves_ledger_for_force(tmp_path, monkeypatch):
    """판 폴더를 쓰다 끊겨도 set.json(모두 expanded)이 먼저 있어 --force 로 이어 펼친다."""
    from vfxtool import variant_expand

    path = write_set(tmp_path / "in", attrs=["fire"], tiers=["weak", "mid"], seeds=1)
    real = variant_expand._write_or_error

    def interrupted(draft, ctx):
        raise KeyboardInterrupt

    monkeypatch.setattr(variant_expand, "_write_or_error", interrupted)
    with pytest.raises(KeyboardInterrupt):
        expand_set(path, tmp_path / "work")
    ledger = json.loads((tmp_path / "work" / "hit" / "set.json").read_text(encoding="utf-8"))
    assert {e["state"] for e in ledger["variants"]} == {"expanded"}
    monkeypatch.setattr(variant_expand, "_write_or_error", real)
    _, ledger = expand_set(path, tmp_path / "work", force=True)
    assert len(ledger["variants"]) == 2
    assert (tmp_path / "work" / "hit" / "hit_fire_mid" / "recipe.json").is_file()
