"""변형 사전 — 속성(불 · 얼음 …) 팔레트 · 소재 치환표 · 파라미터 값 읽기 · 덮기 · 검사(변형묶음설계 3-1 · 3-2).

내장은 variants/, 뒤에 준 --variants 폴더가 같은 이름 파일을 통째로 이긴다(칸 단위 합치기 없음).
"""

import re
from pathlib import Path

from vfxtool.errors import VfxError
from vfxtool.paths import is_junction, read_json
from vfxtool.profile import common
from vfxtool.recipe import colors

BUILTIN_DIR = Path(__file__).resolve().parent / "variants"
DICT_KEYS = ("version", "name", "title", "palette", "max_colors", "fx_extra", "materials", "ramp", "params")
PARAM_NAME_RE = re.compile(r"[a-z_][a-z0-9_]*")
NAME_RE = re.compile(r"[a-z0-9_]{1,16}")
BASE = "base"  # 예약어 — 바탕 프로필 팔레트 그대로
MAX_BYTES = 64 * 1024
LIB_PREFIX = "lib:"
RAMP_PREFIX = "ramp:"
MATERIAL_RE = re.compile(r"(lib|ramp):[a-z0-9_]{1,32}")


def read_small(path, what):
    """사람이 손으로 쓰는 작은 JSON(묶음 · 사전) — 64KB 넘으면 읽기 전에 VfxError."""
    file_path = Path(path)
    if file_path.is_file() and file_path.stat().st_size > MAX_BYTES:
        raise VfxError(f"{what} 파일이 {MAX_BYTES // 1024}KB 를 넘는다 : {file_path}")
    return read_json(file_path)


def load_all(variant_dirs=()):
    """속성 이름 → {"data", "path", "source"}. source 는 "builtin" 이거나 더한 폴더 경로."""
    found = {}
    folders = [(BUILTIN_DIR, "builtin")] + [(Path(d), str(d)) for d in variant_dirs]
    for folder, source in folders:
        if folder.is_symlink() or is_junction(folder):
            raise VfxError(f"변형 사전 폴더가 심볼릭 링크다 : {folder}")
        if not folder.is_dir():
            raise VfxError(f"변형 사전 폴더가 없다 : {folder}")
        for path in sorted(folder.glob("*.json")):
            if path.is_symlink() or is_junction(path) or not path.is_file():
                raise VfxError(f"변형 사전은 보통 파일만 받는다(심볼릭 링크 거절) : {path}")
            data = read_small(path, "변형 사전")
            check_dict(data, path.stem, path)
            found[data["name"]] = {"data": data, "path": str(path), "source": source}
    return found


def check_dict(data, stem, where):
    """사전 한 장의 꼴. 틀리면 VfxError — 모르는 칸도 오타로 보고 바로 알린다."""
    if not isinstance(data, dict):
        raise VfxError(f"변형 사전은 객체여야 한다 : {where}")
    extra = sorted(set(data) - set(DICT_KEYS))
    if extra:
        raise VfxError(f"변형 사전에 모르는 칸 {extra} (쓸 수 있는 칸 {list(DICT_KEYS)}) : {where}")
    if data.get("version") != 1:
        raise VfxError(f"변형 사전 version 은 1 이어야 한다 : {where}")
    name = data.get("name")
    if not isinstance(name, str) or NAME_RE.fullmatch(name) is None or name == BASE:
        raise VfxError(f"변형 사전 name 은 [a-z0-9_] 1~16자(base 는 예약어)여야 한다 : {where}")
    if name != stem:
        raise VfxError(f"변형 사전 name {name!r} 이 파일 이름 {stem!r} 과 다르다 : {where}")
    if "title" in data and not isinstance(data["title"], str):
        raise VfxError(f"변형 사전 title 은 글이어야 한다 : {where}")
    if "palette" not in data:
        raise VfxError(f"변형 사전에 palette 가 없다 : {where}")
    for field in ("max_colors", "fx_extra"):
        if field in data:
            _profile_value(field, data[field], where)
    palette = _profile_value("palette", data["palette"], where)
    if not palette:
        raise VfxError(f"변형 사전 palette 가 비었다 : {where}")
    _check_materials(data.get("materials", {}), where)
    _check_ramp(data, len(palette), where)
    _check_params(data.get("params", {}), where)


def _profile_value(field, value, where):
    try:
        return common.normalize(field, value, common.DEFAULTS[field])
    except ValueError as exc:
        raise VfxError(f"변형 사전 {field} : {exc} : {where}") from None


def _check_materials(materials, where):
    if not isinstance(materials, dict):
        raise VfxError(f"변형 사전 materials 는 {{바꿀 소재: 새 소재}} 객체여야 한다 : {where}")
    for left, right in materials.items():
        if not isinstance(left, str) or not left:
            raise VfxError(f"변형 사전 materials 왼쪽은 빈칸 아닌 글이어야 한다 : {where}")
        if not isinstance(right, str) or MATERIAL_RE.fullmatch(right) is None:
            raise VfxError(f"변형 사전 materials[{left!r}] 는 lib:<이름> 이나 ramp:<이름> 이어야 한다 (지금 {right!r}) : {where}")


def _check_ramp(data, palette_size, where):
    ramp = data.get("ramp")
    uses_ramp = any(right.startswith(RAMP_PREFIX) for right in data.get("materials", {}).values())
    if ramp is None:
        if uses_ramp:
            raise VfxError(f"변형 사전 materials 에 ramp: 가 있는데 ramp 칸이 없다 : {where}")
        return
    if not isinstance(ramp, list) or not ramp:
        raise VfxError(f"변형 사전 ramp 는 팔레트 번호(p0 …) 목록이어야 한다 : {where}")
    for ref in ramp:
        index = None
        if isinstance(ref, str):
            index = colors.palette_index(ref)
        if index is None or index >= palette_size:
            raise VfxError(f"변형 사전 ramp {ref!r} 는 이 사전 palette({palette_size}색) 안의 p<n> 이어야 한다 : {where}")


def _check_params(params, where):
    """params — {템플릿 파라미터 이름: JSON 스칼라}. 템플릿 쪽 꼴 · 범위는 판마다 펼치기가 본다(사전은 템플릿을 모른다)."""
    if not isinstance(params, dict):
        raise VfxError(f"변형 사전 params 는 {{파라미터 이름: 값}} 객체여야 한다 : {where}")
    for name, value in params.items():
        if PARAM_NAME_RE.fullmatch(name) is None:
            raise VfxError(f"변형 사전 params 이름 {name!r} 는 [a-z_][a-z0-9_]* 꼴이어야 한다 : {where}")
        if value is None or not isinstance(value, (str, int, float, bool)):
            raise VfxError(f"변형 사전 params[{name!r}] 는 글 · 숫자 · true/false 하나여야 한다 (지금 {value!r}) : {where}")
