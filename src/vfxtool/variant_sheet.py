"""변형 묶음 격자 접촉판 — overview.png(속성 × 세기·시드) · strips_N.png(판마다 시간 띠)(변형묶음설계 8절).

그림 조각(합성 · 확대 · 프레임 읽기)은 sheet · frames 것을 그대로 쓰고, 여기서는 칸 배치만 한다.
done 이 아닌 판은 빈 칸으로 그린다 — 실패면 짙은 회색 + 자홍 X + `FAIL <규칙>`, 아직 안 돈 판은 회색 + `--`.
"""

import math
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from vfxtool import frames as frames_mod
from vfxtool import measure_metrics as mm
from vfxtool.errors import VfxError
from vfxtool.paths import ensure_inside, read_json
from vfxtool.report import issue
from vfxtool.sheet import HEADER_H, LABEL_H, PAD, PER_GROUP, SHEET_BG, TEXT, MAGENTA, composite, enlarge
from vfxtool.variant_set import ledger_entries, read_ledger

OVERVIEW_FILE = "overview.png"
STRIPS_PREFIX = "strips_"
STRIP_ROWS = 12          # 시간 띠 한 장에 판 12줄
FOLD_OVER = 32           # 장이 이보다 많은 판만 PER_GROUP(12) 장마다 줄을 접는다(8-2)
CHAR_W = 6               # 기본 글꼴 한 글자 폭 상한(px) — 왼쪽 이름 열 폭 셈
FAIL_BG = (40, 40, 40)
PENDING_BG = (96, 96, 96)
STRIPS_RE = re.compile(r"strips_\d+\.png")


def make_sheets(set_dir):
    """set.json 옆에 overview.png · strips_N.png 를 다시 그린다. (만든 파일 [(경로, (w, h))], issues)."""
    out = Path(set_dir).resolve()
    ledger = read_ledger(out)
    entries = ledger_entries(ledger)
    issues = []
    shots = {}
    for entry in entries:
        if entry["state"] != "done":
            continue
        try:
            shots[entry["name"]] = load_variant(out, entry["name"])
        except VfxError as exc:
            issues.append(issue("variant.sheet", "warn", f"{entry['name']} 프레임을 못 읽어 빈 칸으로 둔다 — {exc.message}"))
    texels = _canvas(shots)
    k = frames_mod.cell_scale(texels)
    cell = (texels[0] * k, texels[1] * k)
    made = []
    overview = draw_overview(ledger, entries, shots, cell, k)
    made.append(_save(overview, ensure_inside(out / OVERVIEW_FILE, out)))
    _clear_old_strips(out)
    for number, chunk in enumerate(_chunks(entries, STRIP_ROWS), start=1):
        strip = draw_strips(chunk, shots, cell, k)
        made.append(_save(strip, ensure_inside(out / f"{STRIPS_PREFIX}{number}.png", out)))
    return made, issues


class VariantShot:
    """done 판 하나의 프레임(텍셀 RGBA) · 대표 장 번호."""

    def __init__(self, info, frames, best, counts):
        self.info = info
        self.frames = frames
        self.best = best
        self.counts = counts


def load_variant(out, name):
    folder = ensure_inside(out / name, out)
    result = frames_mod.load_result(folder)
    info = frames_mod.load_round(folder, result, frames_mod.load_resolved(folder))
    loaded = frames_mod.load_frames(folder, result, expected=frames_mod.expected_size(info))
    texel_frames = [(f.i, f.t, frames_mod.to_texels(f.rgba, info.scale, info.texels)) for f in loaded]
    measured = {}
    measure_path = folder / "measure.json"
    if measure_path.is_file():
        measured = read_json(measure_path)
        if not isinstance(measured, dict):
            raise VfxError(f"measure.json 은 JSON 객체여야 한다 : {measure_path}")
    best = pick_frame([tex for _, _, tex in texel_frames], (measured.get("metrics") or {}).get("coverage"))
    issues = measured.get("issues") or []
    counts = tuple(sum(1 for item in issues if item.get("severity") == s) for s in ("error", "warn"))
    return VariantShot(info, texel_frames, best, counts)


