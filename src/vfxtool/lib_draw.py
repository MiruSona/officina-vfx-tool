"""기하 소재 7종 생성기 — 문자 그림 표 → 흰 1단 실루엣 PNG + 메타(소재묶음설계 3-1).

`#` = 칠함 (255, 255, 255, 255), `.` = 빈 칸 (0, 0, 0, 0). 난수가 없어 같은 입력이면 늘 같은 픽셀이다.
시트는 가로로 장(frames), 세로로 변형 줄(rows)을 놓는다. Unity 시트는 위 왼쪽 칸이 0 번이다.
ring 만 표가 커서 중점 원 그리기로 찍는다.
"""

import math
from pathlib import Path

import numpy as np
from PIL import Image

from vfxtool.material_lib import LIB_DIR, META_KEYS
from vfxtool.paths import write_json

LICENSE = "MIT (VFXTool 생성)"
FILLED = (255, 255, 255, 255)

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
    return ART[name]


def names():
    return sorted(list(ART) + ["ring"])


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
                    if char == "#":
                        sheet[row_index * cell + y, frame_index * cell + x] = FILLED
    return sheet


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
