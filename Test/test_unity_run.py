"""가짜 Unity(data/unity/fake_unity.py)로 run · build · render 명령을 돈다. 진짜 Unity 는 안 띄운다."""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from vfxtool.errors import VfxError
from vfxtool.unity import command, lock, run

FAKE = Path(__file__).parent / "data" / "unity" / "fake_unity.py"


def _fake(*extra):
    return [sys.executable, str(FAKE), *extra]


def _job(tmp_path, frames=None):
    job = {"recipe": "r", "mode": "render", "saveRoot": "Assets/Vfx/Generated",
           "outDir": str(tmp_path / "frames"), "frames": frames or [], "backgrounds": ["transparent"]}
    path = tmp_path / "job.json"
    path.write_text(json.dumps(job), encoding="utf-8")
    return path


def _args(tmp_path, job_path):
    return run.build_args(tmp_path / "proj", tmp_path / "unity.log", job_path)


def _alive(pid):
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                         capture_output=True, text=True).stdout
    return str(pid) in out.split()


@pytest.mark.parametrize("code", [0, 1, 2])
def test_run_returns_exit_code(tmp_path, code):
    job_path = _job(tmp_path)
    assert run.run_unity(_fake("--exit", str(code)), _args(tmp_path, job_path), timeout=60) == code


def test_args_shape(tmp_path):
    job_path = _job(tmp_path)
    args_file = tmp_path / "args.json"
    run.run_unity(_fake("--args-file", str(args_file)), _args(tmp_path, job_path), timeout=60)
    seen = json.loads(args_file.read_text(encoding="utf-8"))
    unity_part = seen[2:]
    assert unity_part[0] == "-batchmode"
    assert unity_part[unity_part.index("-executeMethod") + 1] == run.ENTRY_METHOD
    assert unity_part[unity_part.index("-vfxJob") + 1] == str(job_path)
    assert "-nographics" not in unity_part


def test_nographics_refused(tmp_path):
    job_path = _job(tmp_path)
    with pytest.raises(VfxError, match="nographics"):
        run.run_unity(_fake(), _args(tmp_path, job_path) + ["-nographics"], timeout=60)
    with pytest.raises(VfxError):
        run.run_unity(_fake("-NoGraphics"), _args(tmp_path, job_path), timeout=60)


def test_timeout_kills_tree(tmp_path):
    job_path = _job(tmp_path)
    pid_file = tmp_path / "child.pid"
    started = time.monotonic()
    with pytest.raises(VfxError, match="끊었다"):
        run.run_unity(_fake("--sleep", "60", "--child-pid-file", str(pid_file)),
                      _args(tmp_path, job_path), timeout=4)
    assert time.monotonic() - started < 30
    child = int(pid_file.read_text(encoding="utf-8"))
    for _ in range(20):
        if not _alive(child):
            break
        time.sleep(0.25)
    assert not _alive(child)


def test_log_issues(tmp_path):
    log = tmp_path / "unity.log"
    log.write_text("ok line\nAssets/x.cs(1,2): error CS0103: no name\n"
                   "NullReferenceException: boom\nfine\n", encoding="utf-8")
    issues = run.log_issues(log)
    assert [i["rule"] for i in issues] == ["unity.log", "unity.log"]
    assert "CS0103" in issues[0]["detail"]
    assert run.log_issues(tmp_path / "none.log") == []


# --- build · render 명령 ---------------------------------------------------------------


def _project(tmp_path):
    settings = tmp_path / "proj" / "ProjectSettings"
    settings.mkdir(parents=True)
    (settings / "ProjectVersion.txt").write_text("m_EditorVersion: 6000.3.23f1\n", encoding="utf-8")
    return tmp_path / "proj"


