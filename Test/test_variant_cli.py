"""`vfxtool variant expand · run · sheet` — 종료 코드 0/1/2 · 보고 JSON 칸 · --force 가 done 판을 안 건드림 · 가짜 Unity 로 run."""

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from conftest import SRC, write_set
from vfxtool import cli
from vfxtool.unity import lock


def _run(*args):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC)
    done = subprocess.run([sys.executable, "-m", "vfxtool", "variant", *args], capture_output=True, env=env, timeout=60)
    return done.returncode, json.loads(done.stdout.decode("utf-8"))


def test_expand_ok(tmp_path):
    path = write_set(tmp_path / "in")
    code, report = _run("expand", str(path), "--work", str(tmp_path / "work"))
    assert code == 0
    assert report["status"] == "ok"
    metrics = report["metrics"]
    assert metrics["counts"] == {"total": 12, "expanded": 12, "failed": 0, "done": 0}
    assert metrics["set"].endswith("work/hit/set.json")
    assert metrics["next"] == "variant run"
    first = metrics["variants"][0]
    assert list(first) == ["name", "attr", "tier", "seed", "state", "errors", "warns", "seconds", "notes"]
    assert (first["name"], first["seed"], first["seconds"]) == ("hit_fire_weak_s0", 1000, None)


def test_expand_failed_variant_exits_1(tmp_path):
    path = write_set(tmp_path / "in", attrs=["fire"], tiers=["mid", {"name": "huge", "mul": {"life": 1.5}}], seeds=1)
    code, report = _run("expand", str(path), "--work", str(tmp_path / "work"))
    assert code == 1
    assert report["status"] == "fail"
    assert report["metrics"]["counts"]["failed"] == 1
    item = report["issues"][0]
    assert (item["rule"], item["variant"]) == ("variant.tier_range", "hit_fire_huge")


def test_expand_bad_set_exits_2_and_writes_nothing(tmp_path):
    path = write_set(tmp_path / "in", attrs=["wind"])
    code, report = _run("expand", str(path), "--work", str(tmp_path / "work"))
    assert code == 2
    assert report["status"] == "error"
    assert not (tmp_path / "work").exists()


def test_no_action_exits_2(tmp_path):
    code, report = _run()
    assert code == 2


def test_force_keeps_done_variant(tmp_path):
    path = write_set(tmp_path / "in", attrs=["fire"], tiers=["weak", "mid"], seeds=1)
    work = tmp_path / "work"
    assert _run("expand", str(path), "--work", str(work))[0] == 0
    ledger_path = work / "hit" / "set.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger["variants"][0]["state"] = "done"
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
    done_recipe = work / "hit" / "hit_fire_weak" / "recipe.json"
    done_recipe.write_text("손으로 고친 판", encoding="utf-8")
    other_recipe = work / "hit" / "hit_fire_mid" / "recipe.json"
    other_recipe.write_text("{}", encoding="utf-8")
    assert _run("expand", str(path), "--work", str(work))[0] == 2
    code, report = _run("expand", str(path), "--work", str(work), "--force")
    assert code == 0
    assert report["metrics"]["counts"] == {"total": 2, "expanded": 1, "failed": 0, "done": 1}
    assert done_recipe.read_text(encoding="utf-8") == "손으로 고친 판"
    assert json.loads(other_recipe.read_text(encoding="utf-8"))["name"] == "hit_fire_mid"


# --- run · sheet (가짜 Unity, 프로세스 안에서 cli.main) -------------------------------------------

FAKE_UNITY = Path(__file__).parent / "data" / "unity" / "fake_unity.py"


def _call(capsys, argv):
    code = cli.main(argv)
    return code, json.loads(capsys.readouterr().out)


def _project(tmp_path):
    settings = tmp_path / "proj" / "ProjectSettings"
    settings.mkdir(parents=True)
    (settings / "ProjectVersion.txt").write_text("m_EditorVersion: 6000.3.23f1\n", encoding="utf-8")
    return settings.parent


def _fake_unity(tmp_path, *extra):
    dot = np.zeros((256, 256, 4), dtype=np.uint8)
    dot[120:136, 120:136] = [0xFF, 0xC2, 0x3D, 255]
    Image.fromarray(dot, "RGBA").save(tmp_path / "dot.png")
    parts = [sys.executable, str(FAKE_UNITY), "--frame-png", str(tmp_path / "dot.png")] + list(extra)
    return " ".join(f'"{part}"' for part in parts)


