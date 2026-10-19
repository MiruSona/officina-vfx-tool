"""다형 값(숫자 칸) 다섯 꼴 — 검사 · from/to/ease 펼치기 · 텍셀 단위 바꾸기.

꼴 표는 설계 2-4. resolved.json 에는 앞 네 꼴(상수 · random · curve · random_curve)만 남는다.
"""

import math

def _ease_inout(t):
    if t < 0.5:
        return 2 * t * t
    return 1 - 2 * (1 - t) * (1 - t)


# ease 이름 → t(0~1) 를 0~1 로 바꾸는 함수(2차식). 펼친 곡선 키는 5개(설계 2-4).
EASES = {
    "linear": lambda t: t,
    "in": lambda t: t * t,
    "out": lambda t: 1 - (1 - t) * (1 - t),
    "inout": _ease_inout,
}
EASE_KEYS = (0.0, 0.25, 0.5, 0.75, 1.0)
CURVE_MIN_KEYS = 2
CURVE_MAX_KEYS = 8
DIGITS = 6

FORM_KEYS = {
    "random": {"random"},
    "curve": {"curve", "mult", "step"},
    "random_curve": {"random_curve"},
    "ease": {"from", "to", "ease"},
}


def is_number(value):
    """bool 은 int 의 자식이라 따로 막는다."""
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return math.isfinite(value)


def form_of(value):
    """값의 꼴 이름. 모르는 꼴이면 None."""
    if is_number(value):
        return "constant"
    if not isinstance(value, dict):
        return None
    for name in ("random", "curve", "random_curve"):
        if name in value:
            return name
    if "from" in value or "to" in value:
        return "ease"
    return None


def value_problems(value):
    """꼴이 틀린 곳을 사람 말로 돌려준다. 빈 목록이면 통과."""
    form = form_of(value)
    if form is None:
        return ["숫자 · {random} · {curve} · {random_curve} · {from,to,ease} 중 하나여야 한다"]
    if form == "constant":
        return []
    extra = sorted(set(value) - FORM_KEYS[form])
    if extra:
        return [f"{form} 꼴에 모르는 칸 {extra}"]
    if form == "random":
        return _pair_problems(value["random"], is_number, "random 은 숫자 두 개")
    if form == "curve":
        return _curve_object_problems(value)
    if form == "random_curve":
        return _random_curve_problems(value["random_curve"])
    return _ease_problems(value)


def _pair_problems(items, ok, message):
    if not isinstance(items, list) or len(items) != 2:
        return [message]
    if not all(ok(x) for x in items):
        return [message]
    return []


def _random_curve_problems(pair):
    if not isinstance(pair, list) or len(pair) != 2:
        return ["random_curve 는 곡선 키 목록 두 개여야 한다"]
    problems = []
    for keys in pair:
        problems.extend(curve_key_problems(keys))
    return problems


def curve_key_problems(keys):
    """곡선 키 `[[t, v], ...]` — 2~8개, t 는 0~1 오름차순."""
    if not isinstance(keys, list):
        return ["곡선 키는 [[t, v], ...] 목록이어야 한다"]
    if not CURVE_MIN_KEYS <= len(keys) <= CURVE_MAX_KEYS:
        return [f"곡선 키는 {CURVE_MIN_KEYS}~{CURVE_MAX_KEYS}개여야 한다 (지금 {len(keys)}개)"]
    for key in keys:
        if not isinstance(key, list) or len(key) != 2 or not all(is_number(x) for x in key):
            return [f"곡선 키 {key} 는 [t, v] 숫자 둘이어야 한다"]
    times = [key[0] for key in keys]
    if any(t < 0 or t > 1 for t in times):
        return ["곡선 키 t 는 0~1 안이어야 한다"]
    if any(b <= a for a, b in zip(times, times[1:])):
        return ["곡선 키 t 는 오름차순이어야 한다(같은 t 두 번 안 됨)"]
    return []


def _curve_object_problems(value):
    problems = curve_key_problems(value["curve"])
    if "mult" in value and not is_number(value["mult"]):
        problems.append("curve 의 mult 는 숫자여야 한다")
    if "step" in value and not isinstance(value["step"], bool):
        problems.append("curve 의 step 은 true/false 여야 한다")
    return problems


def _ease_problems(value):
    problems = []
    if not is_number(value.get("from")) or not is_number(value.get("to")):
        problems.append("from · to 는 둘 다 숫자여야 한다")
    ease = value.get("ease", "linear")
    if ease not in EASES:
        problems.append(f"ease 는 {sorted(EASES)} 중 하나여야 한다 (지금 {ease!r})")
    return problems


def expand_ease(value):
    """{from, to, ease} → 키 5개 곡선 키 목록."""
    ease = EASES[value.get("ease", "linear")]
    start = value["from"]
    span = value["to"] - start
    return [[t, round(start + span * ease(t), DIGITS)] for t in EASE_KEYS]


def normalize(value, step_default=False):
    """검사를 통과한 값을 resolved 꼴(네 꼴)로 바꾼다. curve 에는 mult · step 을 채운다."""
    form = form_of(value)
    if form == "constant":
        return value
    if form == "random":
        return {"random": list(value["random"])}
    if form == "random_curve":
        return {"random_curve": [_copy_keys(keys) for keys in value["random_curve"]]}
    if form == "ease":
        return {"curve": expand_ease(value), "mult": 1, "step": step_default}
    return {
        "curve": _copy_keys(value["curve"]),
        "mult": value.get("mult", 1),
        "step": value.get("step", step_default),
    }


def _copy_keys(keys):
    return [list(key) for key in keys]


def scale(value, factor):
    """normalize 뒤의 값에 factor 를 곱한다(텍셀 → Unity 단위). curve 는 키 값을 바꾸고 mult 는 둔다."""
    form = form_of(value)
    if form == "constant":
        return _mul(value, factor)
    if form == "random":
        return {"random": [_mul(x, factor) for x in value["random"]]}
    if form == "random_curve":
        return {"random_curve": [_scale_keys(keys, factor) for keys in value["random_curve"]]}
    scaled = dict(value)
    scaled["curve"] = _scale_keys(value["curve"], factor)
    return scaled


def _scale_keys(keys, factor):
    return [[t, _mul(v, factor)] for t, v in keys]


def _mul(x, factor):
    return round(x * factor, DIGITS)


def texels_to_units(x, ppu):
    """텍셀 길이 하나를 Unity 단위로."""
    return round(x / ppu, DIGITS)


def numbers_of(value):
    """값이 낼 수 있는 대표 숫자들(상수 · random 끝점 · 곡선 키 × mult). pixel_size 검사용."""
    form = form_of(value)
    if form == "constant":
        return [value]
    if form == "random":
        return list(value["random"])
    if form == "ease":
        return [v for _, v in expand_ease(value)]
    if form == "random_curve":
        return [v for keys in value["random_curve"] for _, v in keys]
    mult = value.get("mult", 1)
    return [v * mult for _, v in value["curve"]]
