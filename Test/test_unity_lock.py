"""잠금 — 같은 프로젝트를 연 Unity · Temp/UnityLockfile 배타 열기."""

import os

import pytest

from vfxtool.errors import VfxError
from vfxtool.unity import lock

pytestmark = pytest.mark.skipif(os.name != "nt", reason="윈도 잠금 의미")


def _lockfile(project):
    path = project / "Temp" / "UnityLockfile"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"")
    return path


def test_free_without_lockfile(tmp_path):
    assert lock.check_lock(tmp_path, processes=[]) == lock.FREE


def test_stale_lockfile_is_passed(tmp_path):
    _lockfile(tmp_path)
    assert lock.check_lock(tmp_path, processes=[]) == lock.STALE


def test_held_lockfile_is_refused(tmp_path):
    path = _lockfile(tmp_path)
    with open(path, "rb"):
        with pytest.raises(VfxError, match="UnityLockfile"):
            lock.check_lock(tmp_path, processes=[])
    # 손잡이를 놓으면 다시 남은 잠금
    assert lock.check_lock(tmp_path, processes=[]) == lock.STALE


def test_same_project_process_is_refused(tmp_path):
    line = f'"C:\\U\\Unity.exe" -projectpath "{str(tmp_path).upper()}\\"'
    with pytest.raises(VfxError, match="11"):
        lock.check_lock(tmp_path, processes=[{"ProcessId": 11, "CommandLine": line}])


def test_other_project_process_is_ignored(tmp_path):
    line = f"Unity.exe -batchmode -projectPath {tmp_path / 'other'}"
    rows = [{"ProcessId": 12, "CommandLine": line}]
    assert lock.check_lock(tmp_path, processes=rows) == lock.FREE


@pytest.mark.parametrize("command_line", [None, "", "Unity.exe -batchmode"])
def test_unreadable_command_line_counts_as_open(tmp_path, command_line):
    rows = [{"ProcessId": 13, "CommandLine": command_line}]
    with pytest.raises(VfxError):
        lock.check_lock(tmp_path, processes=rows)


def test_project_from_command_line():
    assert lock.project_from_command_line('x -projectPath "C:\\a b\\p" -y') == "C:\\a b\\p"
    assert lock.project_from_command_line("x -PROJECTPATH C:\\p -y") == "C:\\p"


def test_real_process_query_returns_list():
    assert isinstance(lock.list_unity_processes(), list)
