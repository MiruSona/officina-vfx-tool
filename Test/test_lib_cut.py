"""자르기 — 작은 가짜 원본(여기서 만든 것)으로 창 · 잘림 5 초과 실패 · sha256 거절 · 축소 없음 · CLI."""

import json
import os
import subprocess
import sys

import numpy as np
import pytest
from PIL import Image

from conftest import SRC
from vfxtool import lib_cut, material_lib
from vfxtool.errors import VfxError


def _strip(tmp_path, frames, src_cell, extra=()):
    """src_cell 칸 × frames 장 띠. 장마다 가운데 4×4 회색 반투명 덩이 + extra 의 (장, x, y) 점."""
    rgba = np.zeros((src_cell, src_cell * frames, 4), dtype=np.uint8)
    mid = src_cell // 2
    for k in range(frames):
        rgba[mid - 2:mid + 2, k * src_cell + mid - 2:k * src_cell + mid + 2] = (90, 90, 90, 128)
    for k, x, y in extra:
        rgba[y, k * src_cell + x] = (200, 10, 10, 255)
    path = tmp_path / "src.png"
    Image.fromarray(rgba, "RGBA").save(path)
    return path


def _entry(path, **fields):
    entry = {"file": "src.png", "title": "t", "author": "a", "url": "u", "license": "CC0 1.0",
             "sha256": lib_cut.sha256_of(path), "src_cell": 16, "src_frames": 2, "cell": 8, "window": [4, 4], "blend": "alpha"}
    entry.update(fields)
    return {"fake": entry}


def test_window_cut_whitens_and_keeps_size(tmp_path):
    source = _strip(tmp_path, 2, 16, extra=[(0, 0, 0), (1, 15, 15)])
    clipped, problem = lib_cut.cut(source, "fake", tmp_path / "out", _entry(source))
    assert problem is None and clipped == [1, 1]
    sheet = np.array(Image.open(tmp_path / "out" / "fake.png"))
    assert sheet.shape == (8, 16, 4)
    # 회색 반투명 4×4 덩이가 흰 불투명 4×4 로 — 크기는 그대로(축소 없음).
    assert int((sheet[..., 3] == 255).sum()) == 32
    assert set(np.unique(sheet[..., 3])) == {0, 255}
    assert np.all(sheet[sheet[..., 3] == 255][:, :3] == 255)
    meta = json.loads((tmp_path / "out" / "fake.json").read_text(encoding="utf-8"))
    assert meta["tiles"] == [2, 1] and meta["made"] == "cut" and meta["kind"] == "flipbook"


def test_clip_over_five_fails_and_writes_nothing(tmp_path):
    dots = [(1, x, 0) for x in range(6)]
    source = _strip(tmp_path, 2, 16, extra=dots)
    clipped, problem = lib_cut.cut(source, "fake", tmp_path / "out", _entry(source))
    assert clipped == [0, 6] and "[1]" in problem
    assert not (tmp_path / "out" / "fake.png").exists()


def test_sha256_mismatch_refused(tmp_path):
    source = _strip(tmp_path, 2, 16)
    with pytest.raises(VfxError):
        lib_cut.cut(source, "fake", tmp_path / "out", _entry(source, sha256="0" * 64))


def test_small_source_is_padded_not_scaled(tmp_path):
    source = _strip(tmp_path, 2, 4)
    sources = _entry(source, src_cell=4, cell=8, window=[0, 0])
    _, problem = lib_cut.cut(source, "fake", tmp_path / "out", sources)
    sheet = np.array(Image.open(tmp_path / "out" / "fake.png"))
    assert problem is None and sheet.shape == (8, 16, 4)
    assert np.array_equal(np.nonzero(sheet[:, :8, 3])[0], [r for r in range(2, 6) for _ in range(4)])


def test_wrong_strip_shape_is_error(tmp_path):
    source = _strip(tmp_path, 2, 16)
    with pytest.raises(VfxError):
        lib_cut.cut(source, "fake", tmp_path / "out", _entry(source, src_frames=3))


