"""CC0 원본 띠 → 플립북 소재 자르기 · 흰 실루엣 바꾸기(소재묶음설계 3-2).

규칙 : 크기를 안 바꾼다(축소 금지) · 칸이 크면 모든 장에 같은 창으로 잘라 내고, 작으면 가운데 빈 칸을 덧댄다 ·
잘려 나가는 불투명 픽셀이 장당 MAX_CLIPPED 를 넘으면 실패 · 알파 > 0 은 흰색 불투명, 나머지는 (0,0,0,0).
2단(tones=2)이면 밝은 칸은 흰 255, 어두운 칸은 회색 TONE_GREY — 원본의 밝은 속 · 어두운 테두리를 명도로 남긴다.
팔레트 램프(--ramp)면 원본 명도를 램프 색(프로필 팔레트 번호) 중 휘도가 가장 가까운 색으로 미리 칠한다 —
startColor 흰색으로 쓰면 텍스처 × 색 곱이 색을 안 바꾼다. 팔레트는 게임마다 달라 툴 안 lib/ 에는 안 쓴다.
원본은 저장소에 안 넣는다 — 출처 · 창 · sha256 은 lib/sources.json 에 있고, sha256 이 다르면 거절한다.
"""

import hashlib
from pathlib import Path

import numpy as np
from PIL import Image

from vfxtool.errors import VfxError
from vfxtool.material_lib import LIB_DIR, META_KEYS, SOURCES_FILE, TONES_KEY
from vfxtool.paths import read_json, write_json

MAX_CLIPPED = 5
TONE_SPLIT = 128  # 2단 갈림 : 원본 sRGB 휘도(Rec.601)가 이 값 이상이면 밝은 칸
TONE_GREY = 128  # 2단의 어두운 칸 명도(sRGB 50%)
TONES = (1, 2)
RAMP_SUFFIX = "_ramp"
CUT_KEYS = ("file", "title", "author", "url", "license", "sha256", "src_cell", "src_frames", "cell", "window", "blend")


def load_sources(path=None):
    """sources.json — {소재 이름: 자르기 항목}."""
    if path is None:
        path = LIB_DIR / SOURCES_FILE
    data = read_json(path)
    if not isinstance(data, dict):
        raise VfxError(f"sources.json 은 객체여야 한다 : {path}")
    return data


def entry_for(name, sources):
    if name not in sources:
        raise VfxError(f"sources.json 에 {name!r} 가 없다 (있는 것 : {sorted(sources)})")
    entry = sources[name]
    missing = [key for key in CUT_KEYS if key not in entry]
    if missing:
        raise VfxError(f"sources.json 의 {name} 에 칸이 없다 : {missing}")
    window = entry["window"]
    if not (isinstance(window, list) and len(window) == 2 and all(_is_int(n) for n in window)):
        raise VfxError(f"sources.json 의 {name} window 는 [x, y] 정수 둘이어야 한다 : {window!r}")
    if entry.get(TONES_KEY, 1) not in TONES:
        raise VfxError(f"sources.json 의 {name} tones 는 {TONES} 중 하나다 : {entry[TONES_KEY]!r}")
    return entry


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def sha256_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def whiten(rgba, tones=1):
    """알파 > 0 → 흰 불투명, 아니면 (0,0,0,0). 1단은 원본 명도를 버린다(텍스처 × 색 곱 함정).

    tones=2 면 휘도 < TONE_SPLIT 인 칸만 회색 TONE_GREY 로 남긴다(밝은 속 / 어두운 테두리 두 단).
    """
    if tones not in TONES:
        raise VfxError(f"tones 는 {TONES} 중 하나다 : {tones!r}")
    out = np.zeros(rgba.shape, dtype=np.uint8)
    opaque = rgba[..., 3] > 0
    out[opaque] = (255, 255, 255, 255)
    if tones == 2:
        out[opaque & (_luma(rgba[..., :3]) < TONE_SPLIT)] = (TONE_GREY, TONE_GREY, TONE_GREY, 255)
    return out


def _luma(rgb):
    """sRGB 휘도(Rec.601) — TONE_SPLIT 과 같은 자."""
    return rgb.astype(np.float32) @ np.array([0.299, 0.587, 0.114], dtype=np.float32)


