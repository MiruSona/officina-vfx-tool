"""Unity 를 숨긴 창으로 배치 실행하고, 시간이 넘으면 프로세스 나무째 끊는다 (설계 5-4 · 6-2)."""

import re
import subprocess
from pathlib import Path

from vfxtool.errors import VfxError
from vfxtool.report import issue

ENTRY_METHOD = "Officina.Vfx.Editor.VfxEntry.Run"
DEFAULT_TIMEOUT = 300
_MAX_LOG_ISSUES = 20
_LOG_MARKERS = ("error CS", "Exception")


def build_args(project: Path, log_file: Path, job_file: Path) -> list[str]:
    """Unity 에 넘길 인자. 나머지 설정은 다 job.json 에 둔다."""
    return [
        "-batchmode",
        "-projectPath", str(project),
        "-logFile", str(log_file),
        "-executeMethod", ENTRY_METHOD,
        "-vfxJob", str(job_file),
    ]


def reject_nographics(command: list[str]) -> None:
    """-nographics 는 GPU 장치를 끄므로 렌더가 빈 그림이 된다(실측 ①)."""
    if any(part.lower() == "-nographics" for part in command):
        raise VfxError("-nographics 는 쓸 수 없다 — 배치 렌더에 GPU 장치가 필요하다")


def kill_tree(pid: int) -> None:
    """Unity 가 띄운 자식(셰이더 컴파일러 등)까지 같이 끊는다."""
    subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    )


def _hidden_window_options() -> dict:
    if not hasattr(subprocess, "STARTUPINFO"):
        return {}
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    info.wShowWindow = 0  # SW_HIDE
    return {"startupinfo": info, "creationflags": subprocess.CREATE_NO_WINDOW}


def run_unity(unity: list[str], args: list[str], timeout: float = DEFAULT_TIMEOUT) -> int:
    """Unity 를 돌려 종료 코드를 돌려준다. 시간이 넘으면 나무째 끊고 VfxError(종료 2)."""
    command = unity + args
    reject_nographics(command)

    try:
        proc = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, **_hidden_window_options(),
        )
    except OSError as exc:
        raise VfxError(f"Unity 를 못 띄웠다 — {exc}") from exc

    try:
        return proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_tree(proc.pid)
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            raise VfxError(f"Unity 가 {timeout}초를 넘겼고 끊은 뒤에도 안 끝났다(pid {proc.pid})") from None
        raise VfxError(f"Unity 가 {timeout}초 안에 안 끝나 끊었다(pid {proc.pid})") from None


def log_issues(log_file: Path) -> list[dict]:
    """unity.log 에서 컴파일 오류 · 예외 줄을 보고 issues 꼴로 꺼낸다."""
    if not log_file.is_file():
        return []

    issues = []
    for line in log_file.read_text(encoding="utf-8", errors="replace").splitlines():
        if not any(marker in line for marker in _LOG_MARKERS):
            continue
        issues.append(issue("unity.log", "error", line.strip()[:300]))
        if len(issues) >= _MAX_LOG_ISSUES:
            break
    return issues


# 스택 줄 : 「  at Ns.Type.Method () …」 · 「UnityEngine.DebugLogHandler:Internal_Log (…)」 꼴.
_STACK_LINE = re.compile(r"^(at\s|[\w.`<>\[\],]+:[\w.`<>]+\s*\()")


def _is_cause_line(text: str) -> bool:
    if "[VFXTOOL]" in text:
        return True
    return "Exception" in text and _STACK_LINE.match(text) is None


def no_result_lines(log_file: Path) -> list[str]:
    """result.json 이 없을 때 까닭을 짚을 unity.log 줄([VFXTOOL] · Exception, 스택 줄은 뺌)을 모은다."""
    if not log_file.is_file():
        return []
    found = []
    for line in log_file.read_text(encoding="utf-8", errors="replace").splitlines():
        text = line.strip()
        if _is_cause_line(text):
            found.append(text[:300])
        if len(found) >= _MAX_LOG_ISSUES:
            break
    return found