def test_cli_cut_refuses_other_file(tmp_path):
    source = _strip(tmp_path, 2, 16)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC)
    proc = subprocess.run([sys.executable, "-m", "vfxtool", "lib", "cut", "--source", str(source), "--name", "puff8", "--out", str(tmp_path)],
                          capture_output=True, env=env, timeout=60, check=False)
    assert proc.returncode == 2
    assert "sha256" in json.loads(proc.stdout.decode("utf-8"))["issues"][0]["detail"]
    assert not (tmp_path / "puff8.png").exists()


def test_two_tones_keeps_bright_white_and_dark_grey(tmp_path):
    # 회색(90) 덩이는 어두운 칸 → 회색 TONE_GREY, 빨강(200,10,10 휘도 ≈ 66) 점도 어둡다. 흰 점은 흰 255.
    source = _strip(tmp_path, 2, 16, extra=[(0, 6, 6)])
    rgba = np.array(Image.open(source))
    rgba[9, 16 + 9] = (250, 240, 200, 255)
    Image.fromarray(rgba, "RGBA").save(source)
    clipped, problem = lib_cut.cut(source, "fake", tmp_path / "out", _entry(source), tones=2)
    assert problem is None
    sheet = np.array(Image.open(tmp_path / "out" / "fake.png"))
    opaque = sheet[sheet[..., 3] == 255][:, :3]
    assert set(np.unique(opaque)) == {lib_cut.TONE_GREY, 255}
    assert int((opaque[:, 0] == 255).sum()) == 1  # 밝은 칸은 그 한 점뿐
    # sources.json 항목의 tones 를 따른다(인자 없을 때).
    lib_cut.cut(source, "fake", tmp_path / "out2", _entry(source, tones=2))
    again = np.array(Image.open(tmp_path / "out2" / "fake.png"))
    assert np.array_equal(again, sheet)


def test_bad_tones_is_error():
    with pytest.raises(VfxError):
        lib_cut.whiten(np.zeros((2, 2, 4), dtype=np.uint8), tones=3)


def test_tones_recorded_in_meta(tmp_path):
    # 재현용 — 몇 단으로 잘랐나가 메타 끝 tones 에 남는다. --out 이 lib/ 가 아니면 sources 는 안 건드린다.
    source = _strip(tmp_path, 2, 16)
    sources = _entry(source)
    lib_cut.cut(source, "fake", tmp_path / "out", sources, tones=2)
    meta = json.loads((tmp_path / "out" / "fake.json").read_text(encoding="utf-8"))
    assert list(meta)[-1] == "tones" and meta["tones"] == 2
    assert "tones" not in sources["fake"]
    assert material_lib.meta_problem(meta, "fake") is None


@pytest.mark.parametrize("window", [[4], [4, "4"], "4,4", [4, 4.5], [True, 4]])
def test_bad_window_shape_is_vfx_error(tmp_path, window):
    source = _strip(tmp_path, 2, 16)
    with pytest.raises(VfxError):
        lib_cut.cut(source, "fake", tmp_path / "out", _entry(source, window=window))


def test_bad_sources_tones_is_vfx_error(tmp_path):
    source = _strip(tmp_path, 2, 16)
    with pytest.raises(VfxError):
        lib_cut.cut(source, "fake", tmp_path / "out", _entry(source, tones=3))


def test_paint_picks_nearest_luma_ramp_color():
    # 휘도 244 → 밝은 색, 85 → 어두운 색. 투명 칸은 (0,0,0,0) 그대로.
    rgba = np.array([[[255, 241, 232, 255], [255, 0, 77, 255], [9, 9, 9, 0]]], dtype=np.uint8)
    out, mapping = lib_cut.paint(rgba, ["#FFE08A", "#602010"])
    assert out[0, 0].tolist() == [255, 224, 138, 255] and out[0, 1].tolist() == [96, 32, 16, 255]
    assert out[0, 2].tolist() == [0, 0, 0, 0]
    assert mapping == {"#FF004D": "#602010", "#FFF1E8": "#FFE08A"}


