"""variant sheet — 작은 가짜 판 폴더(8×8 텍셀)로 overview 격자 크기 · 대표 장 고르기 · FAIL 칸 · strips 12줄 나눔."""

import json

import numpy as np
import pytest
from PIL import Image

from vfxtool import variant_sheet as vs
from vfxtool.errors import VfxError
from vfxtool.sheet import PAD

TEXELS = 8
CELL = (128, 128)   # cell_scale(8) = 16 → 8 × 16


def _frame(size):
    """size×size 텍셀을 덮은 8×8 RGBA."""
    rgba = np.zeros((TEXELS, TEXELS, 4), dtype=np.uint8)
    rgba[:size, :size] = [255, 128, 0, 255]
    return rgba


def _done(folder, sizes, coverage=None):
    """done 판 폴더 — resolved(캔버스 8 · scale 1) · result · frames/ · measure.json."""
    (folder / "frames").mkdir(parents=True)
    frames = []
    for n, size in enumerate(sizes, start=1):
        Image.fromarray(_frame(size), "RGBA").save(folder / "frames" / f"f{n:03d}.png")
        frames.append({"i": n, "t": round(n / 12, 4), "png": f"f{n:03d}.png"})
    (folder / "resolved.json").write_text(json.dumps({"name": folder.name, "canvas": {"texels": [TEXELS, TEXELS], "scale": 1}}), encoding="utf-8")
    (folder / "result.json").write_text(json.dumps({"status": "ok", "frames": frames}), encoding="utf-8")
    measure = {"status": "warn", "issues": [{"severity": "warn", "rule": "x"}], "metrics": {}}
    if coverage is not None:
        measure["metrics"]["coverage"] = coverage
    (folder / "measure.json").write_text(json.dumps(measure), encoding="utf-8")


def _entry(name, attr, tier, k=0, state="done", issues=()):
    return {"name": name, "attr": attr, "tier": tier, "k": k, "seed": 1000 + 16 * k, "state": state,
            "errors": 0, "warns": 0, "issues": list(issues), "notes": [], "seconds": None}


def _set(tmp_path, entries, attrs, tiers, seeds=1):
    out = tmp_path / "hit"
    out.mkdir(exist_ok=True)
    ledger = {"version": 1, "name": "hit", "template": "hit_sparks", "attrs": attrs, "tiers": tiers, "seeds": seeds,
              "settings": {"templates": []}, "source": {}, "variants": entries}
    (out / "set.json").write_text(json.dumps(ledger), encoding="utf-8")
    return out


def _grid(tmp_path):
    out = tmp_path / "hit"
    out.mkdir()
    _done(out / "hit_fire_weak", [1, 3, 2])
    _done(out / "hit_ice_mid", [2] * 14)
    entries = [
        _entry("hit_fire_weak", "fire", "weak"),
        _entry("hit_fire_mid", "fire", "mid", state="failed",
               issues=[{"rule": "variant.tier_range", "severity": "error", "detail": "d"}]),
        _entry("hit_ice_weak", "ice", "weak", state="expanded"),
        _entry("hit_ice_mid", "ice", "mid"),
    ]
    return _set(tmp_path, entries, ["fire", "ice"], ["weak", "mid"])


def test_overview_size_and_cells(tmp_path):
    out = _grid(tmp_path)
    made, issues = vs.make_sheets(out)
    assert issues == []
    names = [path.name for path, _ in made]
    assert names == ["overview.png", "strips_1.png"]
    left = vs.left_width(["fire", "ice"])
    assert made[0][1] == vs.overview_size(2, 2, CELL, left)
    with Image.open(out / "overview.png") as img:
        assert img.size == vs.overview_size(2, 2, CELL, left)
        sheet = img.convert("RGB")
    top = vs.HEADER_H + vs.LABEL_H
    # fire_weak 대표 장 = 3×3 덮은 둘째 장 → 칸 왼쪽 위 48px 이 주황, 그 밖은 검정
    assert sheet.getpixel((left + 10, top + 10)) == (255, 128, 0)
    assert sheet.getpixel((left + 60, top + 60)) == (0, 0, 0)
    # fire_mid 실패 칸 : 대각선 자홍 · 바탕 짙은 회색
    fail_x = left + CELL[0] + PAD
    assert sheet.getpixel((fail_x + 64, top + 64)) == vs.MAGENTA
    assert sheet.getpixel((fail_x + 100, top + 10)) == vs.FAIL_BG
    # ice_weak 안 돈 칸 : 회색
    row2 = top + CELL[1] + vs.LABEL_H + PAD
    assert sheet.getpixel((left + 64, row2 + 64)) == vs.PENDING_BG


