"""frames.py — result.json 읽기 · 텍셀 줄이기 · 흑백 짝 알파 복원."""
import shutil
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from vfxtool import frames
from vfxtool.errors import VfxError

DATA = Path(__file__).parent / "data" / "frames" / "round_1"


def _copy_round(tmp_path):
    target = tmp_path / "synth_dots" / "round_1"
    shutil.copytree(DATA, target)
    return target


def test_load_frames_order_and_shape():
    result = frames.load_result(DATA)
    loaded = frames.load_frames(DATA, result)
    assert [f.i for f in loaded] == list(range(1, 9))
    assert loaded[0].rgba.shape == (64, 64, 4)
    assert loaded[0].t == pytest.approx(1 / 12, abs=1e-3)


def test_round_info_from_resolved():
    result = frames.load_result(DATA)
    info = frames.load_round(DATA, result, frames.load_resolved(DATA))
    assert info.name == "synth_dots"
    assert info.round_no == 1
    assert info.texels == (16, 16)
    assert info.scale == 4
    assert info.seed == 7
    assert info.loop is False


def test_to_texels_takes_cell_center():
    result = frames.load_result(DATA)
    first = frames.load_frames(DATA, result)[0]
    tex = frames.to_texels(first.rgba, 4, (16, 16))
    assert tex.shape == (16, 16, 4)
    covered = np.argwhere(tex[..., 3] > 0)
    assert sorted({int(c) for c in covered[:, 1]}) == [3, 4]
    assert sorted({int(r) for r in covered[:, 0]}) == [7, 8]


def test_recover_alpha_from_black_white_pair():
    color = np.array([200, 100, 50], dtype=np.float64)
    alpha = 0.5
    black = np.zeros((2, 2, 4), dtype=np.uint8)
    white = np.zeros((2, 2, 4), dtype=np.uint8)
    black[..., :3] = np.round(color * alpha)
    white[..., :3] = np.round(color * alpha + 255 * (1 - alpha))
    black[1, 1, :3] = 0
    white[1, 1, :3] = 255
    rgba = frames.recover_alpha(black, white)
    assert abs(int(rgba[0, 0, 3]) - 128) <= 1
    assert np.all(np.abs(rgba[0, 0, :3].astype(int) - color.astype(int)) <= 2)
    assert tuple(rgba[1, 1]) == (0, 0, 0, 0)


def test_load_frames_uses_bw_pair_when_asked(tmp_path):
    round_dir = _copy_round(tmp_path)
    black = np.zeros((64, 64, 4), dtype=np.uint8)
    white = np.full((64, 64, 4), 255, dtype=np.uint8)
    black[..., 3] = 255
    black[0:4, 0:4, :3] = 255
    Image.fromarray(black, "RGBA").save(round_dir / "frames" / "f001_k.png")
    Image.fromarray(white, "RGBA").save(round_dir / "frames" / "f001_w.png")
    result = frames.load_result(round_dir)
    plain = frames.load_frames(round_dir, result)
    paired = frames.load_frames(round_dir, result, use_bw=True)
    assert int(plain[0].rgba[1, 1, 3]) == 0
    assert tuple(paired[0].rgba[1, 1]) == (255, 255, 255, 255)
    assert int(paired[0].rgba[30, 30, 3]) == 0
    assert np.array_equal(plain[1].rgba, paired[1].rgba)


def test_missing_result_is_vfx_error(tmp_path):
    with pytest.raises(VfxError):
        frames.load_result(tmp_path)


def test_missing_png_is_vfx_error(tmp_path):
    round_dir = _copy_round(tmp_path)
    (round_dir / "frames" / "f004.png").unlink()
    with pytest.raises(VfxError):
        frames.load_frames(round_dir, frames.load_result(round_dir))


def test_cell_scale_and_interval():
    assert frames.cell_scale((64, 64)) == 2
    assert frames.cell_scale((16, 16)) == 8
    loaded = frames.load_frames(DATA, frames.load_result(DATA))
    assert frames.frame_interval(loaded) == pytest.approx(1 / 12, abs=1e-3)
