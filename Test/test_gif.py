"""gif.py — 프레임 수 · 한 장 시간(fps 는 t 간격) · 끝 멈춤 · 무한 반복 · 배율."""
import argparse
import json
import shutil
from pathlib import Path

from PIL import Image

from vfxtool import gif

DATA = Path(__file__).parent / "data" / "frames" / "round_1"


def _copy(tmp_path):
    round_dir = tmp_path / "synth_dots" / "round_1"
    shutil.copytree(DATA, round_dir)
    return round_dir


def test_durations_from_frame_interval():
    loaded = gif.frames_mod.load_frames(DATA, gif.frames_mod.load_result(DATA))
    durations = gif.durations_ms(loaded)
    assert durations[:-1] == [83] * 7
    assert durations[-1] == 83 + gif.HOLD_LAST_MS


def test_gif_frames_loop_and_size(tmp_path):
    round_dir = _copy(tmp_path)
    target, count, _ = gif.make_gif(round_dir, k=4)
    assert target == round_dir / "preview.gif"
    assert count == 8
    with Image.open(target) as img:
        assert img.n_frames == 8
        assert img.size == (64, 64)
        assert img.info.get("loop") == 0
        assert 80 <= img.info["duration"] <= 90
        img.seek(7)
        assert img.info["duration"] >= 500
        last = img.convert("RGB")
        assert last.getpixel((0, 0)) == (0, 0, 0)
        assert last.getpixel((4 * 10 + 1, 4 * 7 + 1)) == (255, 255, 255)


def test_cli_bad_scale_is_exit_2(tmp_path, capsys):
    round_dir = _copy(tmp_path)
    parser = argparse.ArgumentParser()
    gif.add_parser(parser.add_subparsers(dest="command"))
    args = parser.parse_args(["gif", str(round_dir), "--scale", "0"])
    assert gif.run(args) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "error"
