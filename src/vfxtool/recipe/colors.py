"""색 값 네 꼴 — 검사 · `p<n>` 풀이 · 그러데이션 키 수(설계 2-5).

꼴 : "#RRGGBB(AA)" · "p<n>" · {"random": [c1, c2]} · {"gradient": {color, alpha}, "mode"} · {"random_gradient": [g1, g2]}.
"""

import re

from vfxtool.recipe.values import is_number

HEX_RE = re.compile(r"#(?:[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})")
PALETTE_RE = re.compile(r"p(\d+)")
MAX_GRADIENT_KEYS = 8
MODES = ("fixed", "blend")
SCHEMA = "recipe.schema"
KEYS_RULE = "recipe.gradient_keys"


def is_hex(text):
    return isinstance(text, str) and HEX_RE.fullmatch(text) is not None


def is_ref(text):
    """hex 또는 팔레트 번호 글."""
    return is_hex(text) or (isinstance(text, str) and PALETTE_RE.fullmatch(text) is not None)


def color_problems(value):
    """(규칙, 사람 말) 목록. 빈 목록이면 통과."""
    if isinstance(value, str):
        if is_ref(value):
            return []
        return [(SCHEMA, f"색 {value!r} 는 #RRGGBB(AA) 나 p<번호> 여야 한다")]
    if not isinstance(value, dict) or len(value) == 0:
        return [(SCHEMA, "색은 hex · p<n> · {random} · {gradient} · {random_gradient} 중 하나여야 한다")]
    if "random" in value:
        return _random_problems(value)
    if "random_gradient" in value:
        return _random_gradient_problems(value)
    if "gradient" in value:
        return gradient_problems(value)
    return [(SCHEMA, f"모르는 색 꼴 {sorted(value)}")]


def _random_problems(value):
    pair = value["random"]
    if len(value) != 1 or not isinstance(pair, list) or len(pair) != 2:
        return [(SCHEMA, "색 random 은 [색, 색] 하나만 받는다")]
    if not all(is_ref(c) for c in pair):
        return [(SCHEMA, "색 random 의 두 값은 hex 나 p<n> 이어야 한다")]
    return []


def _random_gradient_problems(value):
    pair = value["random_gradient"]
    if len(value) != 1 or not isinstance(pair, list) or len(pair) != 2:
        return [(SCHEMA, "random_gradient 는 [그러데이션, 그러데이션] 하나만 받는다")]
    problems = []
    for item in pair:
        if not isinstance(item, dict) or "gradient" not in item:
            problems.append((SCHEMA, "random_gradient 의 값은 {gradient, mode} 꼴이어야 한다"))
            continue
        problems.extend(gradient_problems(item))
    return problems


def gradient_problems(value):
    """{"gradient": {"color": [[t, c]], "alpha": [[t, a]]}, "mode": ...}"""
    extra = sorted(set(value) - {"gradient", "mode"})
    if extra:
        return [(SCHEMA, f"gradient 꼴에 모르는 칸 {extra}")]
    if value.get("mode", "fixed") not in MODES:
        return [(SCHEMA, f"gradient mode 는 {list(MODES)} 중 하나여야 한다")]
    body = value["gradient"]
    if not isinstance(body, dict) or "color" not in body:
        return [(SCHEMA, "gradient 는 color 키 목록을 가져야 한다")]
    extra = sorted(set(body) - {"color", "alpha"})
    if extra:
        return [(SCHEMA, f"gradient 안에 모르는 칸 {extra}")]
    problems = _keys_problems(body["color"], "color", _is_color_key)
    if "alpha" in body:
        problems.extend(_keys_problems(body["alpha"], "alpha", _is_alpha_key))
    return problems


def _is_color_key(key):
    # 색 키에는 알파를 안 붙인다(Unity GradientColorKey 는 RGB 만). 알파는 alpha 키로.
    if not isinstance(key, list) or len(key) != 2 or not is_number(key[0]):
        return False
    color = key[1]
    if is_hex(color):
        return len(color) == 7
    return is_ref(color)


