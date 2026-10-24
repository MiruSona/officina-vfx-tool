"""램프 굽기 — ramp:<소재> 치환 → 판 tex/ 램프 PNG · color 짝 흰색 · tiles override · --lib-src 없음 · sha256 다름 · 속성마다 한 번."""

import hashlib
import json

import numpy as np
import pytest
from PIL import Image

from conftest import write_set
from vfxtool import lib_cut
from vfxtool.variant_expand import expand_set

FRAMES = 5
CELL = 16


@pytest.fixture
def fake_source(tmp_path, monkeypatch):
    """burst16 자리의 작은 가짜 원본(16 × 5장 띠) — sources.json 항목은 이 파일 sha256 으로 바꿔 끼운다."""
    src = tmp_path / "src"
    src.mkdir()
    strip = np.zeros((CELL, CELL * FRAMES, 4), dtype=np.uint8)
    for index in range(FRAMES):
        strip[4:12, index * CELL + 4:index * CELL + 12] = (200 - index * 30, 120, 60, 255)
    path = src / "fake_burst.png"
    Image.fromarray(strip, "RGBA").save(path)
    entry = {"file": path.name, "title": "t", "author": "a", "url": "u", "license": "CC0 1.0",
             "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "src_cell": CELL, "src_frames": FRAMES,
             "cell": CELL, "window": [0, 0], "blend": "alpha"}
    monkeypatch.setattr(lib_cut, "load_sources", lambda path=None: {"burst16": entry})
    return src


def _game_fire(tmp_path):
    folder = tmp_path / "dicts"
    folder.mkdir()
    data = {"version": 1, "name": "fire", "palette": ["#FFF4A3", "#FFC23D", "#F2751A", "#C2321F", "#5E1914"],
            "materials": {"lib:burst16": "ramp:burst16"}, "ramp": ["p0", "p1", "p2", "p3"]}
    (folder / "fire.json").write_text(json.dumps(data), encoding="utf-8")
    return folder


def _expand(tmp_path, lib_src):
    path = write_set(tmp_path / "in", params={"core": True}, attrs=["fire", "ice"], tiers=["weak", "mid", "strong"], seeds=1)
    return expand_set(path, tmp_path / "work", [_game_fire(tmp_path)], lib_src=lib_src)


def test_ramp_baked_into_variant_tex(tmp_path, fake_source):
    _, ledger = _expand(tmp_path, fake_source)
    states = {entry["name"]: entry["state"] for entry in ledger["variants"]}
    assert set(states.values()) == {"expanded"}, ledger["variants"]
    variant = tmp_path / "work" / "hit" / "hit_fire_mid"
    png = variant / "tex" / "burst16_ramp.png"
    assert Image.open(png).size == (CELL * FRAMES, CELL)
    layer = json.loads((variant / "recipe.json").read_text(encoding="utf-8"))["layers"][0]
    assert layer["params"]["core_tex"] == "tex/burst16_ramp.png"
    assert layer["params"]["core_color"] == "#FFFFFF"
    assert layer["params"]["core_size"] == CELL
    assert layer["override"] == {"core": {"textureSheet": {"tiles": [FRAMES, 1]}}}
    assert not (tmp_path / "work" / "hit" / "hit_ice_mid" / "tex").exists()


def test_ramp_colors_come_from_attr_palette(tmp_path, fake_source):
    _expand(tmp_path, fake_source)
    pixels = np.array(Image.open(tmp_path / "work" / "hit" / "hit_fire_weak" / "tex" / "burst16_ramp.png"))
    found = {"#%02X%02X%02X" % tuple(p[:3]) for p in pixels.reshape(-1, 4) if p[3]}
    assert found <= {"#FFF4A3", "#FFC23D", "#F2751A", "#C2321F"}


def test_no_lib_src_fails_only_ramp_variants(tmp_path, fake_source):
    _, ledger = _expand(tmp_path, None)
    for entry in ledger["variants"]:
        if entry["attr"] == "fire":
            assert entry["state"] == "failed"
            assert entry["issues"][0]["rule"] == "variant.ramp_source"
        else:
            assert entry["state"] == "expanded"


