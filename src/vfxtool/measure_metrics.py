"""프레임 한 장의 지표 계산(설계 8-2 표). 규칙 판정은 measure_rules 가 한다.

배경은 투명(알파 0)이다. 「덮은 칸」= 알파 > 0 인 텍셀.
"""

from collections import Counter

import numpy as np

from vfxtool.frames import to_texels

BRIGHT_LUMA = 0.98
# 「팔레트 안」 RGB 거리 — palette_out · frame.palette · sheet 겹침이 같이 쓴다. Linear 꼭짓점 색 8비트 반올림 흡수(최대 3.74).
# 근거는 변형묶음설계 「구현 뒤 정정」 표.
PALETTE_TOLERANCE = 4.0


def parse_hex(text):
    """'#RRGGBB(AA)' → (r, g, b). 알파는 버린다."""
    value = str(text).lstrip("#")
    if len(value) not in (6, 8):
        raise ValueError(f"hex 색이 아니다 — {text}")
    return tuple(int(value[k:k + 2], 16) for k in (0, 2, 4))


def covered_mask(texel_rgba):
    return texel_rgba[..., 3] > 0


def unique_colors(texel_rgba):
    """덮은 칸의 고유 RGB 집합(int 튜플)."""
    rgb = texel_rgba[covered_mask(texel_rgba)][:, :3]
    return {tuple(int(c) for c in row) for row in np.unique(rgb, axis=0)}


def grid_ratio(rgba, scale):
    """원본 해상도에서 색 경계 좌표 중 scale 배수에 놓인 비율. 경계가 없으면 1.0(실측 2-A 지표 ①)."""
    flat = rgba.astype(np.int32)
    diff_x = np.any(flat[:, 1:] != flat[:, :-1], axis=2)
    diff_y = np.any(flat[1:, :] != flat[:-1, :], axis=2)
    xs = np.nonzero(diff_x)[1] + 1
    ys = np.nonzero(diff_y)[0] + 1
    total = xs.size + ys.size
    if total == 0:
        return 1.0
    aligned = int(np.count_nonzero(xs % scale == 0) + np.count_nonzero(ys % scale == 0))
    return aligned / total


def misaligned_texels(rgba, scale):
    """격자에 안 맞는 경계가 들어 있는 텍셀 표시(접촉판 겹침 줄 용). 원본 → 텍셀 bool 배열."""
    flat = rgba.astype(np.int32)
    height, width = rgba.shape[:2]
    bad = np.zeros((height, width), dtype=bool)
    diff_x = np.any(flat[:, 1:] != flat[:, :-1], axis=2)
    diff_y = np.any(flat[1:, :] != flat[:-1, :], axis=2)
    cols = np.arange(1, width)
    rows = np.arange(1, height)
    bad[:, 1:] |= diff_x & (cols % scale != 0)[None, :]
    bad[1:, :] |= diff_y & (rows % scale != 0)[:, None]
    th, tw = height // scale, width // scale
    return bad[: th * scale, : tw * scale].reshape(th, scale, tw, scale).any(axis=(1, 3))


def palette_distance(texel_rgba, allowed):
    """덮은 칸마다 가장 가까운 허용 색까지 RGB 거리 — 그 최댓값과 칸별 거리 배열."""
    mask = covered_mask(texel_rgba)
    dist = np.zeros(mask.shape, dtype=np.float64)
    if not mask.any() or not allowed:
        return 0.0, dist
    rgb = texel_rgba[..., :3].astype(np.float64)
    pal = np.asarray(allowed, dtype=np.float64)
    gaps = np.sqrt(((rgb[..., None, :] - pal[None, None, :, :]) ** 2).sum(axis=3)).min(axis=2)
    dist[mask] = gaps[mask]
    return float(dist.max()), dist


def palette_out(dist, mask, allowed=True, tol=PALETTE_TOLERANCE):
    """덮은 칸 중 팔레트 · fx_extra 밖(거리 > tol) 칸 비율 0~1. 빈 그림이면 0(소재묶음설계 6-4).

    허용 색이 비면 None(판정 불가) — 거리가 다 0 으로 나와 「팔레트 안」 0 으로 읽히면 안 된다.
    """
    if not allowed:
        return None
    covered = int(np.count_nonzero(mask))
    if covered == 0:
        return 0.0
    return int(np.count_nonzero(dist[mask] > tol)) / covered


def flicker(covered_counts):
    """덮은 텍셀 수 열에서 오르내림이 뒤집힌 횟수. 같은 값이 이어지면 건너뛴다.

    한 번 커졌다 줄면(산 하나) 1. 크기 곡선 · 플립북이 깜박이면 커진다(실험 3).
    """
    flips = 0
    last_sign = 0
    for before, after in zip(covered_counts, covered_counts[1:]):
        sign = (after > before) - (after < before)
        if sign == 0:
            continue
        if last_sign != 0 and sign != last_sign:
            flips += 1
        last_sign = sign
    return flips


