"""템플릿 파라미터 — 값 검사 · 합치기(뼈대 < preset < params) · `$이름` / `@프로필칸` 바꿔 넣기(설계 4-1).

참조 꼴 : "$count" · "$speed*0.5"(숫자 곱하기 하나만) · "@pixel_size"(가장 작은 값) · "@ppu" 같은 프로필 칸.
"""

import re

from vfxtool.errors import VfxError
from vfxtool.recipe import colors, schema, values
from vfxtool.report import issue

PARAM_TYPES = ("int", "float", "color", "bool", "file", "tiles", "vec")
REF_RE = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)(?:\*(-?[0-9]+(?:\.[0-9]+)?))?")
PARAMS_RULE = "recipe.params"


def param_values(template, layer, palette=None):
    """(값 사전, issues). 레시피 층의 preset · params 를 검사하고 기본값 위에 겹친다.

    palette 를 주면 팔레트에 없는 색 기본값을 `fallback` 파라미터 값으로 바꾼다(_apply_fallbacks).
    """
    table = template["params"]
    found = []
    merged = {name: spec["default"] for name, spec in table.items() if "default" in spec}
    chosen = set()
    preset = layer.get("preset")
    if preset is not None:
        if preset not in template.get("presets", {}):
            found.append(_issue(layer, schema.unknown_detail("preset", str(preset), template.get("presets", {}))))
        else:
            merged.update(template["presets"][preset])
            chosen.update(template["presets"][preset])
    given = layer.get("params", {})
    if not isinstance(given, dict):
        return merged, [_issue(layer, "params 는 객체여야 한다")]
    chosen.update(given)
    for name, value in given.items():
        if name not in table:
            found.append(_issue(layer, schema.unknown_detail("params", name, table)))
            continue
        problem = type_problem(table[name], value)
        if problem is not None:
            found.append(_issue(layer, f"params.{name} : {problem}"))
            continue
        merged[name] = value
    # fallback 은 레시피 params 를 합친 뒤에 — 레시피가 고른 색을 따라가야 한다(템플릿 기본값 아님).
    if palette is not None:
        _apply_fallbacks(table, merged, chosen, palette)
    for name in table:
        if name not in merged:
            found.append(_issue(layer, f"params.{name} 는 기본값이 없어 꼭 적어야 한다"))
    return merged, found


def _apply_fallbacks(table, merged, chosen, palette):
    """기본값 그대로인 색 파라미터가 팔레트에 없는 번호(p1 인데 팔레트 1색)면 `fallback` 파라미터 값으로 바꾼다.

    레시피 · preset 이 직접 고른 값은 안 바꾼다 — 틀렸으면 check 가 recipe.palette error 로 알린다.
    """
    for name, spec in table.items():
        target = spec.get("fallback")
        if name in chosen or target not in merged or not isinstance(merged.get(name), str):
            continue
        index = colors.palette_index(merged[name])
        if index is not None and index >= len(palette):
            merged[name] = merged[target]


def _issue(layer, detail):
    return issue(PARAMS_RULE, "error", detail, layer=layer.get("name"), hint=["params", "preset"])


def type_problem(spec, value):
    """값이 파라미터 꼴 · 범위에 맞으면 None, 아니면 사람 말."""
    kind = spec["type"]
    if kind == "int" and (not values.is_number(value) or not isinstance(value, int)):
        return "정수여야 한다"
    if kind == "float" and not values.is_number(value):
        return "숫자여야 한다"
    if kind == "bool" and not isinstance(value, bool):
        return "true/false 여야 한다"
    if kind == "file" and (not isinstance(value, str) or value == ""):
        return "파일 경로 글이어야 한다"
    if kind == "color" and colors.color_problems(value):
        return colors.color_problems(value)[0][1]
    if kind == "tiles" and not _is_tiles(value):
        return "[x, y] 1 이상 정수 둘이어야 한다"
    if kind == "vec" and not (isinstance(value, list) and len(value) == 2 and all(values.is_number(x) for x in value)):
        return "[x, y] 숫자 둘이어야 한다"
    if kind in ("int", "float"):
        return _range_problem(spec, value)
    return None


def _is_tiles(value):
    """[x, y] 1 이상 정수 둘. bool 은 int 의 자식이라 따로 막는다."""
    if not isinstance(value, list) or len(value) != 2:
        return False
    return all(isinstance(x, int) and not isinstance(x, bool) and x >= 1 for x in value)


def _range_problem(spec, value):
    if "min" in spec and value < spec["min"]:
        return f"{spec['min']} 이상이어야 한다 (지금 {value})"
    if "max" in spec and value > spec["max"]:
        return f"{spec['max']} 이하여야 한다 (지금 {value})"
    return None


def substitute(node, params, profile, where):
    """뼈대 안의 `$이름` · `@칸` 을 값으로 바꾼 새 값. 템플릿 파일이 틀린 참조를 쓰면 VfxError."""
    if isinstance(node, list):
        return [substitute(item, params, profile, where) for item in node]
    if isinstance(node, dict):
        return {key: substitute(value, params, profile, where) for key, value in node.items()}
    if not isinstance(node, str):
        return node
    if node.startswith("$"):
        return _param_ref(node, params, where)
    if node.startswith("@"):
        return _profile_ref(node[1:], profile, where)
    return node


def _param_ref(text, params, where):
    match = REF_RE.fullmatch(text)
    if match is None or match.group(1) not in params:
        raise VfxError(f"템플릿 {where} : 모르는 파라미터 참조 {text!r}")
    value = params[match.group(1)]
    if match.group(2) is None:
        return value
    if not values.is_number(value):
        raise VfxError(f"템플릿 {where} : 숫자 아닌 파라미터에 곱하기 {text!r}")
    product = round(value * float(match.group(2)), values.DIGITS)
    # int 파라미터를 곱해 정수가 나오면 int 로 둔다(정수 칸에 2.0 이 들어가지 않게).
    if isinstance(value, int) and float(product).is_integer():
        return int(product)
    return product


def _profile_ref(name, profile, where):
    if name not in profile:
        raise VfxError(f"템플릿 {where} : 모르는 프로필 칸 '@{name}'")
    if name == "pixel_size":
        return min(profile["pixel_size"])
    return profile[name]