def _is_alpha_key(key):
    if not isinstance(key, list) or len(key) != 2:
        return False
    if not (is_number(key[0]) and is_number(key[1])):
        return False
    return 0 <= key[1] <= 1


def _keys_problems(keys, name, ok):
    if not isinstance(keys, list) or len(keys) == 0:
        return [(SCHEMA, f"gradient {name} 키는 하나 이상의 목록이어야 한다")]
    if len(keys) > MAX_GRADIENT_KEYS:
        return [(KEYS_RULE, f"gradient {name} 키가 {len(keys)}개 — 최대 {MAX_GRADIENT_KEYS}개(Unity 한도)")]
    for key in keys:
        if not ok(key):
            return [(SCHEMA, f"gradient {name} 키 {key} 꼴이 틀렸다 (color 는 [t, \"#RRGGBB\"|\"p<n>\"], alpha 는 [t, 0~1])")]
    times = [key[0] for key in keys]
    if any(t < 0 or t > 1 for t in times) or any(b <= a for a, b in zip(times, times[1:])):
        return [(SCHEMA, f"gradient {name} 키 t 는 0~1 오름차순이어야 한다")]
    return []


def refs_of(value):
    """값 안의 색 글(hex · p<n>) 전부. 팔레트 · 색 수 검사용."""
    if isinstance(value, str):
        return [value]
    if "random" in value:
        return list(value["random"])
    if "random_gradient" in value:
        return [ref for item in value["random_gradient"] for ref in refs_of(item)]
    return [key[1] for key in value["gradient"]["color"]]


def alphas_of(value):
    """값 안의 알파(0~1) 전부. hex 의 AA 도 넣는다. alpha_steps 검사용."""
    if isinstance(value, str):
        return _hex_alpha(value)
    if "random" in value:
        return [a for ref in value["random"] for a in _hex_alpha(ref)]
    if "random_gradient" in value:
        return [a for item in value["random_gradient"] for a in alphas_of(item)]
    return [key[1] for key in value["gradient"].get("alpha", [])]


def _hex_alpha(ref):
    if is_hex(ref) and len(ref) == 9:
        return [int(ref[7:9], 16) / 255]
    return []


def uses_blend(value):
    """`mode: blend` 그러데이션이 하나라도 있나."""
    if isinstance(value, str) or "random" in value:
        return False
    if "random_gradient" in value:
        return any(uses_blend(item) for item in value["random_gradient"])
    return value.get("mode", "fixed") == "blend"


def palette_index(ref):
    """"p3" → 3. 팔레트 글이 아니면 None."""
    match = PALETTE_RE.fullmatch(ref)
    if match is None:
        return None
    return int(match.group(1))


def to_hex(ref, palette):
    """색 글 하나를 대문자 hex 로. 팔레트 번호가 범위 밖이면 IndexError."""
    index = palette_index(ref)
    if index is None:
        return ref.upper()
    if index >= len(palette):
        raise IndexError(f"팔레트에 {ref} 가 없다 (팔레트 {len(palette)}색)")
    return palette[index].upper()


def resolve(value, palette):
    """검사를 통과한 색 값의 p<n> 을 hex 로 풀고 mode · alpha 기본값을 채운다."""
    if isinstance(value, str):
        return to_hex(value, palette)
    if "random" in value:
        return {"random": [to_hex(ref, palette) for ref in value["random"]]}
    if "random_gradient" in value:
        return {"random_gradient": [resolve(item, palette) for item in value["random_gradient"]]}
    body = value["gradient"]
    alpha = body.get("alpha", [[0, 1], [1, 1]])
    return {
        "gradient": {
            "color": [[t, to_hex(ref, palette)] for t, ref in body["color"]],
            "alpha": [list(key) for key in alpha],
        },
        "mode": value.get("mode", "fixed"),
    }
