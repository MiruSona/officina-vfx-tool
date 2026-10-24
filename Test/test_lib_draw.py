"""기하 소재 생성기 — 결정성 · 저장소 PNG 와 픽셀 같음 · 흰 1단 · 빈 칸 RGB 0 · 칸 크기 = 메타 · bolt32 밝기 4단 · paint_tones."""

import numpy as np
import pytest
from PIL import Image

from vfxtool import lib_draw
from vfxtool.material_lib import LIB_DIR, load

DRAWN = ("dot", "cross", "star4", "disc", "ring", "shard", "streak", "bolt32")
WHITE = tuple(name for name in DRAWN if name != "bolt32")  # 흰 1단 · 홀수 칸


def _pixels(path):
    with Image.open(path) as image:
        return np.array(image.convert("RGBA"))


def test_eight_names():
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


@pytest.mark.parametrize("name", WHITE)
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


def _bolt_frames():
    sheet = lib_draw.render("bolt32")
    return sheet, [sheet[:, k * 32:(k + 1) * 32] for k in range(8)]


def test_bolt32_frames():
    sheet, frames = _bolt_frames()
    assert sheet.shape == (32, 256, 4)
    alpha = sheet[..., 3] > 0
    assert set(np.unique(sheet[..., 0][alpha])) <= {63, 127, 191, 255}
    assert np.all(sheet[~alpha] == 0)
    counts = [int((f[..., 3] > 0).sum()) for f in frames]
    for frame in frames:
        painted = frame[..., 3] > 0
        # 가운데 16열(x 8~23)에만 그린다
        assert not painted[:, :8].any() and not painted[:, 24:].any()
        if painted.any():
            xs = np.nonzero(painted)[1]
            assert abs(xs.mean() - 15.5) <= 1.5, xs.mean()
        assert len(np.unique(frame[..., 0][painted])) <= 4
    peak = frames[1]
    assert (peak[0, :, 3] > 0).any() and (peak[31, :, 3] > 0).any()
    core = (peak[..., 3] > 0) & (peak[..., 0] == 255)
    assert core.sum(axis=1).min() >= 2
    assert min(counts[1], counts[2]) >= 1.3 * counts[3]
    assert counts[3] > counts[4] > counts[5] > counts[6] > counts[7] > 0
    assert counts[1] >= 2 * counts[0]


def test_paint_tones():
    ramp = ["#FFFFFF", "#FFF3A0", "#FFD23F", "#E8892B"]
    grey = np.zeros((1, 5, 4), dtype=np.uint8)
    for x, value in enumerate((255, 191, 127, 63)):
        grey[0, x] = (value, value, value, 255)
    painted = lib_draw.paint_tones(grey, ramp)
    assert ["#%02X%02X%02X" % tuple(p[:3]) for p in painted[0, :4]] == ramp
    assert np.all(painted[0, :4, 3] == 255) and np.all(painted[0, 4] == 0)
    short = lib_draw.paint_tones(grey, ramp[:3])
    assert "#%02X%02X%02X" % tuple(short[0, 3, :3]) == ramp[2]  # 단 3 → 끝 색
    white = _pixels(LIB_DIR / "disc.png")
    painted = lib_draw.paint_tones(white, ramp)
    opaque = white[..., 3] > 0
    assert np.all(painted[opaque][:, :3] == (255, 255, 255)) and np.all(painted[~opaque] == 0)


def test_build_only_unknown_is_error(tmp_path):
    assert lib_draw.build(tmp_path, only="disc") == ["disc"]
    with pytest.raises(ValueError):
        lib_draw.build(tmp_path, only="puff8")
