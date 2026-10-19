"""같은 프로젝트를 연 Unity 가 있나 본다. 있으면 종료 2, 남은 Temp/UnityLockfile 만 있으면 진행."""

import json
import os
import re
import subprocess
from pathlib import Path

from vfxtool.errors import VfxError

FREE = "free"
STALE = "stale"

_PROJECT_ARG = re.compile(r'-projectPath\s+(?:"([^"]+)"|(\S+))', re.IGNORECASE)
_PS_QUERY = (
    "Get-CimInstance Win32_Process -Filter \"Name='Unity.exe'\" | "
    "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
)


def normalize(path: str | Path) -> str:
    """대소문자 · 구분자 · 끝 슬래시를 맞춰 경로 둘을 견줄 수 있게 한다."""
    return os.path.normcase(os.path.abspath(str(path))).rstrip("\\/")


def project_from_command_line(command_line: str | None) -> str | None:
    """명령줄에서 -projectPath 값을 꺼낸다. 못 읽으면 None."""
    if not command_line:
        return None
    match = _PROJECT_ARG.search(command_line)
    if match is None:
        return None
    return match.group(1) or match.group(2)


def list_unity_processes() -> list[dict]:
    """떠 있는 Unity.exe 의 {ProcessId, CommandLine} 목록. 못 읽으면 VfxError."""
    try:
        done = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_QUERY],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VfxError(f"Unity 프로세스 목록을 못 읽었다 — {exc}") from exc

    if done.returncode != 0:
        raise VfxError(f"Unity 프로세스 목록을 못 읽었다 — {done.stderr.strip()}")
    text = done.stdout.strip()
    if not text:
        return []
    try:
        rows = json.loads(text)
    except json.JSONDecodeError as exc:
        raise VfxError(f"Unity 프로세스 목록을 못 읽었다 — JSON 이 깨졌다 ({exc.msg})") from None
    if isinstance(rows, dict):
        return [rows]
    return rows


def find_blocking_pids(project: Path, processes: list[dict]) -> list[int]:
    """같은 프로젝트를 연 Unity 의 pid. 명령줄을 못 읽은 프로세스도 「연 것」으로 센다."""
    target = normalize(project)
    pids = []
    for row in processes:
        opened = project_from_command_line(row.get("CommandLine"))
        if opened is None or normalize(opened) == target:
            pids.append(int(row.get("ProcessId", 0)))
    return pids


def lockfile_held(lockfile: Path) -> bool:
    """다른 손잡이가 쥐고 있으면 True. 공유 없이(share 0) 열어 보고 바로 닫는다."""
    if os.name != "nt":
        return False

    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    generic_read_write = 0x80000000 | 0x40000000
    open_existing = 3
    handle = kernel32.CreateFileW(str(lockfile), generic_read_write, 0, None, open_existing, 0, None)
    if handle == wintypes.HANDLE(-1).value:
        return True
    kernel32.CloseHandle(handle)
    return False


def check_lock(project: Path, processes: list[dict] | None = None) -> str:
    """진행해도 되면 FREE 나 STALE(남은 잠금)을 돌려준다. 막히면 VfxError(종료 2)."""
    if processes is None:
        processes = list_unity_processes()

    pids = find_blocking_pids(project, processes)
    if pids:
        raise VfxError(
            f"같은 프로젝트를 연 Unity 가 떠 있다(pid {pids}). 에디터를 닫고 다시 돌린다"
        )

    lockfile = project / "Temp" / "UnityLockfile"
    if not lockfile.exists():
        return FREE
    if lockfile_held(lockfile):
        raise VfxError(f"{lockfile} 를 누가 쥐고 있다. 그 프로그램을 닫고 다시 돌린다")
    return STALE
