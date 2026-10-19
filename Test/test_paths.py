"""경로 감옥 · JSON 읽기 쓰기 · doctor 의 Unity 판 읽기."""

import subprocess

import pytest

from vfxtool.unity.locate import read_editor_version
from vfxtool.errors import VfxError
from vfxtool.paths import ensure_inside, read_json, write_json


def test_inside_ok(tmp_path):
    (tmp_path / "a").mkdir()
    assert ensure_inside("a/b.png", tmp_path) == (tmp_path / "a" / "b.png").resolve()


def test_dotdot_rejected(tmp_path):
    with pytest.raises(VfxError):
        ensure_inside("../x.png", tmp_path / "root")


def test_absolute_outside_rejected(tmp_path):
    with pytest.raises(VfxError):
        ensure_inside(tmp_path.parent / "x.png", tmp_path)


def test_symlink_rejected(tmp_path):
    target = tmp_path / "real"
    target.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("이 PC 는 심볼릭 링크를 못 만든다(권한)")
    with pytest.raises(VfxError):
        ensure_inside("link/x.png", tmp_path)


def test_junction_rejected(tmp_path):
    target = tmp_path / "real"
    target.mkdir()
    link = tmp_path / "junction"
    done = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
    if done.returncode != 0 or not link.exists():
        pytest.skip("이 PC 는 junction 을 못 만든다(윈도 전용)")
    with pytest.raises(VfxError):
        ensure_inside("junction/x.png", tmp_path)


def test_write_json_is_lf_utf8(tmp_path):
    path = write_json(tmp_path / "sub" / "o.json", {"이름": [1, 2]})
    data = path.read_bytes()
    assert b"\r\n" not in data
    assert data.endswith(b"\n")
    assert "이름".encode("utf-8") in data
    assert read_json(path) == {"이름": [1, 2]}


def test_read_json_errors(tmp_path):
    with pytest.raises(VfxError):
        read_json(tmp_path / "none.json")
    bad = tmp_path / "bad.json"
    bad.write_text("[1,", encoding="utf-8")
    with pytest.raises(VfxError):
        read_json(bad)


def test_unity_version(tmp_path):
    settings = tmp_path / "ProjectSettings"
    settings.mkdir()
    (settings / "ProjectVersion.txt").write_text(
        "m_EditorVersion: 6000.3.23f1\nm_EditorVersionWithRevision: 6000.3.23f1 (abc)\n", encoding="utf-8"
    )
    assert read_editor_version(tmp_path) == "6000.3.23f1"
    with pytest.raises(VfxError):
        read_editor_version(tmp_path / "nope")