def paint(rgba, ramp):
    """알파 > 0 칸을 램프 색(#RRGGBB 목록) 중 휘도가 가장 가까운 색으로, 나머지는 (0,0,0,0). 같으면 앞 색.

    돌려주는 것 : (칠한 배열, {원본 hex: 램프 hex}). 알파 붙은 8자리는 VfxError — 램프 칸은 늘 불투명이라 알파가 조용히 사라진다.
    """
    bad = [h for h in ramp if not (isinstance(h, str) and len(h) == 7 and h.startswith("#"))]
    if bad:
        raise VfxError(f"램프 색은 알파 없는 #RRGGBB 여야 한다 (램프 칸은 불투명) : {bad}")
    colors = np.array([[int(h[i:i + 2], 16) for i in (1, 3, 5)] for h in ramp], dtype=np.uint8)
    out = np.zeros(rgba.shape, dtype=np.uint8)
    opaque = rgba[..., 3] > 0
    pick = np.abs(_luma(rgba[..., :3])[..., None] - _luma(colors)[None, None, :]).argmin(axis=-1)
    out[opaque, :3] = colors[pick[opaque]]
    out[opaque, 3] = 255
    found = np.unique(rgba[opaque, :3], axis=0)
    picks = np.abs(_luma(found)[:, None] - _luma(colors)[None, :]).argmin(axis=-1)
    mapping = {"#%02X%02X%02X" % tuple(int(v) for v in src): ramp[int(i)].upper() for src, i in zip(found, picks)}
    return out, dict(sorted(mapping.items()))


def cut_frames(rgba, entry, tones=1):
    """원본 띠 배열 → (흰 실루엣 시트 배열, 장별 잘린 불투명 픽셀 수)."""
    sheet, clipped = crop_frames(rgba, entry)
    return whiten(sheet, tones), clipped


def crop_frames(rgba, entry):
    """원본 띠 배열 → (색 그대로인 시트 배열, 장별 잘린 불투명 픽셀 수). 원본은 가로 한 줄 띠라고 본다."""
    src_cell = entry["src_cell"]
    frames = entry["src_frames"]
    cell = entry["cell"]
    height, width = rgba.shape[:2]
    if height != src_cell or width != src_cell * frames:
        raise VfxError(f"원본 {width}×{height} 가 sources.json 의 {src_cell} 칸 × {frames} 장 띠가 아니다")
    sheet = np.zeros((cell, cell * frames, 4), dtype=np.uint8)
    clipped = []
    for index in range(frames):
        tile = rgba[:, index * src_cell:(index + 1) * src_cell]
        part, lost = _fit(tile, cell, entry["window"])
        sheet[:, index * cell:(index + 1) * cell] = part
        clipped.append(lost)
    return sheet, clipped


def _fit(tile, cell, window):
    """한 장을 cell 칸에 맞춘다 — (칸 배열, 잘린 불투명 픽셀 수)."""
    src_cell = tile.shape[0]
    if cell >= src_cell:
        out = np.zeros((cell, cell, 4), dtype=np.uint8)
        pad = (cell - src_cell) // 2
        out[pad:pad + src_cell, pad:pad + src_cell] = tile
        return out, 0
    x, y = window
    if not (0 <= x <= src_cell - cell and 0 <= y <= src_cell - cell):
        raise VfxError(f"창 {window} 가 원본 칸 {src_cell} 안에 {cell} 칸으로 안 들어간다")
    part = tile[y:y + cell, x:x + cell]
    lost = int(np.count_nonzero(tile[..., 3] > 0)) - int(np.count_nonzero(part[..., 3] > 0))
    return part.copy(), lost


def meta_for(name, entry, tones=1):
    frames = entry["src_frames"]
    values = [name, entry["cell"], [frames, 1], frames, 1, "flipbook", [], entry["blend"], "cut", name, entry["license"]]
    meta = dict(zip(META_KEYS, values))
    meta[TONES_KEY] = tones
    return meta


