"""profile/extract.py — 기준 PNG 에서 palette · pixel_size 뽑기."""
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from vfxtool.errors import VfxError
from vfxtool.profile.extract import extract

DATA = Path(__file__).parent / "data" / "profile"
# small.png 의 색은 많이 쓰인 순으로 이렇다(텍셀 23 · 11 · 7 · 3 칸).
EXPECTED_PALETTE = ["#E04020", "#F0C040", "#FFFFFF", "#402010"]


def _rules(result) -> list:
    return [issue["rule"] for issue in result["issues"]]


def test_small_png_gives_four_colors_by_use():
    result = extract([DATA / "small.png"])
    assert result["fields"]["palette"] == EXPECTED_PALETTE
    assert result["fields"]["pixel_size"] == [2]
    assert result["metrics"]["used_pixels"] == 44 * 4


def test_block_two_png_warns_upscaled_by_literal_rule():
    # 가장 작은 줄 길이가 2 이상이면 info — 진짜 2px 블록 원본에도 걸려 warn 에서 낮췄다.
    result = extract([DATA / "small.png"])
    assert "profile.upscaled" in _rules(result)
    assert result["metrics"]["min_run"] == 2


def test_upscaled_png_warns_and_reports_bigger_size():
    result = extract([DATA / "small_x3.png"])
    assert result["fields"]["palette"] == EXPECTED_PALETTE
    assert result["fields"]["pixel_size"] == [6]
    assert "profile.upscaled" in _rules(result)


def test_one_to_one_png_has_no_warn():
    result = extract([DATA / "fine.png"])
    assert result["fields"]["pixel_size"] == [1]
    assert result["issues"] == []


def test_gcd_across_several_pngs():
    result = extract([DATA / "small.png", DATA / "fine.png"])
    assert result["fields"]["pixel_size"] == [1]
    assert result["metrics"]["images"] == 2
    assert result["metrics"]["ref_max_colors"] == 4


def _save(path, pixels):
    Image.fromarray(np.array(pixels, dtype=np.uint8), "RGBA").save(path)


def test_rare_color_under_half_percent_is_dropped(tmp_path):
    # 1000 칸 중 4 칸(0.4%)은 빠지고, 6 칸(0.6%)은 남는다.
    base = [[200, 10, 10, 255]] * 996 + [[0, 0, 255, 255]] * 4
    _save(tmp_path / "drop.png", [base])
    assert extract([tmp_path / "drop.png"])["fields"]["palette"] == ["#C80A0A"]

    base = [[200, 10, 10, 255]] * 994 + [[0, 0, 255, 255]] * 6
    _save(tmp_path / "keep.png", [base])
    assert extract([tmp_path / "keep.png"])["fields"]["palette"] == ["#C80A0A", "#0000FF"]


def test_transparent_pixels_are_ignored_and_semi_alpha_keeps_alpha(tmp_path):
    pixels = [[[0, 0, 0, 0], [10, 20, 30, 128], [0, 0, 0, 0], [10, 20, 30, 128]]]
    _save(tmp_path / "semi.png", pixels)
    result = extract([tmp_path / "semi.png"])
    assert result["fields"]["palette"] == ["#0A141E80"]
    assert result["metrics"]["used_pixels"] == 2


def test_fully_transparent_png_gives_empty_palette(tmp_path):
    _save(tmp_path / "empty.png", [[[0, 0, 0, 0]] * 4] * 4)
    result = extract([tmp_path / "empty.png"])
    assert result["fields"]["palette"] == []
    assert "pixel_size" not in result["fields"]


def test_missing_png_is_error(tmp_path):
    with pytest.raises(VfxError):
        extract([tmp_path / "none.png"])


def test_not_a_png_is_error(tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_text("not a png", encoding="utf-8")
    with pytest.raises(VfxError):
        extract([bad])
