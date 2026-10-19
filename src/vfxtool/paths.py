"""경로 감옥과 JSON 읽기 · 쓰기. 파일을 쓰고 읽는 모든 명령이 여기를 거친다."""

import json
import os
import tempfile
from pathlib import Path

from vfxtool.errors import VfxError


def ensure_inside(path, root):
    """root 안의 경로만 돌려준다. `..` 로 빠져나가거나 심볼릭 링크를 거치면 VfxError.

    path 가 상대 경로면 root 기준으로 본다. 아직 없는 파일도 된다(쓰기 자리 검사용).
    """
    root_path = Path(root).resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root_path / candidate
    _reject_symlinks(candidate, root_path)
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root_path):
        raise VfxError(f"경로가 허용된 폴더 밖이다 : {path} (허용 : {root_path})")
    return resolved


def _reject_symlinks(candidate, root_path):
    """root 아래 각 단계가 심볼릭 링크(또는 윈도 junction)면 거절한다."""
    current = candidate
    while True:
        if current.is_symlink() or is_junction(current):
            raise VfxError(f"심볼릭 링크는 받지 않는다 : {current}")
        parent = current.parent
        if parent == current or current.resolve() == root_path:
            return
        current = parent


def is_junction(path):
    try:
        return path.is_junction()
    except OSError:
        return False


def read_json(path):
    """UTF-8(BOM 허용) JSON 을 읽는다. 없거나 깨졌으면 VfxError."""
    file_path = Path(path)
    try:
        text = file_path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        raise VfxError(f"파일이 없다 : {file_path}") from None
    except OSError as exc:
        raise VfxError(f"파일을 못 읽었다 : {file_path} ({exc.strerror})") from None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise VfxError(f"JSON 이 깨졌다 : {file_path} {exc.lineno}줄 {exc.colno}칸 — {exc.msg}") from None


def dump_json(obj):
    """정해진 꼴의 JSON 글. golden 바이트 비교가 이 꼴에 기대므로 바꾸지 않는다."""
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def write_json(path, obj):
    """UTF-8 · ensure_ascii=False · indent 2 · 줄 끝 LF 로 쓴다. 상위 폴더는 만든다.

    같은 폴더 임시 파일에 다 쓴 뒤 os.replace 로 바꿔 끼운다 — 도중에 죽어도 반쪽 파일이 안 남는다.
    """
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=file_path.parent, prefix=f".{file_path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(dump_json(obj))
        os.replace(temp_name, file_path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise
    return file_path
