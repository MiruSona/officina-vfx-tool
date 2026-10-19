"""고리(loop) — 가짜 Unity 로 한 바퀴 · rollback · 멈춤 · 실패 바퀴를 돈다. 진짜 Unity 는 안 띄운다."""

import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from conftest import PROFILE_PATH, RECIPE_PATH
from vfxtool import cli
from vfxtool.unity import lock

FAKE = Path(__file__).parent / "data" / "unity" / "fake_unity.py"
ROUND_FILES = ("recipe.json", "resolved.json", "job.json", "result.json", "unity.log",
               "measure.json", "sheet.png", "preview.gif")


@pytest.fixture(autouse=True)
def _no_real_unity(monkeypatch):
    monkeypatch.setattr(lock, "list_unity_processes", lambda: [])


def _frames(tmp_path):
    """256px(64 텍셀 × 4) 판 — 가운데 2×2 텍셀 점 하나, 그리고 빈 판."""
    dot = np.zeros((256, 256, 4), dtype=np.uint8)
    dot[120:128, 128:136] = [0xFF, 0xE0, 0x8A, 255]
    Image.fromarray(dot, "RGBA").save(tmp_path / "dot.png")
    Image.fromarray(np.zeros_like(dot), "RGBA").save(tmp_path / "blank.png")
    return tmp_path / "dot.png", tmp_path / "blank.png"


def _setup(tmp_path, capsys, *fake_extra, init_extra=()):
    """원본 레시피 · 프로필 · 가짜 프로젝트를 tmp 에 두고 loop init 까지 한다."""
    (tmp_path / "recipes").mkdir()
    shutil.copyfile(RECIPE_PATH, tmp_path / "recipes" / "hit.json")
    shutil.copyfile(PROFILE_PATH, tmp_path / "profile.json")
    settings = tmp_path / "proj" / "ProjectSettings"
    settings.mkdir(parents=True)
    (settings / "ProjectVersion.txt").write_text("m_EditorVersion: 6000.3.23f1\n", encoding="utf-8")
    dot, blank = _frames(tmp_path)
    parts = [sys.executable, str(FAKE), "--frame-png", str(dot), "--blank-png", str(blank)] + list(fake_extra)
    unity = " ".join(f'"{part}"' for part in parts)
    work = tmp_path / "work"
    code, _ = _call(capsys, ["loop", "init", str(tmp_path / "recipes" / "hit.json"), "--work", str(work),
                    "--project", str(settings.parent), "--unity", unity, "--input-root", str(tmp_path)] + list(init_extra))
    assert code == 0
    return work / "hit_sparks_a"


def _next(capsys, tmp_path, score, patch=True):
    argv = ["loop", "next", "--work", str(tmp_path / "work"),
            "--critic", _write(tmp_path / f"critic_{score}.json", {"score": score, "symptoms": []})]
    if patch:
        argv += ["--patch", _write(tmp_path / "patch.json", {"layers": {"sparks": {"main": {"startSpeed": 50}}}})]
    return _call(capsys, argv)


def _call(capsys, argv):
    code = cli.main(argv)
    return code, json.loads(capsys.readouterr().out)


def _write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def _ledger(loop_dir):
    return json.loads((loop_dir / "loop.json").read_text(encoding="utf-8"))


def test_one_round_collects_files(tmp_path, capsys):
    loop_dir = _setup(tmp_path, capsys)
    code, report = _call(capsys, ["loop", "run", "--work", str(tmp_path / "work")])
    assert code == 0, report
    folder = loop_dir / "round_1"
    for name in ROUND_FILES:
        assert (folder / name).is_file(), name
    assert (folder / "frames" / "f001.png").is_file()
    metrics = report["metrics"]
    assert metrics["rounds_used"] == 1 and metrics["best"]["round"] == 1
    assert metrics["stopped"] is False and metrics["stop_reason"] is None
    assert report["status"] in ("ok", "warn")