def _resolved_file(tmp_path, loop=False):
    data = {"version": 1, "name": "hit", "duration": 0.5, "fps": 12, "loop": loop,
            "layers": [{"name": "sparks", "main": {"startLifetime": {"random": [0.25, 0.45]}}}]}
    path = tmp_path / "round_1" / "resolved.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _cli(argv):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    command.add_build_parser(sub)
    command.add_render_parser(sub)
    return parser.parse_args(argv)


def _unity_flag(*extra):
    return " ".join(f'"{part}"' for part in _fake(*extra))


@pytest.fixture(autouse=True)
def _no_real_unity(monkeypatch):
    monkeypatch.setattr(lock, "list_unity_processes", lambda: [])


def _run_cli(capsys, argv):
    args = _cli(argv)
    code = command.run(args)
    return code, json.loads(capsys.readouterr().out)


def test_render_ok(tmp_path, capsys):
    project, resolved = _project(tmp_path), _resolved_file(tmp_path)
    work = tmp_path / "work"
    code, report = _run_cli(capsys, ["render", str(resolved), "--project", str(project),
                                     "--work", str(work), "--unity", _unity_flag()])
    assert code == 0 and report["status"] == "ok"
    job = json.loads((work / "job.json").read_text(encoding="utf-8"))
    assert job["mode"] == "render" and len(job["frames"]) == 12  # (0.5+0.45)*12 = 11.4 → 12
    assert job["outDir"] == str((work / "frames").resolve())
    assert report["metrics"]["frames"] == 12
    assert report["metrics"]["t0_skipped"] is True
    copied = json.loads((work / "resolved.json").read_text(encoding="utf-8"))
    assert copied == json.loads(resolved.read_text(encoding="utf-8"))


def test_render_issues_and_backgrounds(tmp_path, capsys):
    project, resolved = _project(tmp_path), _resolved_file(tmp_path)
    work = tmp_path / "work"
    code, report = _run_cli(capsys, ["render", str(resolved), "--project", str(project),
                                     "--work", str(work), "--fps", "16", "--backgrounds", "black,white",
                                     "--unity", _unity_flag("--status", "issues", "--exit", "1")])
    assert code == 1 and report["status"] == "fail"
    assert report["issues"][0]["rule"] == "build.unknown_field"
    job = json.loads((work / "job.json").read_text(encoding="utf-8"))
    assert job["backgrounds"] == ["black", "white"] and len(job["frames"]) == 16


def test_build_default_work_and_error_log(tmp_path, capsys):
    project, resolved = _project(tmp_path), _resolved_file(tmp_path)
    flag = _unity_flag("--no-result", "--exit", "2", "--log-line", "x.cs(1,1): error CS1002: ;")
    code, report = _run_cli(capsys, ["build", str(resolved), "--project", str(project), "--unity", flag])
    assert code == 2 and report["status"] == "error"
    rules = [i["rule"] for i in report["issues"]]
    assert rules == ["unity.no_result", "unity.log"]
    job = json.loads((resolved.parent / "job.json").read_text(encoding="utf-8"))
    assert job["mode"] == "build" and job["frames"] == []


def test_result_ok_but_crash_code_is_error(tmp_path, capsys):
    project, resolved = _project(tmp_path), _resolved_file(tmp_path)
    code, _ = _run_cli(capsys, ["build", str(resolved), "--project", str(project),
                                "--unity", _unity_flag("--exit", "-1")])
    assert code == 2


def test_stale_lock_is_info(tmp_path, capsys):
    project, resolved = _project(tmp_path), _resolved_file(tmp_path)
    (project / "Temp").mkdir()
    (project / "Temp" / "UnityLockfile").write_bytes(b"")
    code, report = _run_cli(capsys, ["build", str(resolved), "--project", str(project),
                                     "--unity", _unity_flag()])
    assert code == 0
    assert report["issues"][0]["rule"] == "unity.stale_lock"
    assert report["metrics"]["lock"] == lock.STALE


