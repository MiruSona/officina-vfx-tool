"""기준 PNG 들에서 palette · pixel_size 를 뽑는다. 규칙은 설계 3-1 · 3-2."""
from functools import reduce
from math import gcd
from pathlib import Path

import numpy as np
from PIL import Image, UnidentifiedImageError

from vfxtool.errors import VfxError
from vfxtool.profile.common import MAX_PALETTE, make_issue

MIN_SHARE = 0.005  # 쓰인 칸(알파 > 0)의 0.5% 아래 색은 잡티로 본다
TRANSPARENT_KEY = -1


def load_rgba(path) -> np.ndarray:
    p = Path(path)
    if not p.is_file():
        raise VfxError(f"기준 PNG 가 없다 : {p}")
    try:
        with Image.open(p) as image:
            return np.asarray(image.convert("RGBA"), dtype=np.uint8)
    except (UnidentifiedImageError, OSError) as error:
        raise VfxError(f"PNG 를 못 읽었다 : {p} ({error})") from error


def _to_hex(r: int, g: int, b: int, a: int) -> str:
    if a == 255:
        return f"#{r:02X}{g:02X}{b:02X}"
    return f"#{r:02X}{g:02X}{b:02X}{a:02X}"


def _color_keys(rgba: np.ndarray) -> np.ndarray:
    """칸마다 RGBA 를 정수 하나로 묶는다. 알파 0 칸은 -1."""
    channels = rgba.astype(np.int64)
    keys = (channels[..., 0] << 24) | (channels[..., 1] << 16) | (channels[..., 2] << 8) | channels[..., 3]
    keys[rgba[..., 3] == 0] = TRANSPARENT_KEY
    return keys


def _key_to_hex(key: int) -> str:
    return _to_hex((key >> 24) & 255, (key >> 16) & 255, (key >> 8) & 255, key & 255)


def _row_runs(keys: np.ndarray) -> np.ndarray:
    """줄마다 같은 색이 이어진 길이들. 투명 줄은 뺀다."""
    lengths = []
    for row in keys:
        change = np.flatnonzero(row[1:] != row[:-1]) + 1
        starts = np.concatenate(([0], change))
        ends = np.concatenate((change, [len(row)]))
        opaque = row[starts] != TRANSPARENT_KEY
        lengths.append((ends - starts)[opaque])
    return np.concatenate(lengths)


def _count_colors(keys: np.ndarray) -> dict:
    opaque = keys[keys != TRANSPARENT_KEY]
    values, counts = np.unique(opaque, return_counts=True)
    return {int(v): int(c) for v, c in zip(values, counts)}


def extract(png_paths: list) -> dict:
    """{"fields": {palette, pixel_size}, "issues": [...], "metrics": {...}} 를 돌려준다."""
    if not png_paths:
        raise VfxError("기준 PNG 를 하나 이상 넣어라 (--from)")
    totals = {}
    per_image = []
    runs = []
    for path in png_paths:
        keys = _color_keys(load_rgba(path))
        counts = _count_colors(keys)
        per_image.append(set(counts))
        for key, count in counts.items():
            totals[key] = totals.get(key, 0) + count
        runs.append(_row_runs(keys))
        runs.append(_row_runs(keys.T))

    issues = []
    fields = {}
    used = sum(totals.values())
    # 많이 쓰인 순, 같으면 hex 순으로 늘 같은 결과를 낸다.
    ranked = sorted(totals.items(), key=lambda item: (-item[1], _key_to_hex(item[0])))
    kept = [key for key, count in ranked if used > 0 and count / used >= MIN_SHARE]
    if len(kept) > MAX_PALETTE:
        issues.append(make_issue("profile.palette_cut", "warn", f"쓰인 색이 {len(kept)} 개 — 많이 쓰인 {MAX_PALETTE} 개만 남겼다"))
        kept = kept[:MAX_PALETTE]
    fields["palette"] = [_key_to_hex(key) for key in kept]

    all_runs = np.concatenate(runs)
    min_run = None
    if all_runs.size > 0:
        min_run = int(all_runs.min())
        fields["pixel_size"] = [int(reduce(gcd, np.unique(all_runs).tolist()))]
    if min_run is not None and min_run >= 2:
        issues.append(make_issue(
            "profile.upscaled", "info",
            f"가장 작은 같은 색 줄 길이가 {min_run}px — 확대본이면 pixel_size 가 틀리다. 1:1 원본을 넣어라",
            ["--from"],
        ))

    kept_set = set(kept)
    ref_max_colors = max((len(colors & kept_set) for colors in per_image), default=0)
    metrics = {
        "images": len(png_paths),
        "used_pixels": used,
        "colors_found": len(totals),
        "colors_kept": len(kept),
        "min_run": min_run,
        "ref_max_colors": ref_max_colors,
    }
    return {"fields": fields, "issues": issues, "metrics": metrics}
