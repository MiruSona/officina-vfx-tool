"""기하 소재 8종 생성기 — 문자 그림 표 → 실루엣 PNG + 메타(소재묶음설계 3-1 · 번개낙뢰설계 2절).

`#` = 칠함 (255, 255, 255, 255), `.` = 빈 칸 (0, 0, 0, 0). 난수가 없어 같은 입력이면 늘 같은 픽셀이다.
`1 2 3` 은 회색 밝기 단(191 · 127 · 63)이다. bolt32 만 밝기 4단을 쓴다 — 변형 판에서 램프로 칠해 굽는다(paint_tones).
나머지 7종은 흰 1단이다.
시트는 가로로 장(frames), 세로로 변형 줄(rows)을 놓는다. Unity 시트는 위 왼쪽 칸이 0 번이다.
ring · bolt32 는 표가 커서 규칙으로 그린다.
"""

import math
from pathlib import Path

import numpy as np
from PIL import Image

from vfxtool.material_lib import LIB_DIR, META_KEYS
from vfxtool.paths import write_json

LICENSE = "MIT (VFXTool 생성)"
FILLED = (255, 255, 255, 255)
TONES = {"#": 255, "1": 191, "2": 127, "3": 63}  # 글자 → 회색 명도. 단 번호 0~3 = 램프 번호 p0~p3

# 이름 → (칸 크기, 변형 줄 이름, 블렌드 권장, 줄마다 장 목록). 장 하나 = 문자 그림 줄 목록.
ART = {
    "dot": (3, ["px1", "px2", "plus3"], "alpha", [
        [["...", ".#.", "..."]],
        [["...", ".##", ".##"]],
        [[".#.", "###", ".#."]],
    ]),
    "cross": (5, ["small", "big", "hollow"], "alpha", [
        [[".....", "..#..", ".###.", "..#..", "....."]],
        [["..#..", "..#..", "#####", "..#..", "..#.."]],
        [["..#..", ".....", "#.#.#", ".....", "..#.."]],
    ]),
    "star4": (7, [], "additive", [[
        [".......", ".......", ".......", "...#...", ".......", ".......", "......."],
        [".......", ".......", "...#...", "..###..", "...#...", ".......", "......."],
        ["...#...", "...#...", "..###..", "#######", "..###..", "...#...", "...#..."],
        [".......", ".......", ".......", "...#...", ".......", ".......", "......."],
    ]]),
    "disc": (7, [], "additive", [[
        ["..###..", ".#####.", "#######", "#######", "#######", ".#####.", "..###.."],
    ]]),
    "shard": (5, ["l2", "l3", "blob4"], "alpha", [
        [[".....", ".....", "..#..", "...#.", "....."]],
        [[".....", "..##.", "...#.", ".....", "....."]],
        [[".....", "..##.", ".##..", "..#..", "....."]],
    ]),
    "streak": (7, ["v5", "v7", "diag5"], "additive", [
        [[".......", "...#...", "...#...", "...#...", "...#...", "...#...", "......."]],
        [["...#...", "...#...", "...#...", "...#...", "...#...", "...#...", "...#..."]],
        [[".......", ".....#.", "....#..", "...#...", "..#....", ".#.....", "......."]],
    ]),
}
RING_CELL = 15


def midpoint_circle(radius, center):
    """중점 원 그리기(Bresenham) — 1px 선 위 (x, y) 집합."""
    cx, cy = center
    points = set()
    x, y, err = radius, 0, 1 - radius
    while x >= y:
        for dx, dy in ((x, y), (y, x), (-y, x), (-x, y), (-x, -y), (-y, -x), (y, -x), (x, -y)):
            points.add((cx + dx, cy + dy))
        y += 1
        if err < 0:
            err += 2 * y + 1
        else:
            x -= 1
            err += 2 * (y - x) + 1
    return points


