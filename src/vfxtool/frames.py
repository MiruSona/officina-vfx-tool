"""바퀴 폴더의 result.json · 프레임 PNG 를 읽어 RGBA numpy 배열로 돌려준다.

투명 1회 렌더가 기본이다. 흑백 짝(f###_k · f###_w)은 additive 디버그 옵션으로만 쓴다(설계 5-4 · 8-2).
"""

import math
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from vfxtool.errors import VfxError
from vfxtool.paths import ensure_inside, read_json

DEFAULT_TEXELS = (64, 64)
DEFAULT_SCALE = 4
ROUND_DIR_PATTERN = re.compile(r"round_(\d+)")


@dataclass
class Frame:
    i: int
    t: float
    rgba: np.ndarray  # 원본 해상도 H×W×4 uint8


@dataclass
class RoundInfo:
    """측정 · 접촉판이 알아야 하는 바퀴 정보(result.json + resolved.json)."""

    name: str
    round_no: int
    seed: object
    fixed_time_step: object
    texels: tuple
    scale: int
    loop: bool
    layers: list


def load_result(round_dir):
    path = Path(round_dir) / "result.json"
    if not path.is_file():
        raise VfxError(f"result.json 이 없다 — {path}")
    return read_json(path)


def load_resolved(round_dir, recipe_path=None):
    """--recipe 로 준 resolved.json, 없으면 바퀴 폴더의 resolved.json. 둘 다 없으면 빈 dict."""
    if recipe_path is not None:
        path = Path(recipe_path)
        if not path.is_file():
            raise VfxError(f"레시피 파일이 없다 — {path}")
        return read_json(path)
    path = Path(round_dir) / "resolved.json"
    if path.is_file():
        return read_json(path)
    return {}


def load_round(round_dir, result, resolved):
    canvas = resolved.get("canvas") or {}
    texels = tuple(canvas.get("texels") or DEFAULT_TEXELS)
    scale = int(canvas.get("scale") or DEFAULT_SCALE)
    match = ROUND_DIR_PATTERN.fullmatch(Path(round_dir).resolve().name)
    round_no = 0
    if match:
        round_no = int(match.group(1))
    return RoundInfo(
        name=str(resolved.get("name") or Path(round_dir).resolve().parent.name),
        round_no=round_no,
        seed=result.get("seed", resolved.get("seed")),
        fixed_time_step=result.get("fixedTimeStep", resolved.get("fixedTimeStep")),
        texels=(int(texels[0]), int(texels[1])),
        scale=scale,
        loop=bool(resolved.get("loop", False)),
        layers=list(resolved.get("layers") or []),
    )


def _frame_file(round_dir, name):
    """프레임 PNG 는 round_N/frames/ 아래가 기본. 없으면 바퀴 폴더 바로 아래를 본다."""
    root = Path(round_dir)
    for candidate in (root / "frames" / name, root / name):
        if candidate.is_file():
            ensure_inside(candidate, root)
            return candidate
    raise VfxError(f"프레임 PNG 가 없다 — {name}")


def _read_rgba(path):
    with Image.open(path) as img:
        return np.asarray(img.convert("RGBA"), dtype=np.uint8).copy()


def recover_alpha(black, white):
    """검정 · 흰 배경 짝에서 RGBA 복원. a = 1 − (흰 − 검정), 색 = 검정 / a (검정 판은 c·a)."""
    k = black[..., :3].astype(np.float64) / 255.0
    w = white[..., :3].astype(np.float64) / 255.0
    alpha = 1.0 - (w - k).mean(axis=2)
    alpha = np.clip(alpha, 0.0, 1.0)
    safe = np.where(alpha > 0, alpha, 1.0)
    color = np.clip(k / safe[..., None], 0.0, 1.0)
    rgba = np.zeros(black.shape[:2] + (4,), dtype=np.uint8)
    rgba[..., :3] = np.round(color * 255.0).astype(np.uint8)
    rgba[..., 3] = np.round(alpha * 255.0).astype(np.uint8)
    rgba[alpha <= 0] = 0
    return rgba


def _bw_pair(round_dir, png_name):
    stem = Path(png_name).stem
    try:
        black = _frame_file(round_dir, f"{stem}_k.png")
        white = _frame_file(round_dir, f"{stem}_w.png")
    except VfxError:
        return None
    return recover_alpha(_read_rgba(black), _read_rgba(white))


def expected_size(info):
    """프레임 PNG 가 가져야 할 (높이, 너비) 픽셀 = 텍셀 × scale."""
    return (info.texels[1] * info.scale, info.texels[0] * info.scale)


def load_frames(round_dir, result, use_bw=False, expected=None):
    """result.json 프레임 순서대로 Frame 목록. use_bw 면 흑백 짝은 복원식으로. expected 와 크기가 다르면 VfxError."""
    frames = []
    for entry in result.get("frames") or []:
        png = entry.get("png") or f"f{int(entry['i']):03d}.png"
        rgba = None
        if use_bw:
            rgba = _bw_pair(round_dir, png)
        if rgba is None:
            rgba = _read_rgba(_frame_file(round_dir, png))
        if expected is not None and tuple(rgba.shape[:2]) != tuple(expected):
            raise VfxError(f"프레임 {png} 크기 {rgba.shape[1]}x{rgba.shape[0]} 가 캔버스 {expected[1]}x{expected[0]} 와 다르다")
        frames.append(Frame(i=int(entry["i"]), t=float(entry.get("t", 0.0)), rgba=rgba))
    if not frames:
        raise VfxError("result.json 에 프레임이 없다")
    return frames


def to_texels(rgba, scale, texels=None):
    """원본을 텍셀 해상도로 줄인다 — 칸마다 가운데 픽셀 하나를 고른다(nearest)."""
    offset = scale // 2
    small = rgba[offset::scale, offset::scale]
    if texels is not None:
        small = small[: texels[1], : texels[0]]
    return np.ascontiguousarray(small)


def frame_interval(frames):
    """프레임 t 간격(초). 한 장뿐이거나 간격이 0 이면 1/12."""
    gaps = [b.t - a.t for a, b in zip(frames, frames[1:]) if b.t > a.t]
    if not gaps:
        return 1.0 / 12.0
    gaps.sort()
    return gaps[len(gaps) // 2]


def cell_scale(texels, minimum=128):
    """칸이 minimum px 이상 되는 가장 작은 정수 배율(설계 6-3)."""
    shortest = max(1, min(texels))
    return max(1, math.ceil(minimum / shortest))
