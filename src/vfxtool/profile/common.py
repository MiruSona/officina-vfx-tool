"""프로필 칸의 기본값·값 다듬기·issue 꼴. 칸 표는 설계 3-1."""
import copy
import re

PROFILE_VERSION = 1
MAX_PALETTE = 32

# 설계 3-1 기본값 표. 순서가 곧 profile.json 의 칸 순서다.
DEFAULTS = {
    "palette": [],
    "fx_extra": ["#FFFFFF"],
    "ppu": 32,
    "pixel_size": [1, 2],
    "max_colors": 4,
    "outline": "none",
    "fps": 12,
    "fps_range": [12, 16],
    "alpha_steps": "binary",
    "allow_rotation": True,
    "seq_tolerance": {"ratio": 0.5, "run": 3},
    "max_particles": 256,
    "sorting_layer": "Default",
    "snap": True,
    "bloom": False,
}

_HEX = re.compile(r"#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?")


def defaults() -> dict:
    return copy.deepcopy(DEFAULTS)


def make_issue(rule: str, severity: str, detail: str, hint=None) -> dict:
    if hint is None:
        hint = []
    return {"rule": rule, "layer": None, "frame": None, "severity": severity, "detail": detail, "hint": hint}


def _is_int(value) -> bool:
    # bool 은 int 의 자식이라 따로 막는다.
    return isinstance(value, int) and not isinstance(value, bool)


def _positive_int(value, low: int = 1) -> int:
    if not _is_int(value) or value < low:
        raise ValueError(f"{low} 이상 정수여야 한다 : {value!r}")
    return value


def _hex_list(value, limit=None) -> list:
    if not isinstance(value, list):
        raise ValueError(f"hex 배열이어야 한다 : {value!r}")
    result = []
    for item in value:
        if not isinstance(item, str) or _HEX.fullmatch(item) is None:
            raise ValueError(f"#RRGGBB(AA) 꼴이 아니다 : {item!r}")
        if item.upper() not in result:
            result.append(item.upper())
    if limit is not None and len(result) > limit:
        raise ValueError(f"색이 {len(result)} 개 — 최대 {limit} 개")
    return result


def _pixel_size(value) -> list:
    if _is_int(value):
        value = [value]
    if not isinstance(value, list) or not value:
        raise ValueError(f"정수 또는 정수 배열이어야 한다 : {value!r}")
    return sorted({_positive_int(v) for v in value})


def _fps_range(value) -> list:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"[min, max] 꼴이어야 한다 : {value!r}")
    low = _positive_int(value[0])
    high = _positive_int(value[1])
    if low > high:
        raise ValueError(f"min 이 max 보다 크다 : {value!r}")
    return [low, high]


def _seq_tolerance(value, current: dict) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{{ratio, run}} 객체여야 한다 : {value!r}")
    unknown = set(value) - {"ratio", "run"}
    if unknown:
        raise ValueError(f"모르는 칸 : {sorted(unknown)}")
    result = dict(current)
    if "ratio" in value:
        ratio = value["ratio"]
        if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or not 0 <= ratio <= 1:
            raise ValueError(f"ratio 는 0~1 숫자여야 한다 : {ratio!r}")
        result["ratio"] = ratio
    if "run" in value:
        result["run"] = _positive_int(value["run"])
    return result


def _choice(value, allowed: tuple):
    if value not in allowed:
        raise ValueError(f"{list(allowed)} 중 하나여야 한다 : {value!r}")
    return value


def _flag(value) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"true/false 여야 한다 : {value!r}")
    return value


def _name(value) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"빈 글이 아닌 이름이어야 한다 : {value!r}")
    return value


def normalize(field: str, value, current):
    """칸 값을 검사해 다듬은 값을 돌려준다. 틀리면 ValueError. current 는 그 칸의 지금 값."""
    if field == "palette":
        return _hex_list(value, MAX_PALETTE)
    if field == "fx_extra":
        return _hex_list(value)
    if field in ("ppu", "max_colors", "fps", "max_particles"):
        return _positive_int(value)
    if field == "pixel_size":
        return _pixel_size(value)
    if field == "fps_range":
        return _fps_range(value)
    if field == "seq_tolerance":
        return _seq_tolerance(value, current)
    if field == "outline":
        return _choice(value, ("none",))
    if field == "alpha_steps":
        return _choice(value, ("binary", "free"))
    if field in ("allow_rotation", "snap", "bloom"):
        return _flag(value)
    if field == "sorting_layer":
        return _name(value)
    raise ValueError(f"모르는 칸 : {field}")