def _ring_frames():
    """ring 4장 — 작은 원 · 고리 · 끊긴 고리(45° 조각 중 짝수 번째) · 상하좌우 점 4개."""
    center = (RING_CELL // 2, RING_CELL // 2)
    broken = set()
    for x, y in midpoint_circle(7, center):
        angle = math.degrees(math.atan2(y - center[1], x - center[0])) % 360
        if int(angle // 45) % 2 == 0:
            broken.add((x, y))
    dots = {(7, 0), (14, 7), (7, 14), (0, 7)}
    return [midpoint_circle(2, center), midpoint_circle(5, center), broken, dots]


BOLT_CELL = 32
BOLT_PEAK = [(15, 0), (12, 8), (19, 13), (13, 21), (15, 28)]  # 줄기 꼭짓점 A~E
BOLT_JITTER = [(15, 0), (12, 8), (20, 13), (12, 21), (15, 28)]  # 장 2 「지직」 — C · D 를 1px 옮김
BOLT_BRANCHES = [[(12, 8), (9, 12), (8, 15)], [(19, 13), (22, 16), (23, 19)]]


def _line(p, q):
    """Bresenham 1px 선(8방향) 위 (x, y) 집합 — 두 끝 포함."""
    (x0, y0), (x1, y1) = p, q
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x1 > x0 else -1), (1 if y1 > y0 else -1)
    err = dx + dy
    points = set()
    while True:
        points.add((x0, y0))
        if (x0, y0) == (x1, y1):
            return points
        twice = 2 * err
        if twice >= dy:
            err += dy
            x0 += sx
        if twice <= dx:
            err += dx
            y0 += sy


def _polyline(vertices):
    points = set()
    for p, q in zip(vertices, vertices[1:]):
        points |= _line(p, q)
    return points


def _core(vertices):
    """2px 심 — 세로가 긴 마디는 오른쪽 한 칸, 가로가 긴 마디는 아래 한 칸을 더한다."""
    points = set()
    for p, q in zip(vertices, vertices[1:]):
        step = (1, 0) if abs(q[1] - p[1]) >= abs(q[0] - p[0]) else (0, 1)
        for x, y in _line(p, q):
            points |= {(x, y), (x + step[0], y + step[1])}
    return points


def _rim(core, cell=BOLT_CELL):
    """심의 8-이웃 팽창 − 심. 칸 밖은 버린다."""
    grown = {(x + dx, y + dy) for x, y in core for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
    return {(x, y) for x, y in grown - core if 0 <= x < cell and 0 <= y < cell}


def _disc(rows):
    """바닥 원 — rows = [(y, x 시작, x 끝), …] 칸 채움."""
    return {(x, y) for y, x0, x1 in rows for x in range(x0, x1 + 1)}


def _outline(disc):
    """원의 바깥 둘레 — 4-이웃이 모두 원 안인 칸을 뺀다."""
    return {(x, y) for x, y in disc if not all(n in disc for n in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)))}


DISC_8x3 = _disc([(29, 13, 18), (30, 12, 19), (31, 13, 18)])
DISC_10x4 = _disc([(28, 12, 19), (29, 11, 20), (30, 11, 20), (31, 12, 19)])
DISC_12x4 = _disc([(28, 11, 20), (29, 10, 21), (30, 10, 21), (31, 11, 20)])


def _bolt_frames():
    """bolt32 8장 — 장마다 [(글자, 점 집합), …]. 뒤에 칠한 것이 앞을 덮는다(설계 2-3 장별 표)."""
    core1, core2 = _core(BOLT_PEAK), _core(BOLT_JITTER)
    branches = _polyline(BOLT_BRANCHES[0]) | _polyline(BOLT_BRANCHES[1])
    center = _polyline(BOLT_PEAK)
    pieces = {(x, y) for x, y in center if y <= 6 or 11 <= y <= 17 or 22 <= y <= 27}
    return [
        [("1", {(14, 31), (17, 31)} | _line((15, 0), (14, 3)))],
        [("2", _rim(core1)), ("2", branches), ("#", core1), ("#", DISC_8x3)],
        [("2", _rim(core2)), ("3", branches), ("#", core2), ("1", DISC_10x4),
         ("#", _disc([(29, 14, 17), (30, 14, 17)])), ("2", {(11, 26), (11, 27), (20, 26), (20, 27)})],
        [("1", _rim(core1)), ("2", _outline(DISC_10x4))],
        [("2", pieces), ("3", {(x, y) for x, y in _outline(DISC_12x4) if (x + y) % 2 == 0})],
        [("3", _line((13, 29), (9, 31)) | _line((18, 29), (22, 31)))],
        [("3", {(11, 24), (20, 22), (13, 18), (18, 27), (9, 29), (22, 29)})],
        [("3", {(12, 21), (19, 24), (15, 27)})],
    ]