def test_cut_ramp_writes_only_ramp_png(tmp_path):
    source = _strip(tmp_path, 2, 16)
    clipped, problem, mapping, frames = lib_cut.cut_ramp(source, "fake", tmp_path / "out", ["#FFFFFF", "#404040"], _entry(source))
    assert problem is None and clipped == [0, 0] and mapping == {"#5A5A5A": "#404040"} and frames == 2
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["fake_ramp.png"]
    sheet = np.array(Image.open(tmp_path / "out" / "fake_ramp.png"))
    assert sheet.shape == (8, 16, 4) and set(map(tuple, sheet[sheet[..., 3] == 255][:, :3])) == {(64, 64, 64)}


def test_cut_ramp_refuses_tool_lib_dir(tmp_path):
    source = _strip(tmp_path, 2, 16)
    with pytest.raises(VfxError):
        lib_cut.cut_ramp(source, "fake", material_lib.LIB_DIR, ["#FFFFFF"], _entry(source))
    with pytest.raises(VfxError):
        lib_cut.cut_ramp(source, "fake", material_lib.LIB_DIR / "sub", ["#FFFFFF"], _entry(source))
    assert not (material_lib.LIB_DIR / "sub").exists()


def _cli(*args):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC)
    return subprocess.run([sys.executable, "-m", "vfxtool", "lib", "cut", *args], capture_output=True, env=env, timeout=60, check=False)


@pytest.mark.parametrize("extra", [["--ramp", "p0"], ["--ramp", "p0", "--profile", "P"], ["--ramp", "#FFFFFF", "--profile", "P", "--out", "O"],
                                   ["--ramp", "p9", "--profile", "P", "--out", "O"], ["--ramp", "p0", "--profile", "P", "--out", "O", "--tones", "1"]])
def test_cli_ramp_argument_errors(tmp_path, extra):
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"version": 1, "palette": ["#FFE08A", "#602010"]}), encoding="utf-8")
    args = [str(profile) if a == "P" else str(tmp_path / "o") if a == "O" else a for a in extra]
    proc = _cli("--source", str(tmp_path / "none.png"), "--name", "burst16", *args)
    assert proc.returncode == 2
    detail = json.loads(proc.stdout.decode("utf-8"))["issues"][0]["detail"]
    assert "--ramp" in detail or "팔레트" in detail  # 원본이 없다는 말보다 먼저 인자에서 막힌다
    assert not (tmp_path / "o").exists()


def test_repo_sources_json_is_in_write_json_form():
    # cut 이 tones 를 고쳐 sources.json 을 다시 쓸 때 꼴만 바뀌는 diff(손으로 접은 배열 등)가 안 나게.
    from vfxtool.paths import dump_json
    path = material_lib.LIB_DIR / material_lib.SOURCES_FILE
    # autocrlf 로 받은 작업 사본은 CRLF 일 수 있다 — 줄끝은 맞춰 놓고 꼴만 본다.
    text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    assert text == dump_json(lib_cut.load_sources(path))


def test_paint_refuses_alpha_hex():
    # 8자리(알파)는 램프 칸이 불투명이라 알파가 조용히 사라지므로 거절한다.
    with pytest.raises(VfxError):
        lib_cut.paint(np.zeros((1, 1, 4), dtype=np.uint8), ["#FFE08A80"])


def test_cli_ramp_clip_failure_has_no_file_or_recipe(tmp_path, monkeypatch):
    from argparse import Namespace
    from vfxtool.commands import lib as lib_command
    source = _strip(tmp_path, 2, 16, extra=[(1, x, 0) for x in range(6)])
    monkeypatch.setattr(lib_cut, "load_sources", lambda path=None: _entry(source))
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"version": 1, "palette": ["#FFE08A", "#602010"]}), encoding="utf-8")
    args = Namespace(source=str(source), name="fake", out=str(tmp_path / "o"), tones=None, ramp="p0,p1", profile=str(profile))
    metrics, issues = lib_command._cut(args)
    assert issues[0]["rule"] == "lib.clip"
    assert "file" not in metrics and "recipe" not in metrics and "mapping" not in metrics
    assert not (tmp_path / "o").exists()
