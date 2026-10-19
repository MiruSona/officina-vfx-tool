"""build · render 앞 검사 — 인자 꼴 · work 자리 · resolved 텍스처 경로 감옥. Unity 를 띄우기 전에 다 거른다."""

import argparse
from pathlib import Path

from vfxtool import material_lib
from vfxtool import report as reports
from vfxtool.errors import VfxError
from vfxtool.paths import ensure_inside
from vfxtool.recipe.resolve import TEXTURE_BUILTINS


def positive_float(text: str) -> float:
    """argparse type — 0 보다 큰 수만."""
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"숫자가 아니다 : {text!r}") from None
    if value <= 0:
        raise argparse.ArgumentTypeError(f"0 보다 커야 한다 : {text}")
    return value


def positive_int(text: str) -> int:
    """argparse type — 1 이상 정수만."""
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"정수가 아니다 : {text!r}") from None
    if value <= 0:
        raise argparse.ArgumentTypeError(f"1 이상이어야 한다 : {text}")
    return value


def work_path(work: str | None, resolved_path: Path, project: Path) -> Path:
    """work 자리(아직 안 만듦). 프로젝트 안이면 VfxError — PNG 마다 Unity 가져오기가 돈다(설계 5-5)."""
    path = resolved_path.parent
    if work:
        path = Path(work).resolve()
    if path.is_relative_to(project):
        raise VfxError(f"--work 는 Unity 프로젝트 밖이어야 한다 — {path}")
    return path


def texture_issues(resolved: dict, input_root: Path) -> list[dict]:
    """resolved 의 텍스처 절대 경로가 input_root 안인지 다시 본다. 손으로 고친 resolved 도 막는다."""
    found = []
    for layer in resolved.get("layers", []):
        texture = layer.get("texture")
        if not isinstance(texture, str) or texture in TEXTURE_BUILTINS:
            continue
        if material_lib.is_lib(texture):
            found.append(reports.issue("recipe.lib", "error", f"texture {texture!r} : resolved.json 에 lib: 가 남았다 — check 를 거친 resolved 를 쓴다",
                                       layer=layer.get("name"), hint=["texture"]))
            continue
        if material_lib.is_inside(texture):
            # 툴 안 소재 PNG(check 가 lib: 를 푼 자리)는 --input-root 밖이어도 된다.
            continue
        try:
            ensure_inside(Path(texture), input_root)
        except VfxError as exc:
            detail = f"texture : {exc.message} — 레시피 폴더 밖 파일이면 --input-root 로 그 위 폴더를 준다"
            found.append(reports.issue("recipe.paths", "error", detail, layer=layer.get("name"),
                                       hint=["texture", "--input-root"]))
    return found