def _tone_art(layers, cell):
    """[(글자, 점 집합), …] → 문자 그림 줄 목록. 뒤 층이 앞 층을 덮는다."""
    rows = [["."] * cell for _ in range(cell)]
    for char, points in layers:
        for x, y in points:
            rows[y][x] = char
    return ["".join(row) for row in rows]


def _points_to_art(points, cell):
    rows = [["."] * cell for _ in range(cell)]
    for x, y in points:
        rows[y][x] = "#"
    return ["".join(row) for row in rows]


def spec(name):
    """(칸, 변형, 블렌드, 줄마다 장 목록). ring 은 규칙으로 만든다."""
    if name == "ring":
        frames = [_points_to_art(points, RING_CELL) for points in _ring_frames()]
        return RING_CELL, [], "alpha", [frames]
    if name == "bolt32":
        return BOLT_CELL, [], "alpha", [[_tone_art(layers, BOLT_CELL) for layers in _bolt_frames()]]
    return ART[name]


def names():
    return sorted(list(ART) + ["ring", "bolt32"])


def render(name):
    """시트 픽셀 배열 (높이, 너비, 4) uint8. 칸이 문자 그림 크기와 다르면 ValueError(표 오타)."""
    cell, _, _, rows = spec(name)
    frames = len(rows[0])
    sheet = np.zeros((cell * len(rows), cell * frames, 4), dtype=np.uint8)
    for row_index, row in enumerate(rows):
        if len(row) != frames:
            raise ValueError(f"{name} : 줄마다 장 수가 같아야 한다")
        for frame_index, art in enumerate(row):
            if len(art) != cell or any(len(line) != cell for line in art):
                raise ValueError(f"{name} : 장 {row_index}/{frame_index} 가 {cell}×{cell} 이 아니다")
            for y, line in enumerate(art):
                for x, char in enumerate(line):
                    if char in TONES:
                        value = TONES[char]
                        sheet[row_index * cell + y, frame_index * cell + x] = (value, value, value, 255)
    return sheet


def paint_tones(rgba, ramp):
    """밝기 단 → 램프 색(#RRGGBB 목록). 단 번호 = rint((255 − R) / 64), 램프 끝을 넘으면 끝 색.

    알파 > 0 칸만 칠하고 나머지는 (0,0,0,0). 흰 1단 소재는 모두 ramp[0] 이 된다.
    lib_cut.paint(휘도 최근접)를 안 쓰는 까닭 : 노랑 램프에서 191 이 Y2 로 가 Y1 이 사라진다(설계 3-2).
    """
    colors = np.array([[int(h[i:i + 2], 16) for i in (1, 3, 5)] for h in ramp], dtype=np.uint8)
    tone = np.clip(np.rint((255 - rgba[..., 0].astype(np.float32)) / 64), 0, len(ramp) - 1).astype(int)
    out = np.zeros(rgba.shape, dtype=np.uint8)
    opaque = rgba[..., 3] > 0
    out[opaque, :3] = colors[tone[opaque]]
    out[opaque, 3] = 255
    return out


def meta(name):
    cell, variants, blend, rows = spec(name)
    frames = len(rows[0])
    kind = "flipbook" if frames > 1 else "grain"
    values = [name, cell, [frames, len(rows)], frames, len(rows), kind, list(variants), blend, "draw", None, LICENSE]
    return dict(zip(META_KEYS, values))


def build(out_dir=LIB_DIR, only=None):
    """PNG + 메타를 out_dir 에 쓴다. 쓴 이름 목록을 돌려준다. only 를 모르면 ValueError."""
    chosen = names()
    if only is not None:
        if only not in chosen:
            raise ValueError(f"생성기가 모르는 소재 {only!r} (그리는 것 : {chosen})")
        chosen = [only]
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name in chosen:
        Image.fromarray(render(name), "RGBA").save(out / f"{name}.png")
        write_json(out / f"{name}.json", meta(name))
    return chosen
