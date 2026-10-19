"""`python -m vfxtool` — 종료 코드 0 / 1 / 2 · 보고 JSON · 명령 표."""

import json
import os
import subprocess
import sys

from conftest import DATA, RECIPE_PATH, SRC
from vfxtool import cli


def _run(*args):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC)
    done = subprocess.run(
        [sys.executable, "-m", "vfxtool", *args],
        capture_output=True, env=env, timeout=60,
    )
    return done.returncode, done.stdout.decode("utf-8"), done.stderr.decode("utf-8", errors="replace")


def test_help_runs():
    code, _, _ = _run("--help")
    assert code == 0


def test_check_ok_writes_resolved(tmp_path):
    out = tmp_path / "resolved.json"
    code, stdout, _ = _run("check", str(RECIPE_PATH), "--input-root", str(DATA), "--out", str(out))
    assert code == 0
    report = json.loads(stdout)
    assert report["status"] == "ok"
    assert report["metrics"]["layers"] == 1
    assert out.read_bytes() == (DATA / "golden" / "hit_sparks_a.resolved.json").read_bytes()


def test_check_rule_error_is_exit1(tmp_path):
    recipe = json.loads(RECIPE_PATH.read_text(encoding="utf-8"))
    recipe["layers"][0]["main"]["startSize"] = 5
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(recipe), encoding="utf-8")
    out = tmp_path / "resolved.json"
    code, stdout, _ = _run("check", str(path), "--profile", str(DATA / "profile.json"), "--out", str(out))
    assert code == 1
    report = json.loads(stdout)
    assert report["status"] == "fail"
    assert report["issues"][0]["rule"] == "recipe.pixel_size"
    assert set(report["issues"][0]) == {"rule", "layer", "frame", "severity", "detail", "hint"}
    assert not out.exists()


def test_check_missing_file_is_exit2(tmp_path):
    code, stdout, _ = _run("check", str(tmp_path / "nope.json"))
    assert code == 2
    assert json.loads(stdout)["status"] == "error"


def test_check_broken_json_is_exit2(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{ nope", encoding="utf-8")
    code, stdout, _ = _run("check", str(path))
    assert code == 2
    assert "JSON" in json.loads(stdout)["issues"][0]["detail"]


def test_bad_argument_is_exit2():
    code, stdout, _ = _run("check")
    assert code == 2
    assert json.loads(stdout)["status"] == "error"


def test_bad_sub_argument_and_no_command_are_json():
    code, stdout, _ = _run("loop", "run", "--nope")
    assert code == 2
    assert "인자 오류" in json.loads(stdout)["issues"][0]["detail"]
    code, stdout, _ = _run()
    assert code == 2
    assert json.loads(stdout)["status"] == "error"


def test_template_list_and_show():
    code, stdout, _ = _run("template", "list")
    assert code == 0
    names = [item["name"] for item in json.loads(stdout)["metrics"]["templates"]]
    assert {"hit_sparks", "land_dust", "sparkle", "ambient_motes", "heal_rise"} <= set(names)
    code, stdout, _ = _run("template", "show", "heal_rise")
    assert code == 0
    shown = [p["name"] for p in json.loads(stdout)["metrics"]["params"]]
    start = shown.index("glow")
    # 소재 짝 파라미터(<층>_tex · <층>_size)는 params 끝에 붙는다(변형묶음설계 5절).
    assert shown[start:start + 3] == ["glow", "glow_color", "streak"] and shown[-1] == "rest_size"
    code, stdout, _ = _run("template", "show", "hit_spark")
    assert code == 2
    assert "hit_sparks" in json.loads(stdout)["issues"][0]["detail"]


def test_help_lists_all_commands():
    code, stdout, _ = _run("--help")
    for name in ("profile", "check", "patch", "build", "render", "measure", "sheet", "gif", "loop", "template", "variant", "doctor"):
        assert f"    {name} " in stdout


def test_doctor_reports_packages():
    code, stdout, _ = _run("doctor")
    report = json.loads(stdout)
    assert code == 0
    assert report["metrics"]["packages"]["numpy"]


def test_command_table_has_thirteen():
    assert len(cli.COMMANDS) == 13
    assert all(hasattr(module, "add_parser") and hasattr(module, "run") for module in cli.COMMANDS.values())


def test_doctor_reads_unity_version(tmp_path):
    settings = tmp_path / "ProjectSettings"
    settings.mkdir()
    (settings / "ProjectVersion.txt").write_text("m_EditorVersion: 0000.0.0f0\n", encoding="utf-8")
    os.environ.pop("VFXTOOL_UNITY", None)
    code, stdout, _ = _run("doctor", "--project", str(tmp_path))
    report = json.loads(stdout)
    assert report["metrics"]["unity_version"] == "0000.0.0f0"
    assert report["metrics"]["unity_exe"] is None
    assert code in (0, 1)


def test_doctor_lock_and_manifest(tmp_path, monkeypatch, capsys):
    from argparse import Namespace

    from vfxtool.commands import doctor
    from vfxtool.unity import lock

    monkeypatch.setattr(lock, "list_unity_processes", lambda: [])
    monkeypatch.setenv("VFXTOOL_UNITY", sys.executable)
    settings = tmp_path / "ProjectSettings"
    settings.mkdir()
    (settings / "ProjectVersion.txt").write_text("m_EditorVersion: 0000.0.0f0\n", encoding="utf-8")
    packages = tmp_path / "Packages"
    packages.mkdir()
    (packages / "manifest.json").write_text('{"dependencies": {"com.officina.vfx": "file:x"}}', encoding="utf-8")
    doctor.run(Namespace(project=str(tmp_path)))
    report = json.loads(capsys.readouterr().out)
    assert report["metrics"]["lock"] == "free"
    assert report["metrics"]["vfx_package"] is True
    rules = {item["rule"] for item in report["issues"]}
    assert {"doctor.lock", "doctor.manifest", "doctor.newtonsoft"} <= rules

    (packages / "manifest.json").write_text('{"dependencies": {}}', encoding="utf-8")
    doctor.run(Namespace(project=str(tmp_path)))
    assert json.loads(capsys.readouterr().out)["metrics"]["vfx_package"] is False
