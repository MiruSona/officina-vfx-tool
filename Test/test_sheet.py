"""sheet.py — 접촉판 크기 · 칸 색 · 겹침 줄 · 같은 입력이면 같은 바이트."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

from PIL import Image

from vfxtool import sheet

DATA = Path(__file__).parent / "data" / "frames" / "round_1"
PROFILE = {"palette": ["#FFFFFF"]}
K = 8  # 16 텍셀 → 128px 이상 되는 가장 작은 배율
CELL = 16 * K
X0 = sheet.PAD
Y0 = sheet.HEADER_H + sheet.LABEL_H


def _setup(tmp_path):
    round_dir = tmp_path / "synth_dots" / "round_1"
    shutil.copytree(DATA, round_dir)
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps(PROFILE), encoding="utf-8")
    return round_dir, profile


def _cell_xy(n, row, tx, ty):
    """n 번째 칸(0부터) · row 줄의 텍셀 (tx, ty) 가운데 픽셀."""
    x = X0 + n * (CELL + sheet.PAD) + tx * K + K // 2
    y = Y0 + row * (CELL + sheet.PAD) + ty * K + K // 2
    return x, y


def test_sheet_size_two_rows(tmp_path):
    round_dir, _ = _setup(tmp_path)
    target, size = sheet.make_sheet(round_dir)
    assert size == (sheet.PAD + 8 * (CELL + sheet.PAD), sheet.HEADER_H + sheet.LABEL_H + 2 * (CELL + sheet.PAD) + sheet.PAD)
    assert target == round_dir / "sheet.png"


def test_sheet_cells_black_and_white_rows(tmp_path):
    round_dir, _ = _setup(tmp_path)
    target, _ = sheet.make_sheet(round_dir)
    img = Image.open(target).convert("RGB")
    assert img.getpixel(_cell_xy(0, 0, 3, 7)) == (255, 255, 255)
    assert img.getpixel(_cell_xy(0, 0, 0, 0)) == (0, 0, 0)
    assert img.getpixel(_cell_xy(0, 1, 0, 0)) == (255, 255, 255)
    assert img.getpixel(_cell_xy(2, 1, 5, 7)) == (240, 160, 64)


def test_overlay_row_marks(tmp_path):
    round_dir, profile = _setup(tmp_path)
    target, size = sheet.make_sheet(round_dir, overlay=True, profile_path=profile)
    assert size[1] == sheet.HEADER_H + sheet.LABEL_H + 3 * (CELL + sheet.PAD) + sheet.PAD
    img = Image.open(target).convert("RGB")
    assert img.getpixel(_cell_xy(2, 2, 5, 7)) == sheet.MAGENTA
    assert img.getpixel(_cell_xy(4, 2, 9, 7)) == sheet.YELLOW
    assert img.getpixel(_cell_xy(0, 2, 3, 7)) == (255, 255, 255)
    cross = (X0 + (-4 + 8) * K, Y0 + 2 * (CELL + sheet.PAD) + 8 * K)
    assert img.getpixel(cross) == sheet.CROSS


def test_sheet_bytes_are_stable(tmp_path):
    round_dir, profile = _setup(tmp_path)
    first, _ = sheet.make_sheet(round_dir, overlay=True, profile_path=profile, out=tmp_path / "a.png")
    second, _ = sheet.make_sheet(round_dir, overlay=True, profile_path=profile, out=tmp_path / "b.png")
    digest = [hashlib.sha256(p.read_bytes()).hexdigest() for p in (first, second)]
    assert digest[0] == digest[1]


def test_header_uses_measure_counts(tmp_path):
    round_dir, _ = _setup(tmp_path)
    (round_dir / "measure.json").write_text(json.dumps({"status": "warn", "issues": [
        {"rule": "frame.last_not_empty", "severity": "warn"}], "metrics": {}}), encoding="utf-8")
    sheet_mod_info = sheet.frames_mod.load_round(round_dir, sheet.frames_mod.load_result(round_dir),
                                                 sheet.frames_mod.load_resolved(round_dir))
    text = sheet.header_text(sheet_mod_info, sheet._counts(round_dir, None))
    assert text == "synth_dots | round 1 | seed 7 | fts true | error 0 warn 1"
    assert text.isascii()


def test_cli_missing_round_is_exit_2(tmp_path, capsys):
    parser = argparse.ArgumentParser()
    sheet.add_parser(parser.add_subparsers(dest="command"))
    args = parser.parse_args(["sheet", str(tmp_path / "nope")])
    assert sheet.run(args) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "error"