def test_rollback_then_stall_and_best(tmp_path, capsys):
    loop_dir = _setup(tmp_path, capsys)
    _call(capsys, ["loop", "run", "--work", str(tmp_path / "work")])
    code, report = _next(capsys, tmp_path, 0.6)          # 1판 0.6 → 2판
    assert code == 0 and report["metrics"]["round"] == "round_2"
    assert (loop_dir / "round_2" / "patch.json").is_file()
    recipe = json.loads((loop_dir / "round_2" / "recipe.json").read_text(encoding="utf-8"))
    assert recipe["layers"][0]["main"]["startSpeed"] == 50

    code, report = _next(capsys, tmp_path, 0.3)          # 2판 0.3 < 0.6 → rollback, 3판은 1판에서
    ledger = _ledger(loop_dir)
    assert ledger["rounds"][1]["rollback"] is True and ledger["rounds"][2]["base"] == 1
    assert report["metrics"]["discarded_patches"] == ["round_2/patch.json"]
    assert report["metrics"]["stopped"] is False and ledger["rounds"][2]["rollback"] is None

    code, report = _next(capsys, tmp_path, 0.2)          # 3판도 rollback → 두 번 연속 → 멈춤
    assert code == 0 and report["metrics"]["stop_reason"] == "stalled"
    assert not (loop_dir / "round_4").exists()
    assert (loop_dir / "round_3" / "critic.json").is_file()

    code, report = _call(capsys, ["loop", "best", "--work", str(tmp_path / "work")])
    assert code == 0 and report["metrics"]["best"]["round"] == 1 and report["metrics"]["best"]["score"] == 0.6
    code, report = _call(capsys, ["loop", "run", "--work", str(tmp_path / "work")])
    assert code == 2 and report["status"] == "error"


def test_clean_round_stops(tmp_path, capsys):
    _setup(tmp_path, capsys)
    _call(capsys, ["loop", "run", "--work", str(tmp_path / "work")])
    code, report = _next(capsys, tmp_path, 0.95)
    assert code == 0 and report["metrics"]["stop_reason"] == "clean"
    assert report["metrics"]["rounds_used"] == 1


def test_four_rounds_is_the_limit(tmp_path, capsys):
    loop_dir = _setup(tmp_path, capsys)
    _call(capsys, ["loop", "run", "--work", str(tmp_path / "work")])
    for score in (0.5, 0.6, 0.7):
        code, report = _next(capsys, tmp_path, score)
    assert report["metrics"]["round"] == "round_4"
    assert report["metrics"]["stopped"] is True and report["metrics"]["stop_reason"] == "max_rounds"
    assert _ledger(loop_dir)["stop_reason"] == "max_rounds"
    code, report = _next(capsys, tmp_path, 0.8)          # 멈춘 뒤에도 critic 은 붙는다
    assert report["metrics"]["best"]["round"] == 4


def test_unity_failure_does_not_use_a_round(tmp_path, capsys):
    loop_dir = _setup(tmp_path, capsys, "--no-result", "--exit", "2", "--log-line", "[VFXTOOL] boom")
    code, report = _call(capsys, ["loop", "run", "--work", str(tmp_path / "work")])
    assert code == 2 and report["metrics"]["rounds_used"] == 0
    assert report["issues"][0]["rule"] == "unity.no_result" and "[VFXTOOL] boom" in report["issues"][0]["detail"]
    assert _ledger(loop_dir)["failures"] == 1
    code, report = _call(capsys, ["loop", "run", "--work", str(tmp_path / "work")])
    ledger = _ledger(loop_dir)
    assert ledger["rounds"][0]["failed"] is True and ledger["failures"] == 0
    assert ledger["rounds"][0]["rollback"] is None and ledger["stopped"] is False
    code, report = _call(capsys, ["loop", "best", "--work", str(tmp_path / "work")])
    assert code == 2