def test_sha_mismatch_fails(tmp_path, fake_source):
    (fake_source / "fake_burst.png").write_bytes(b"not the same file")
    _, ledger = _expand(tmp_path, fake_source)
    fire = [entry for entry in ledger["variants"] if entry["attr"] == "fire"]
    assert all(entry["state"] == "failed" for entry in fire)
    assert "sha256" in fire[0]["issues"][0]["detail"]


def test_baked_once_per_attr(tmp_path, fake_source, monkeypatch):
    calls = []
    real = lib_cut.cut_ramp

    def counting(*args, **kwargs):
        calls.append(args[1])
        return real(*args, **kwargs)

    monkeypatch.setattr(lib_cut, "cut_ramp", counting)
    _expand(tmp_path, fake_source)
    assert calls == ["burst16"]
    pngs = sorted((tmp_path / "work" / "hit").glob("hit_fire_*/tex/burst16_ramp.png"))
    assert len(pngs) == 3
    assert len({png.read_bytes() for png in pngs}) == 1


def test_drawn_material_ramp_without_lib_src(tmp_path):
    """만든 소재(bolt32) × 내장 lightning — --lib-src 없이 lib PNG 밝기 단을 램프 번호대로 칠한다."""
    path = write_set(tmp_path / "in", template="lightning_strike", name="strike", duration=0.75, params={},
                     attrs=["lightning"], tiers=["mid"], seeds=1)
    _, ledger = expand_set(path, tmp_path / "work", lib_src=None)
    entry = ledger["variants"][0]
    assert entry["state"] == "expanded", entry["issues"]
    variant = tmp_path / "work" / "strike" / "strike_lightning_mid"
    pixels = np.array(Image.open(variant / "tex" / "bolt32_ramp.png").convert("RGBA"))
    assert pixels.shape == (32, 256, 4)
    ramp = ["#FFFFFF", "#FFF3A0", "#FFD240", "#E8892A"]  # lightning p0~p3
    grey = np.array(Image.open(lib_cut.LIB_DIR / "bolt32.png").convert("RGBA"))
    opaque = grey[..., 3] > 0
    assert np.array_equal(opaque, pixels[..., 3] > 0)
    for value, hexa in zip((255, 191, 127, 63), ramp):
        found = {"#%02X%02X%02X" % tuple(p[:3]) for p in pixels[opaque & (grey[..., 0] == value)]}
        assert found == {hexa}, (value, found)
    layer = json.loads((variant / "recipe.json").read_text(encoding="utf-8"))["layers"][0]
    assert layer["params"]["bolt_tex"] == "tex/bolt32_ramp.png"
    assert layer["params"]["color"] == "#FFFFFF"
    assert layer["params"]["bolt_size"] == 32
    assert layer["override"] == {"bolt": {"textureSheet": {"tiles": [8, 1]}}}


def _strike_with(tmp_path, material):
    """lightning_strike × 내 사전 zap — lib:bolt32 를 ramp:<material> 로 바꾼다."""
    folder = tmp_path / "dicts"
    folder.mkdir()
    data = {"version": 1, "name": "zap", "palette": ["#FFFFFF", "#FFF3A0", "#FFD240", "#E8892A"],
            "materials": {"lib:bolt32": f"ramp:{material}"}, "ramp": ["p0", "p1", "p2", "p3"]}
    (folder / "zap.json").write_text(json.dumps(data), encoding="utf-8")
    path = write_set(tmp_path / "in", template="lightning_strike", name="strike", duration=0.75, params={},
                     attrs=["zap"], tiers=["mid"], seeds=1)
    _, ledger = expand_set(path, tmp_path / "work", [folder], lib_src=None)
    return ledger["variants"][0]


def test_ramp_unknown_material_fails(tmp_path):
    entry = _strike_with(tmp_path, "nope")
    assert entry["state"] == "failed"
    assert entry["issues"][0]["rule"] == "variant.ramp_source"


def test_ramp_drawn_grain_fails(tmp_path):
    """만든 소재라도 grain(dot)은 bolt32 플립북 자리에 못 들어간다."""
    entry = _strike_with(tmp_path, "dot")
    assert entry["state"] == "failed"
    assert entry["issues"][0]["rule"] == "variant.material"