def cut(source_path, name, out_dir=LIB_DIR, sources=None, tones=None):
    """원본을 잘라 <out_dir>/<name>.png · .json 을 쓴다. (장별 잘림, 실패 까닭 또는 None).

    tones = 1(흰 1단) · 2(흰 + 회색). None 이면 sources.json 항목의 `tones`(없으면 1).
    쓴 tones 는 메타에 남기고, 기본 sources.json 을 읽어 툴 안 lib/ 에 쓴 판에서 항목과 다르면 항목에도 적는다 —
    다음에 --tones 없이 잘라도 같은 소재가 나오게(재현). --out 으로 딴 데 쓴 시험 판은 sources.json 을 안 건드린다.

    sha256 이 다르거나 꼴이 틀리면 VfxError. 장당 잘림이 MAX_CLIPPED 를 넘으면 파일을 안 쓰고 까닭을 돌려준다.
    """
    sources_path = None
    if sources is None:
        sources_path = LIB_DIR / SOURCES_FILE
        sources = load_sources(sources_path)
    entry = entry_for(name, sources)
    rgba = _read_source(source_path, entry)
    if tones is None:
        tones = entry.get("tones", 1)
    sheet, clipped = cut_frames(rgba, entry, tones)
    problem = _clip_problem(clipped)
    if problem is not None:
        return clipped, problem
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    Image.fromarray(sheet, "RGBA").save(out / f"{name}.png")
    write_json(out / f"{name}.json", meta_for(name, entry, tones))
    if sources_path is not None and out.resolve() == LIB_DIR and entry.get(TONES_KEY, 1) != tones:
        entry[TONES_KEY] = tones
        write_json(sources_path, sources)
    return clipped, None


def ramp_file(name):
    return f"{name}{RAMP_SUFFIX}.png"


def _clip_problem(clipped):
    """장당 잘림이 MAX_CLIPPED 를 넘으면 사람 말, 아니면 None."""
    over = [index for index, lost in enumerate(clipped) if lost > MAX_CLIPPED]
    if not over:
        return None
    return f"장 {over} 에서 불투명 픽셀이 {MAX_CLIPPED} 개 넘게 잘린다 (장별 {clipped}) — 창을 옮기거나 칸을 키운다"


def cut_ramp(source_path, name, out_dir, ramp, sources=None):
    """원본을 잘라 램프 색으로 칠한 <out_dir>/<name>_ramp.png 하나를 쓴다. (장별 잘림, 실패 까닭 또는 None, 색 대응, 장 수).

    ramp 는 hex 목록(프로필 팔레트에서 푼 것). out_dir 이 툴 안 lib/ (또는 그 아래)면 VfxError — lib 은 모든 게임이 같이 쓰는 흰 소재다.
    메타 JSON 은 안 쓴다 — 레시피가 파일 시트로 부른다(tiles 는 sources.json 의 장 수).
    """
    out = Path(out_dir)
    real = out.resolve()
    if real == LIB_DIR or LIB_DIR in real.parents:
        raise VfxError("램프 소재는 게임 팔레트로 칠한 것이라 툴 안 lib 폴더에 못 쓴다 — --out 에 게임 쪽 폴더를 준다")
    if not ramp:
        raise VfxError("램프 색이 비었다")
    if sources is None:
        sources = load_sources()
    entry = entry_for(name, sources)
    sheet, clipped = crop_frames(_read_source(source_path, entry), entry)
    frames = entry["src_frames"]
    problem = _clip_problem(clipped)
    if problem is not None:
        return clipped, problem, {}, frames
    painted, mapping = paint(sheet, ramp)
    out.mkdir(parents=True, exist_ok=True)
    Image.fromarray(painted, "RGBA").save(out / ramp_file(name))
    return clipped, None, mapping, frames


def _read_source(source_path, entry):
    """sha256 을 맞춰 본 원본 RGBA 배열."""
    source = Path(source_path)
    if not source.is_file():
        raise VfxError(f"원본 파일이 없다 : {source}")
    digest = sha256_of(source)
    if digest != entry["sha256"]:
        raise VfxError(f"원본 sha256 이 sources.json 과 다르다 — 다른 파일이다 ({digest[:12]}… ≠ {entry['sha256'][:12]}…)")
    with Image.open(source) as image:
        return np.array(image.convert("RGBA"))