def test_open_editor_is_refused(tmp_path, capsys, monkeypatch):
    project, resolved = _project(tmp_path), _resolved_file(tmp_path)
    rows = [{"ProcessId": 7, "CommandLine": f'Unity.exe -projectPath "{project}"'}]
    monkeypatch.setattr(lock, "list_unity_processes", lambda: rows)
    code, report = _run_cli(capsys, ["build", str(resolved), "--project", str(project),
                                     "--unity", _unity_flag()])
    assert code == 2 and "pid" in report["issues"][0]["detail"]


def test_bad_save_root_and_missing_project(tmp_path, capsys):
    project, resolved = _project(tmp_path), _resolved_file(tmp_path)
    code, _ = _run_cli(capsys, ["build", str(resolved), "--project", str(project),
                                "--save-root", "../Outside", "--unity", _unity_flag()])
    assert code == 2
    code, _ = _run_cli(capsys, ["build", str(resolved), "--project", str(tmp_path / "nope"),
                                "--unity", _unity_flag()])
    assert code == 2
    code, report = _run_cli(capsys, ["build", str(resolved), "--project", str(project),
                                     "--work", str(project / "Temp" / "w"), "--unity", _unity_flag()])
    assert code == 2 and "밖" in report["issues"][0]["detail"]


def test_render_timeout_is_error(tmp_path, capsys):
    project, resolved = _project(tmp_path), _resolved_file(tmp_path)
    code, report = _run_cli(capsys, ["render", str(resolved), "--project", str(project),
                                     "--work", str(tmp_path / "w"), "--timeout", "3",
                                     "--unity", _unity_flag("--sleep", "60")])
    assert code == 2 and "끊었다" in report["issues"][0]["detail"]


def test_no_result_detail_carries_vfxtool_lines(tmp_path, capsys):
    project, resolved = _project(tmp_path), _resolved_file(tmp_path)
    flag = _unity_flag("--no-result", "--exit", "2", "--log-line", "[VFXTOOL] job 을 못 읽었다",
                       "--log-line", "NullReferenceException: x")
    code, report = _run_cli(capsys, ["build", str(resolved), "--project", str(project), "--unity", flag])
    assert code == 2
    first = report["issues"][0]
    assert first["rule"] == "unity.no_result"
    assert "[VFXTOOL] job 을 못 읽었다" in first["detail"] and "NullReferenceException" in first["detail"]


def test_result_graphics_device_passes(tmp_path):
    result = tmp_path / "result.json"
    result.write_text(json.dumps({"status": "ok", "frames": [], "graphicsDevice": "Direct3D11"}), encoding="utf-8")
    report = command._merge_result(0, result, [], {}, tmp_path / "unity.log")
    assert report["status"] == "ok" and report["metrics"]["graphicsDevice"] == "Direct3D11"


def test_no_result_lines_skip_stack(tmp_path):
    log = tmp_path / "unity.log"
    log.write_text("\n".join([
        "[VFXTOOL] job 을 못 읽었다",
        "NullReferenceException: Object reference not set",
        "UnityEngine.DebugLogHandler:Internal_LogException (System.Exception,UnityEngine.Object)",
        "  at Officina.Vfx.Editor.VfxEntry.Run () [0x00000] in <abc>:0",
        "Officina.Vfx.Editor.VfxEntry:Run () (at ./Library/x.cs:30)",
        "plain line",
    ]), encoding="utf-8")
    assert run.no_result_lines(log) == ["[VFXTOOL] job 을 못 읽었다", "NullReferenceException: Object reference not set"]


def test_result_issue_hint_filled_from_rule_hints():
    from vfxtool.measure_rules import load_rule_hints

    hints = load_rule_hints()
    for rule in ("entry.bug", "render.frames_capped", "build.texture_bad"):
        item = command._result_issue({"rule": rule, "severity": "warn", "detail": "x"}, hints)
        assert item["hint"], rule
    kept = command._result_issue({"rule": "build.texture_bad", "detail": "x", "hint": ["main"]}, hints)
    assert kept["hint"] == ["main"]