def semi_alpha(texel_rgba):
    alpha = texel_rgba[..., 3]
    return int(np.count_nonzero((alpha > 0) & (alpha < 255)))


def alpha_sum(texel_rgba):
    return float(texel_rgba[..., 3].astype(np.float64).sum() / 255.0)


def coverage(texel_rgba):
    """덮은 칸 %(0~100)."""
    mask = covered_mask(texel_rgba)
    return 100.0 * float(np.count_nonzero(mask)) / float(mask.size)


def centroid(texel_rgba):
    """덮은 칸 평균 [x, y] 텍셀. 원점 = 캔버스 가운데, y 는 위가 +. 빈 그림이면 None."""
    mask = covered_mask(texel_rgba)
    if not mask.any():
        return None
    height, width = mask.shape
    rows, cols = np.nonzero(mask)
    x = float(cols.mean()) + 0.5 - width / 2.0
    y = height / 2.0 - (float(rows.mean()) + 0.5)
    return [round(x, 4), round(y, 4)]


def spread_x(blob_xs):
    """덩어리 무게중심 x 들의 표준편차(텍셀). 덩어리가 하나 이하면 0.

    덩어리 안 텍셀 퍼짐은 안 센다 — 큰 덩어리 하나(빛 · 빽빽한 먼지)가 흔들림으로 잡히면 쏠림을 놓친다.
    """
    if len(blob_xs) < 2:
        return 0.0
    return round(float(np.std(blob_xs)), 4)


def _linear(channel):
    c = channel / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def luma(texel_rgba):
    """칸별 선형 밝기(Rec.709). 덮지 않은 칸은 0."""
    rgb = texel_rgba[..., :3].astype(np.float64)
    value = 0.2126 * _linear(rgb[..., 0]) + 0.7152 * _linear(rgb[..., 1]) + 0.0722 * _linear(rgb[..., 2])
    return np.where(covered_mask(texel_rgba), value, 0.0)


def touches_border(texel_rgba):
    mask = covered_mask(texel_rgba)
    return bool(mask[0, :].any() or mask[-1, :].any() or mask[:, 0].any() or mask[:, -1].any())


def _blobs(mask):
    """4-이웃 덩어리마다 (가로 폭, 무게중심 x) — x 는 칸 열 번호 평균(텍셀)."""
    seen = np.zeros(mask.shape, dtype=bool)
    height, width = mask.shape
    blobs = []
    for row, col in zip(*np.nonzero(mask)):
        if seen[row, col]:
            continue
        stack = [(row, col)]
        seen[row, col] = True
        low, high = col, col
        col_sum, count = 0, 0
        while stack:
            r, c = stack.pop()
            low, high = min(low, c), max(high, c)
            col_sum, count = col_sum + int(c), count + 1
            for nr, nc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
                if 0 <= nr < height and 0 <= nc < width and mask[nr, nc] and not seen[nr, nc]:
                    seen[nr, nc] = True
                    stack.append((nr, nc))
        blobs.append((int(high - low + 1), col_sum / count))
    return blobs


def _blob_widths(mask):
    """4-이웃 덩어리마다 가로 폭(텍셀)."""
    return [w for w, _ in _blobs(mask)]


def particle_size(texel_rgba, widths=None):
    """덩어리 폭의 최빈값. 같은 수면 작은 폭. 빈 그림이면 None."""
    if widths is None:
        widths = _blob_widths(covered_mask(texel_rgba))
    if not widths:
        return None
    counts = Counter(widths)
    best = max(counts.values())
    return min(w for w, n in counts.items() if n == best)


def frame_metrics(frame_rgba, scale, texels, allowed):
    """한 장의 지표 묶음. allowed = 팔레트 + fx_extra RGB 목록."""
    tex = to_texels(frame_rgba, scale, texels)
    mask = covered_mask(tex)
    lum = luma(tex)
    dist, dist_map = palette_distance(tex, allowed)
    blobs = _blobs(mask)
    widths = [w for w, _ in blobs]
    return {
        "colors": unique_colors(tex),
        "grid_ratio": grid_ratio(frame_rgba, scale),
        "palette_dist": dist,
        "palette_out": palette_out(dist_map, mask, allowed),
        "semi_alpha": semi_alpha(tex),
        "alpha_sum": alpha_sum(tex),
        "coverage": coverage(tex),
        "centroid": centroid(tex),
        "max_luma": float(lum.max()),
        "bright_count": int(np.count_nonzero(lum >= BRIGHT_LUMA)),
        "covered": int(np.count_nonzero(mask)),
        "clipped": touches_border(tex),
        "particle_size": particle_size(tex, widths),
        "blobs": len(widths),
        "spread_x": spread_x([x for _, x in blobs]),
        # 캔버스 가로 텍셀 — frame.lopsided 문턱 상한(폭의 1/4)에 쓴다.
        "width": int(mask.shape[1]),
    }
