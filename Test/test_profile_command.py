"""profile/command.py — `vfxtool profile` 보고 · 종료 코드 · golden 바이트 비교."""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

from vfxtool.profile import command

DATA = Path(__file__).parent / "data" / "profile"


def _run(capsys, argv: list):
    parser = argparse.ArgumentParser()
    command.add_parser(parser.add_subparsers(dest="command"))
    args = parser.parse_args(["profile"] + argv)
    code = command.run(args)
    report = json.loads(capsys.readouterr().out)
    return code, report


def test_golden_profile_bytes(tmp_path, capsys):
    out = tmp_path / "profile.json"
    code, report = _run(capsys, [
        "--from", str(DATA / "small.png"),
        "--style", str(DATA / "style.json"),
        "--override", str(DATA / "hand.json"),
        "--out", str(out),
    ])
    assert code == 0
    assert report["status"] == "warn"
    assert out.read_bytes() == (DATA / "golden_profile.json").read_bytes()


def test_report_lists_warns_and_metrics(tmp_path, capsys):
    out = tmp_path / "p.json"
    code, report = _run(capsys, ["--from", str(DATA / "small_x3.png"), "--out", str(out)])
    assert code == 0
    assert [issue["rule"] for issue in report["issues"]] == ["profile.upscaled"]
    assert report["metrics"]["palette"] == 4
    assert json.loads(out.read_text(encoding="utf-8"))["pixel_size"] == [6]


def test_empty_palette_is_fail_and_writes_nothing(tmp_path, capsys):
    png = tmp_path / "empty.png"
    Image.fromarray(np.zeros((4, 4, 4), dtype=np.uint8), "RGBA").save(png)
    out = tmp_path / "p.json"
    code, report = _run(capsys, ["--from", str(png), "--out", str(out)])
    assert code == 1
    assert report["status"] == "fail"
    assert report["issues"][-1]["rule"] == "profile.palette_empty"
    assert not out.exists()


def test_missing_png_is_error_exit_two(tmp_path, capsys):
    code, report = _run(capsys, ["--from", str(tmp_path / "none.png"), "--out", str(tmp_path / "p.json")])
    assert code == 2
    assert report["status"] == "error"


def test_bad_override_is_error_exit_two(tmp_path, capsys):
    hand = tmp_path / "hand.json"
    hand.write_text('{"ppu": -1}', encoding="utf-8")
    code, report = _run(capsys, [
        "--from", str(DATA / "fine.png"), "--override", str(hand), "--out", str(tmp_path / "p.json"),
    ])
    assert code == 2
    assert "ppu" in report["issues"][0]["detail"]
