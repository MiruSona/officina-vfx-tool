"""Unity.exe 찾기 — ProjectVersion.txt · --unity · VFXTOOL_UNITY."""

import sys

import pytest

from vfxtool.errors import VfxError
from vfxtool.unity import locate


def _project(tmp_path, version="6000.3.23f1"):
    settings = tmp_path / "proj" / "ProjectSettings"
    settings.mkdir(parents=True)
    (settings / "ProjectVersion.txt").write_text(
        f"m_EditorVersion: {version}\nm_EditorVersionWithRevision: {version} (abc)\n",
        encoding="utf-8")
    return tmp_path / "proj"


def test_read_version(tmp_path):
    assert locate.read_editor_version(_project(tmp_path)) == "6000.3.23f1"


def test_not_a_project(tmp_path):
    with pytest.raises(VfxError):
        locate.read_editor_version(tmp_path)


def test_hub_path_from_program_files(tmp_path, monkeypatch):
    monkeypatch.delenv(locate.ENV_NAME, raising=False)
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "pf"))
    project = _project(tmp_path)
    with pytest.raises(VfxError, match="6000.3.23f1"):
        locate.locate_unity(project)

    exe = tmp_path / "pf" / "Unity" / "Hub" / "Editor" / "6000.3.23f1" / "Editor" / "Unity.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    assert locate.locate_unity(project) == [str(exe)]


def test_override_beats_env(tmp_path, monkeypatch):
    monkeypatch.setenv(locate.ENV_NAME, "nothing-here.exe")
    fake = tmp_path / "fake.py"
    fake.write_text("", encoding="utf-8")
    command = locate.locate_unity(tmp_path, f'"{sys.executable}" "{fake}" --exit 1')
    assert command == [sys.executable, str(fake), "--exit", "1"]


def test_env_used_when_no_override(tmp_path, monkeypatch):
    exe = tmp_path / "Unity.exe"
    exe.write_bytes(b"")
    monkeypatch.setenv(locate.ENV_NAME, str(exe))
    assert locate.locate_unity(tmp_path) == [str(exe)]


def test_missing_override(tmp_path):
    with pytest.raises(VfxError):
        locate.locate_unity(tmp_path, str(tmp_path / "no" / "Unity.exe"))