def _expanded(tmp_path, capsys, **fields):
    path = write_set(tmp_path / "in", **fields)
    code, _ = _call(capsys, ["variant", "expand", str(path), "--work", str(tmp_path / "work")])
    assert code == 0
    return tmp_path / "work" / "hit"


def test_run_with_fake_unity_then_sheet(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(lock, "list_unity_processes", lambda: [])
    set_dir = _expanded(tmp_path, capsys, attrs=["fire", "ice"], tiers=["mid"], seeds=1)
    code, built = _call(capsys, ["variant", "run", "--work", str(set_dir), "--project", str(_project(tmp_path)),
                                 "--unity", _fake_unity(tmp_path)])
    assert code == 0, built["issues"]
    metrics = built["metrics"]
    assert metrics["counts"] == {"total": 2, "expanded": 0, "failed": 0, "done": 2}
    assert metrics["next"] is None
    assert [Path(s["path"]).name for s in metrics["sheets"]] == ["overview.png", "strips_1.png"]
    timing = metrics["timing"]
    assert timing["measured"] == 2 and timing["unity_inside"] == 0.4
    seconds = metrics["variants"][0]["seconds"]
    assert (seconds["unity_build"], seconds["unity_render"]) == (0.1, 0.1)
    for name in ("hit_fire_mid", "hit_ice_mid"):
        assert (set_dir / name / "measure.json").is_file()
        assert (set_dir / name / "sheet.png").is_file()
    assert abs(timing["startup_ratio"] - (1 - 0.4 / timing["wall_total"])) < 0.002
    assert (timing["mode"], timing["retries"]) == ("batch", 0)
    assert metrics["variants"][0]["seconds"]["wall"] is None

    code, built = _call(capsys, ["variant", "sheet", "--work", str(set_dir)])
    assert code == 0
    assert built["metrics"]["sheets"][0]["size"] == list(Image.open(set_dir / "overview.png").size)


def test_run_failure_exits_1_and_keeps_going(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(lock, "list_unity_processes", lambda: [])
    set_dir = _expanded(tmp_path, capsys, attrs=["fire", "ice"], tiers=["mid"], seeds=1)
    code, built = _call(capsys, ["variant", "run", "--work", str(set_dir), "--project", str(_project(tmp_path)),
                                 "--unity", _fake_unity(tmp_path, "--status", "error"), "--no-sheet"])
    assert code == 1
    assert built["metrics"]["counts"]["failed"] == 2
    assert [(i["rule"], i["variant"]) for i in built["issues"]] == [("variant.run", "hit_fire_mid"), ("variant.run", "hit_ice_mid")]
    assert built["metrics"]["sheets"] is None
    assert not (set_dir / "overview.png").exists()


def test_run_each_runs_unity_per_variant(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(lock, "list_unity_processes", lambda: [])
    set_dir = _expanded(tmp_path, capsys, attrs=["fire", "ice"], tiers=["mid"], seeds=1)
    code, built = _call(capsys, ["variant", "run", "--work", str(set_dir), "--project", str(_project(tmp_path)),
                                 "--unity", _fake_unity(tmp_path), "--each", "--no-sheet"])
    assert code == 0, built["issues"]
    timing = built["metrics"]["timing"]
    assert (timing["mode"], timing["retries"], timing["unity_wall"]) == ("each", 0, None)
    assert built["metrics"]["variants"][0]["seconds"]["wall"] > 0
    assert (set_dir / "hit_fire_mid" / "unity.log").is_file()
    assert not (set_dir / "jobs.json").exists()


def test_run_refuses_work_inside_project_and_lock(tmp_path, capsys):
    project = _project(tmp_path)
    path = write_set(tmp_path / "in", attrs=["fire"], tiers=["mid"], seeds=1)
    assert _call(capsys, ["variant", "expand", str(path), "--work", str(project / "fx")])[0] == 0
    code, built = _call(capsys, ["variant", "run", "--work", str(project / "fx" / "hit"), "--project", str(project)])
    assert code == 2
    assert "Unity 프로젝트 밖" in built["issues"][0]["detail"]

    set_dir = _expanded(tmp_path, capsys, attrs=["fire"], tiers=["mid"], seeds=1)
    (set_dir / "set.lock").write_text("", encoding="utf-8")
    code, built = _call(capsys, ["variant", "run", "--work", str(set_dir), "--project", str(project)])
    assert code == 2
    assert built["issues"][0]["rule"] == "variant.locked"


def test_sheet_without_set_json_exits_2(tmp_path, capsys):
    code, built = _call(capsys, ["variant", "sheet", "--work", str(tmp_path)])
    assert code == 2
    assert built["status"] == "error"