def test_bad_critic_and_double_init(tmp_path, capsys):
    _setup(tmp_path, capsys)
    _call(capsys, ["loop", "run", "--work", str(tmp_path / "work")])
    bad = _write(tmp_path / "bad.json", {"score": 2})
    code, _ = _call(capsys, ["loop", "next", "--work", str(tmp_path / "work"), "--critic", bad])
    assert code == 2
    code, _ = _call(capsys, ["loop", "init", str(tmp_path / "recipes" / "hit.json"), "--work",
                             str(tmp_path / "work"), "--project", str(tmp_path / "proj")])
    assert code == 2


def test_lock_file_blocks_a_second_run(tmp_path, capsys):
    loop_dir = _setup(tmp_path, capsys)
    (loop_dir / "loop.lock").write_text("", encoding="utf-8")
    code, report = _call(capsys, ["loop", "run", "--work", str(tmp_path / "work")])
    assert code == 2 and report["issues"][0]["rule"] == "loop.locked"
    (loop_dir / "loop.lock").unlink()
    code, _ = _call(capsys, ["loop", "run", "--work", str(tmp_path / "work")])
    assert code == 0 and not (loop_dir / "loop.lock").exists()


def test_max_flag_and_check_issues_not_ranked(tmp_path, capsys):
    loop_dir = _setup(tmp_path, capsys, init_extra=["--max", "2"])
    _call(capsys, ["loop", "run", "--work", str(tmp_path / "work")])
    tinted = {"layers": {"sparks": {"colorOverLifetime": {"color": {"gradient": {"color": [[0, "p3"]]}}}}}}
    argv = ["loop", "next", "--work", str(tmp_path / "work"), "--patch", _write(tmp_path / "tint.json", tinted),
            "--critic", _write(tmp_path / "c.json", {"score": 0.5})]
    code, report = _call(capsys, argv)
    assert "recipe.color_multiply" in [i["rule"] for i in report["issues"]]  # 보고에는 싣는다
    ledger = _ledger(loop_dir)
    assert ledger["rounds"][1]["warns"] == 0  # 순위에는 안 센다
    assert ledger["stop_reason"] == "max_rounds" and ledger["max_rounds"] == 2


def test_bad_patch_does_not_use_a_round(tmp_path, capsys):
    loop_dir = _setup(tmp_path, capsys)
    _call(capsys, ["loop", "run", "--work", str(tmp_path / "work")])
    argv = ["loop", "next", "--work", str(tmp_path / "work"),
            "--patch", _write(tmp_path / "bad.json", {"profile": "x.json"})]
    code, report = _call(capsys, argv)
    assert code == 1 and report["issues"][0]["rule"] == "patch.fixed_field"
    assert not (loop_dir / "round_2").exists() and _ledger(loop_dir)["pending"]["round"] == 2


def test_init_refuses_bad_name(tmp_path, capsys):
    recipe = json.loads(RECIPE_PATH.read_text(encoding="utf-8"))
    recipe["name"] = "../escape"
    path = tmp_path / "r.json"
    path.write_text(json.dumps(recipe), encoding="utf-8")
    code, report = _call(capsys, ["loop", "init", str(path), "--work", str(tmp_path / "w"),
                                  "--project", str(tmp_path), "--profile", str(PROFILE_PATH)])
    assert code == 2 and not (tmp_path / "escape").exists()


def test_critic_only_next_sets_pending_base(tmp_path, capsys):
    loop_dir = _setup(tmp_path, capsys)
    _call(capsys, ["loop", "run", "--work", str(tmp_path / "work")])
    code, _ = _next(capsys, tmp_path, 0.6, patch=False)          # 1판 판정만 → 다음 판 base 는 1판
    assert code == 0 and _ledger(loop_dir)["pending"] == {"round": 2, "base": 1}
    _next(capsys, tmp_path, 0.6)                                  # 2판을 돈다(1판에서)
    code, _ = _next(capsys, tmp_path, 0.3, patch=False)          # 2판 0.3 → rollback, base 는 다시 1판
    ledger = _ledger(loop_dir)
    assert ledger["rounds"][1]["rollback"] is True and ledger["pending"] == {"round": 3, "base": 1}
