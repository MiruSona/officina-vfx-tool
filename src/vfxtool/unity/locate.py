"""어느 Unity.exe 로 돌릴지 정한다. 순서 : --unity > 환경 변수 VFXTOOL_UNITY > ProjectVersion.txt."""

import os
import re
import shlex
import shutil
from pathlib import Path

from vfxtool.errors import VfxError

ENV_NAME = "VFXTOOL_UNITY"
_VERSION_KEY = re.compile(r"^m_EditorVersion:\s*(\S+)\s*$", re.MULTILINE)


def read_editor_version(project: Path) -> str:
    """ProjectSettings/ProjectVersion.txt 의 m_EditorVersion 값을 읽는다."""
    version_file = project / "ProjectSettings" / "ProjectVersion.txt"
    if not version_file.is_file():
        raise VfxError(f"Unity 프로젝트가 아니다 — {version_file} 가 없다")

    match = _VERSION_KEY.search(version_file.read_text(encoding="utf-8", errors="replace"))
    if match is None:
        raise VfxError(f"{version_file} 에 m_EditorVersion 줄이 없다")
    return match.group(1)


def hub_editor_path(version: str) -> Path:
    """Unity Hub 기본 설치 자리. Program Files 는 환경 변수에서 읽는다."""
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    return Path(program_files) / "Unity" / "Hub" / "Editor" / version / "Editor" / "Unity.exe"


def split_command(value: str) -> list[str]:
    """덮기 값을 명령 앞부분으로 나눈다. 파일 경로 하나면 그대로, 아니면 「exe 인자…」 꼴로 본다."""
    if os.path.isfile(value):
        return [value]

    parts = [p.strip('"') for p in shlex.split(value, posix=False)]
    if not parts:
        raise VfxError("--unity 값이 비었다")

    head = parts[0]
    if os.path.isfile(head):
        return parts
    found = shutil.which(head)
    if found is None:
        raise VfxError(f"Unity 실행 파일을 못 찾았다 — {head}")
    return [found] + parts[1:]


def locate_unity(project: Path, override: str | None = None) -> list[str]:
    """Unity 를 띄울 명령 앞부분(보통 [Unity.exe 경로])을 돌려준다. 못 찾으면 VfxError(종료 2)."""
    if override:
        return split_command(override)

    env_value = os.environ.get(ENV_NAME)
    if env_value:
        return split_command(env_value)

    version = read_editor_version(project)
    exe = hub_editor_path(version)
    if not exe.is_file():
        raise VfxError(
            f"Unity {version} 를 못 찾았다 — {exe} 가 없다. --unity 나 {ENV_NAME} 로 경로를 준다"
        )
    return [str(exe)]