def pick_frame(texel_frames, coverage=None):
    """덮은 면적이 가장 큰 장의 번호(목록 자리). 같으면 앞 장. measure 의 coverage 가 맞는 길이면 그것을 쓴다."""
    if not isinstance(coverage, list) or len(coverage) != len(texel_frames):
        coverage = [mm.coverage(tex) for tex in texel_frames]
    best = 0
    for n, value in enumerate(coverage):
        if value > coverage[best]:
            best = n
    return best


def _canvas(shots):
    """칸 텍셀 크기 — 처음 done 판 캔버스. done 판이 없으면 기본 64×64."""
    for shot in shots.values():
        return shot.info.texels
    return frames_mod.DEFAULT_TEXELS


def columns_of(ledger, entries):
    """열 = (세기, 시드 k) — 세기 순 안에서 시드 순. 장부 tiers · seeds 를 따르고, 없으면 판 칸 순서대로."""
    tiers = ledger.get("tiers") or _unique(entry.get("tier") for entry in entries)
    seeds = ledger.get("seeds") or 1
    return [(tier, k) for tier in tiers for k in range(seeds)]


def rows_of(ledger, entries):
    return ledger.get("attrs") or _unique(entry.get("attr") for entry in entries)


def _unique(values):
    seen = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen


def left_width(names):
    return max(len(str(name)) for name in names) * CHAR_W + 2 * PAD


def overview_size(n_rows, n_cols, cell, left):
    """overview 크기 — 머리글 · 열 머리 한 줄 · 줄마다 (칸 + 밑 글줄)."""
    width = left + n_cols * (cell[0] + PAD) + PAD
    height = HEADER_H + LABEL_H + n_rows * (cell[1] + LABEL_H + PAD) + PAD
    return width, height


