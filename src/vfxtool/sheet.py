"""`vfxtool sheet` — 접촉판 sheet.png (설계 6-3).

칸 = 캔버스 텍셀 × k(128px 이상 되는 가장 작은 정수), 12칸마다 다음 묶음.
줄 : 1 검정 배경 · 2 흰 배경 · (--overlay) 3 팔레트 밖 자홍 · 격자 어긋남 노랑 · 무게중심 십자.
"""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from vfxtool import frames as frames_mod
from vfxtool import measure_metrics as mm
from vfxtool import report as report_mod
from vfxtool.errors import VfxError
from vfxtool.measure import allowed_colors
from vfxtool.recipe.profile_view import load_profile
from vfxtool.paths import read_json

PER_GROUP = 12
PAD = 4
LABEL_H = 12
HEADER_H = 16
SHEET_BG = (48, 48, 48)
TEXT = (255, 255, 255)
MAGENTA = (255, 0, 255)
YELLOW = (255, 255, 0)
CROSS = (0, 255, 255)


def composite(texel_rgba, background):
    """RGBA 를 단색 판 위에 합성한 RGB uint8."""
    rgb = texel_rgba[..., :3].astype(np.float64)
    alpha = texel_rgba[..., 3:4].astype(np.float64) / 255.0
    bg = np.asarray(background, dtype=np.float64)
    return np.round(rgb * alpha + bg * (1.0 - alpha)).astype(np.uint8)


def enlarge(rgb, k):
    """텍셀 RGB 를 k 배 nearest 로 키운 Image. variant_sheet 도 쓴다."""
    img = Image.fromarray(rgb, "RGB")
    return img.resize((img.width * k, img.height * k), Image.NEAREST)


def overlay_cell(frame_rgba, info, allowed, k):
    """겹침 칸 : 검정 합성 위에 격자 어긋난 텍셀 노랑, 팔레트 밖(거리 > PALETTE_TOLERANCE) 칸 자홍, 무게중심 십자."""
    tex = frames_mod.to_texels(frame_rgba, info.scale, info.texels)
    rgb = composite(tex, (0, 0, 0))
    bad_grid = mm.misaligned_texels(frame_rgba, info.scale)[: tex.shape[0], : tex.shape[1]]
    rgb[bad_grid] = YELLOW
    if allowed:
        _, dist = mm.palette_distance(tex, allowed)
        rgb[dist > mm.PALETTE_TOLERANCE] = MAGENTA
    cell = enlarge(rgb, k)
    center = mm.centroid(tex)
    if center is not None:
        px = (center[0] + tex.shape[1] / 2.0) * k
        py = (tex.shape[0] / 2.0 - center[1]) * k
        arm = 2 * k
        draw = ImageDraw.Draw(cell)
        draw.line([(px - arm, py), (px + arm, py)], fill=CROSS)
        draw.line([(px, py - arm), (px, py + arm)], fill=CROSS)
    return cell


def _counts(round_dir, measure_path):
    """measure.json 의 error · warn 수. 없으면 None."""
    path = Path(measure_path) if measure_path else Path(round_dir) / "measure.json"
    if not path.is_file():
        if measure_path:
            raise VfxError(f"measure.json 이 없다 — {path}")
        return None
    report = read_json(path)
    issues = report.get("issues") or []
    return tuple(sum(1 for i in issues if i.get("severity") == s) for s in ("error", "warn"))


def header_text(info, counts):
    """ASCII 만(PIL 기본 글꼴)."""
    fts = str(info.fixed_time_step).lower()
    tail = "error - warn -"
    if counts is not None:
        tail = f"error {counts[0]} warn {counts[1]}"
    return ascii_only(f"{info.name} | round {info.round_no} | seed {info.seed} | fts {fts} | {tail}")


def ascii_only(text):
    """기본 글꼴이 못 그리는 ASCII 밖 글자는 ? 로."""
    return text.encode("ascii", "replace").decode("ascii")


def build_sheet(round_dir, info, frames, counts, allowed=None, overlay=False):
    """접촉판 Image(RGB)."""
    k = frames_mod.cell_scale(info.texels)
    cell_w, cell_h = info.texels[0] * k, info.texels[1] * k
    rows = 3 if overlay else 2
    columns = min(PER_GROUP, len(frames))
    groups = (len(frames) + PER_GROUP - 1) // PER_GROUP
    group_h = LABEL_H + rows * (cell_h + PAD)
    width = PAD + columns * (cell_w + PAD)
    height = HEADER_H + groups * group_h + PAD
    sheet = Image.new("RGB", (width, height), SHEET_BG)
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    draw.text((PAD, 2), header_text(info, counts), fill=TEXT, font=font)
    for n, frame in enumerate(frames):
        x = PAD + (n % PER_GROUP) * (cell_w + PAD)
        top = HEADER_H + (n // PER_GROUP) * group_h
        draw.text((x, top), f"#{frame.i} t={frame.t:.3f}", fill=TEXT, font=font)
        tex = frames_mod.to_texels(frame.rgba, info.scale, info.texels)
        y = top + LABEL_H
        sheet.paste(enlarge(composite(tex, (0, 0, 0)), k), (x, y))
        sheet.paste(enlarge(composite(tex, (255, 255, 255)), k), (x, y + cell_h + PAD))
        if overlay:
            sheet.paste(overlay_cell(frame.rgba, info, allowed, k), (x, y + 2 * (cell_h + PAD)))
    return sheet


def make_sheet(round_dir, measure_path=None, overlay=False, profile_path=None, out=None):
    result = frames_mod.load_result(round_dir)
    info = frames_mod.load_round(round_dir, result, frames_mod.load_resolved(round_dir))
    frames = frames_mod.load_frames(round_dir, result, expected=frames_mod.expected_size(info))
    allowed = None
    if profile_path:
        allowed = allowed_colors(load_profile(profile_path))
    sheet = build_sheet(round_dir, info, frames, _counts(round_dir, measure_path), allowed, overlay)
    target = Path(out) if out else Path(round_dir) / "sheet.png"
    sheet.save(target, format="PNG")
    return target, sheet.size


def add_parser(sub):
    parser = sub.add_parser("sheet", help="바퀴 폴더 프레임으로 접촉판 sheet.png 를 만든다")
    parser.add_argument("round_dir", help="round_N 폴더(result.json · frames/)")
    parser.add_argument("--measure", help="measure.json (기본 <round_dir>/measure.json, 머리의 error/warn 수)")
    parser.add_argument("--overlay", action="store_true", help="3줄 — 팔레트 밖 · 격자 어긋남 · 무게중심")
    parser.add_argument("--profile", help="팔레트 밖 칸 표시에 쓸 profile.json (overlay 때만)")
    parser.add_argument("--out", help="sheet.png 자리 (기본 <round_dir>/sheet.png)")
    return parser


def run(args):
    try:
        target, size = make_sheet(args.round_dir, args.measure, args.overlay, args.profile, args.out)
    except VfxError as exc:
        report_mod.emit(report_mod.error_report(str(exc)))
        return 2
    report_mod.emit(report_mod.build([], {"sheet": str(target), "size": list(size)}))
    report_mod.say(f"sheet {size[0]}x{size[1]} — {target}")
    return 0