def test_strips_one_line_up_to_32_frames(tmp_path):
    out = _grid(tmp_path)
    made, _ = vs.make_sheets(out)
    left = vs.left_width(["hit_fire_weak", "hit_fire_mid", "hit_ice_weak", "hit_ice_mid"])
    expected = vs.strips_size([3, 0, 0, 14], CELL, left)
    assert made[1][1] == expected
    # 줄 : 3장 1줄 + 실패 1줄 + 안 돈 판 1줄 + 14장 1줄(32장 이하라 안 접음) = 4줄, 폭은 14장
    assert expected[1] == vs.LABEL_H + 4 * (CELL[1] + PAD) + PAD
    assert expected[0] == left + 14 * (CELL[0] + PAD) + PAD


def test_strips_fold_over_32_frames():
    assert (vs.strip_columns(32), vs.strip_lines(32)) == (32, 1)
    assert (vs.strip_columns(33), vs.strip_lines(33)) == (12, 3)
    assert vs.strips_size([40, 5], CELL, 10) == (10 + 12 * (CELL[0] + PAD) + PAD, vs.LABEL_H + 5 * (CELL[1] + PAD) + PAD)  # 40장 4줄 + 5장 1줄


def test_pick_frame_largest_coverage_first_on_tie():
    frames = [_frame(1), _frame(3), _frame(3), _frame(2)]
    assert vs.pick_frame(frames) == 1
    assert vs.pick_frame(frames, [0.1, 0.5, 0.9, 0.2]) == 2
    assert vs.pick_frame(frames, [0.1, 0.2]) == 1   # 길이가 안 맞는 measure 값은 버리고 직접 잰다


def test_measure_coverage_chooses_frame(tmp_path):
    out = tmp_path / "hit"
    out.mkdir()
    _done(out / "hit_fire_mid", [1, 3, 2], coverage=[0.0, 1.0, 9.0])
    shot = vs.load_variant(out, "hit_fire_mid")
    assert shot.best == 2
    assert shot.counts == (0, 1)


def test_thirteen_variants_make_two_strips_and_clear_old(tmp_path):
    entries = [_entry(f"hit_a{n:02d}_mid", f"a{n:02d}", "mid", state="expanded") for n in range(13)]
    out = _set(tmp_path, entries, [e["attr"] for e in entries], ["mid"])
    (out / "strips_3.png").write_bytes(b"old")
    made, _ = vs.make_sheets(out)
    assert [path.name for path, _ in made] == ["overview.png", "strips_1.png", "strips_2.png"]
    assert not (out / "strips_3.png").exists()
    left = vs.left_width([e["attr"] for e in entries])
    assert made[0][1] == vs.overview_size(13, 1, (128, 128), left)   # done 판이 없으면 64 텍셀 → 128


def test_broken_done_variant_becomes_blank_with_warn(tmp_path):
    out = _set(tmp_path, [_entry("hit_fire_mid", "fire", "mid")], ["fire"], ["mid"])
    (out / "hit_fire_mid").mkdir()
    made, issues = vs.make_sheets(out)
    assert [i["rule"] for i in issues] == ["variant.sheet"]
    assert made[0][0].is_file()


def test_bad_variant_name_in_ledger_is_refused(tmp_path):
    out = _set(tmp_path, [_entry("../evil", "fire", "mid")], ["fire"], ["mid"])
    with pytest.raises(VfxError, match="판 이름"):
        vs.make_sheets(out)