def draw_overview(ledger, entries, shots, cell, k):
    rows = rows_of(ledger, entries)
    cols = columns_of(ledger, entries)
    left = left_width(rows)
    sheet = Image.new("RGB", overview_size(len(rows), len(cols), cell, left), SHEET_BG)
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    draw.text((PAD, 2), _ascii(_overview_header(ledger, entries)), fill=TEXT, font=font)
    for c, (tier, seed_k) in enumerate(cols):
        draw.text((left + c * (cell[0] + PAD), HEADER_H), _ascii(f"{tier} s{seed_k}"), fill=TEXT, font=font)
    by_place = {(entry.get("attr"), entry.get("tier"), entry.get("k", 0)): entry for entry in entries}
    for r, attr in enumerate(rows):
        y = HEADER_H + LABEL_H + r * (cell[1] + LABEL_H + PAD)
        draw.text((PAD, y + cell[1] // 2 - 6), _ascii(str(attr)), fill=TEXT, font=font)
        for c, (tier, seed_k) in enumerate(cols):
            x = left + c * (cell[0] + PAD)
            entry = by_place.get((attr, tier, seed_k))
            shot = None
            if entry is not None:
                shot = shots.get(entry["name"])
            if shot is None:
                _blank_cell(sheet, draw, font, (x, y), cell, entry)
                continue
            frame_i, _, tex = shot.frames[shot.best]
            sheet.paste(enlarge(composite(tex, (0, 0, 0)), k), (x, y))
            caption = f"#{frame_i} e{shot.counts[0]} w{shot.counts[1]}"
            draw.text((x, y + cell[1] + 1), caption, fill=TEXT, font=font)
    return sheet


def _overview_header(ledger, entries):
    seeds = [entry.get("seed") for entry in entries if isinstance(entry.get("seed"), int)]
    base = min(seeds) if seeds else "-"
    failed = sum(1 for entry in entries if entry.get("state") == "failed")
    return (f"{ledger.get('name')} | {ledger.get('template')} | seed {base} +16k | "
            f"{len(entries)} variants | fail {failed}")


def _blank_cell(sheet, draw, font, origin, cell, entry):
    """실패 판 = 짙은 회색 + 자홍 X + FAIL <규칙>, 아직 안 돈 판(또는 칸이 없음) = 회색 + --."""
    x, y = origin
    box = [x, y, x + cell[0] - 1, y + cell[1] - 1]
    if entry is not None and entry.get("state") == "failed":
        draw.rectangle(box, fill=FAIL_BG)
        draw.line([(box[0], box[1]), (box[2], box[3])], fill=MAGENTA, width=2)
        draw.line([(box[0], box[3]), (box[2], box[1])], fill=MAGENTA, width=2)
        draw.text((x + 2, y + cell[1] + 1), _ascii(f"FAIL {_fail_rule(entry)}"), fill=MAGENTA, font=font)
        return
    draw.rectangle(box, fill=PENDING_BG)
    draw.text((x + 2, y + cell[1] + 1), "--", fill=TEXT, font=font)


def _fail_rule(entry):
    """실패 까닭 줄인 말 — 첫 error issue 규칙에서 `variant.` 머리를 뗀다."""
    for item in entry.get("issues") or []:
        if item.get("severity") == "error":
            return str(item.get("rule", "")).removeprefix("variant.")
    return "?"


def strip_columns(n_frames):
    """한 판 띠의 한 줄 장 수 — 32장까지는 한 줄, 넘으면 PER_GROUP(12) 장마다 접는다. 장이 없으면 1."""
    if n_frames > FOLD_OVER:
        return PER_GROUP
    return max(1, n_frames)


def strip_lines(n_frames):
    return max(1, math.ceil(n_frames / strip_columns(n_frames)))


def strips_size(frame_counts, cell, left):
    """시간 띠 한 장 크기. frame_counts = 판마다 장 수(done 이 아니면 0)."""
    columns = max(strip_columns(n) for n in frame_counts)
    width = left + columns * (cell[0] + PAD) + PAD
    rows_h = sum(strip_lines(n) * (cell[1] + PAD) for n in frame_counts)
    return width, LABEL_H + rows_h + PAD


def draw_strips(chunk, shots, cell, k):
    left = left_width([entry["name"] for entry in chunk])
    counts = [len(shots[entry["name"]].frames) if entry["name"] in shots else 0 for entry in chunk]
    sheet = Image.new("RGB", strips_size(counts, cell, left), SHEET_BG)
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    _label_columns(draw, font, chunk, shots, cell, left)
    y = LABEL_H
    for entry, n_frames in zip(chunk, counts):
        draw.text((PAD, y + 2), entry["name"], fill=TEXT, font=font)
        shot = shots.get(entry["name"])
        if shot is None:
            _blank_cell(sheet, draw, font, (left, y), cell, entry)
            y += cell[1] + PAD
            continue
        per_line = strip_columns(n_frames)
        for n, (frame_i, t, tex) in enumerate(shot.frames):
            x = left + (n % per_line) * (cell[0] + PAD)
            row_y = y + (n // per_line) * (cell[1] + PAD)
            sheet.paste(enlarge(composite(tex, (0, 0, 0)), k), (x, row_y))
        y += strip_lines(n_frames) * (cell[1] + PAD)
    return sheet


def _label_columns(draw, font, chunk, shots, cell, left):
    """맨 위 한 줄에만 `#i t=` — 이 장에서 장이 가장 많은 판 것(첫 줄 장 수만큼). 줄마다 같으니 한 번만 단다."""
    longest = None
    for entry in chunk:
        shot = shots.get(entry["name"])
        if shot is not None and (longest is None or len(shot.frames) > len(longest.frames)):
            longest = shot
    if longest is None:
        return
    for n, (frame_i, t, _) in enumerate(longest.frames[: strip_columns(len(longest.frames))]):
        draw.text((left + n * (cell[0] + PAD), 0), f"#{frame_i} t={t:.3f}", fill=TEXT, font=font)


def _chunks(items, size):
    return [items[n:n + size] for n in range(0, len(items), size)]


def _clear_old_strips(out):
    """판 수가 줄어 남은 옛 strips_N.png 를 지운다(이 폴더 바로 아래 · 이름 꼴이 맞는 파일만)."""
    for path in out.iterdir():
        if STRIPS_RE.fullmatch(path.name) and path.is_file() and not path.is_symlink():
            path.unlink()


def _save(image, path):
    image.save(path, format="PNG")
    return path, image.size


def _ascii(text):
    """기본 글꼴이 못 그리는 글자는 ? 로(이름은 이미 ASCII — 안전장치)."""
    return text.encode("ascii", "replace").decode("ascii")
