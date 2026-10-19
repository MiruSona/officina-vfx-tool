"""기하 소재 생성기 — 결정성 · 저장소 PNG 와 픽셀 같음 · 흰 1단 · 빈 칸 RGB 0 · 칸 크기 = 메타."""

import numpy as np
import pytest
from PIL import Image

from vfxtool import lib_draw
from vfxtool.material_lib import LIB_DIR, load

DRAWN = ("dot", "cross", "star4", "disc", "ring", "shard", "streak")


def _pixels(path):
    with Image.open(path) as image:
        return np.array(image.convert("RGBA"))


def test_seven_names():
    assert lib_draw.names() == sorted(DRAWN)


def test_build_twice_same_pixels_and_matches_repo(tmp_path):
    first = tmp_path / "a"
    second = tmp_path / "b"
    lib_draw.build(first)
    lib_draw.build(second)
    for name in DRAWN:
        a = _pixels(first / f"{name}.png")
        assert np.array_equal(a, _pixels(second / f"{name}.png"))
        assert np.array_equal(a, _pixels(LIB_DIR / f"{name}.png")), name
        assert (first / f"{name}.json").read_text(encoding="utf-8") == (LIB_DIR / f"{name}.json").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", DRAWN)
def test_white_binary_and_cell_matches_meta(name):
    pixels = _pixels(LIB_DIR / f"{name}.png")
    alpha = pixels[..., 3]
    assert set(np.unique(alpha)) <= {0, 255}
    assert np.all(pixels[alpha == 0][:, :3] == 0)
    assert np.all(pixels[alpha == 255][:, :3] == 255)
    meta = load(name)
    assert pixels.shape[:2] == (meta["cell"] * meta["rows"], meta["cell"] * meta["frames"])
    assert meta["cell"] % 2 == 1


def test_art_matches_design_samples():
    dot = lib_draw.render("dot")[..., 3] > 0
    assert dot[0:3].sum() == 1 and dot[1, 1]
    assert dot[6:9].sum() == 5
    star = lib_draw.render("star4")[..., 3] > 0
    assert star[:, 14:21].sum() == 17
    disc = lib_draw.render("disc")[..., 3] > 0
    assert disc.sum() == 37


def test_ring_frames_symmetric():
    ring = lib_draw.render("ring")[..., 3] > 0
    frames = [ring[:, k * 15:(k + 1) * 15] for k in range(4)]
    for frame in frames[:2] + frames[3:]:
        assert np.array_equal(frame, frame[::-1, :]) and np.array_equal(frame, frame[:, ::-1])
    assert frames[3].sum() == 4 and frames[3][0, 7] and frames[3][7, 14]
    assert 0 < frames[2].sum() < lib_draw.midpoint_circle(7, (7, 7)).__len__()


def test_build_only_unknown_is_error(tmp_path):
    assert lib_draw.build(tmp_path, only="disc") == ["disc"]
    with pytest.raises(ValueError):
        lib_draw.build(tmp_path, only="puff8")
