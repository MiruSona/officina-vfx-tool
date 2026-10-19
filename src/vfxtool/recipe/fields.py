"""schema.py 의 칸 표대로 레시피를 훑어 recipe.schema · recipe.unsupported issue 를 만든다."""

import re

from vfxtool.recipe import colors, schema, values
from vfxtool.report import issue

SCHEMA = "recipe.schema"
UNSUPPORTED = "recipe.unsupported"


def check_top(recipe):
    """최상위 칸 · 층 목록 · 층 이름까지. 층 안의 모듈은 템플릿을 펼친 뒤 check_layers 가 본다."""
    if not isinstance(recipe, dict):
        return [issue(SCHEMA, "error", "레시피는 JSON 객체여야 한다")]
    found = []
    for name in recipe:
        if name not in schema.TOP_FIELDS:
            found.append(issue(SCHEMA, "error", schema.unknown_detail("레시피", name, schema.TOP_FIELDS)))
    for name in schema.TOP_REQUIRED:
        if name not in recipe:
            found.append(issue(SCHEMA, "error", f"필수 칸 {name!r} 가 없다"))
    for name, kind in schema.TOP_FIELDS.items():
        if name not in recipe:
            continue
        for rule, detail in field_problems(kind, recipe[name]):
            found.append(issue(rule, "error", f"{name} : {detail}"))
    found.extend(_top_values(recipe))
    return found


def _top_values(recipe):
    found = []
    if recipe.get("version", schema.RECIPE_VERSION) != schema.RECIPE_VERSION:
        found.append(issue(SCHEMA, "error", f"모르는 레시피 판 {recipe['version']!r} (아는 판 : {schema.RECIPE_VERSION})"))
    name = recipe.get("name")
    if isinstance(name, str) and re.fullmatch(schema.NAME_PATTERN, name) is None:
        found.append(issue(SCHEMA, "error", f"name {name!r} 는 [a-z0-9_]+ 여야 한다"))
    layers = recipe.get("layers")
    if isinstance(layers, list):
        found.extend(_layer_names(layers))
    return found


def _layer_names(layers):
    found = []
    seen = set()
    for index, layer in enumerate(layers):
        if not isinstance(layer, dict):
            continue
        name = layer.get("name")
        problem = schema.layer_name_problem(name)
        if problem is not None:
            found.append(issue(SCHEMA, "error", f"layers[{index}] : {problem}"))
            continue
        if name in seen:
            found.append(issue(SCHEMA, "error", f"층 이름 {name!r} 가 겹친다", layer=name))
        seen.add(name)
    return found


def check_layers(recipe):
    """펼친 레시피의 층 수 · 층 이름 · 모듈 칸 전부."""
    layers = recipe["layers"]
    found = []
    if not 1 <= len(layers) <= schema.MAX_LAYERS:
        found.append(issue(SCHEMA, "error", f"펼친 층이 {len(layers)}개 — 1~{schema.MAX_LAYERS}개여야 한다", hint=["layers"]))
    found.extend(_layer_names(layers))
    if found:
        return found
    for layer in layers:
        found.extend(_check_layer(layer))
    return found


def _check_layer(layer):
    name = layer["name"]
    found = []
    for key, value in layer.items():
        if key in schema.TEMPLATE_FIELDS:
            continue
        if key in schema.UNSUPPORTED_MODULES:
            found.append(issue(UNSUPPORTED, "error", f"{key} 모듈은 2차로 미뤘다 — 못 옮긴다", layer=name, hint=[key]))
            continue
        if key in schema.LAYER_FIELDS:
            found.extend(_field_issues(schema.LAYER_FIELDS[key], value, key, name))
            continue
        if key in schema.MODULES:
            found.extend(_check_module(key, value, name))
            continue
        found.append(issue(SCHEMA, "error", schema.unknown_detail("층", key, schema.known_layer_keys()), layer=name))
    return found


def _check_module(module, body, layer_name):
    if not isinstance(body, dict):
        return [issue(SCHEMA, "error", f"{module} 는 객체여야 한다", layer=layer_name)]
    table = schema.MODULES[module]
    found = []
    for key, value in body.items():
        where = f"{module}.{key}"
        if key not in table:
            found.append(issue(SCHEMA, "error", schema.unknown_detail(module, key, table), layer=layer_name))
            continue
        found.extend(_field_issues(table[key], value, where, layer_name))
    return found


def _field_issues(kind, value, where, layer_name):
    return [issue(rule, "error", f"{where} : {detail}", layer=layer_name, hint=[where]) for rule, detail in field_problems(kind, value)]


def field_problems(kind, value):
    """칸 꼴 하나를 검사해 (규칙, 사람 말) 목록을 돌려준다."""
    name = kind[0]
    if name == "value":
        return [(SCHEMA, text) for text in values.value_problems(value)]
    if name == "color":
        return colors.color_problems(value)
    if name in ("int", "number"):
        return _number_problems(name, kind[1], kind[2], value)
    if name == "bool":
        return _expect(isinstance(value, bool), "true/false 여야 한다")
    if name == "str":
        return _expect(isinstance(value, str) and value != "", "빈칸 아닌 글이어야 한다")
    if name == "enum":
        return _enum_problems(kind[1], kind[2], value)
    if name == "vec":
        ok = isinstance(value, list) and len(value) in kind[1] and all(values.is_number(x) for x in value)
        return _expect(ok, f"숫자 {'·'.join(str(n) for n in kind[1])}개 목록이어야 한다")
    if name == "tiles":
        ok = isinstance(value, list) and len(value) == 2 and all(_is_int(x) and x >= 1 for x in value)
        return _expect(ok, "[x, y] 1 이상 정수 둘이어야 한다")
    if name == "row":
        ok = value == "random" or (_is_int(value) and value >= 0)
        return _expect(ok, '0 이상 정수(줄 번호)나 "random" 이어야 한다')
    if name == "bursts":
        return _bursts_problems(value)
    if name == "canvas":
        return _canvas_problems(value)
    if name == "layers":
        # 층 수 상한은 템플릿을 펼친 뒤(check_layers)에 본다.
        ok = isinstance(value, list) and len(value) >= 1 and all(isinstance(x, dict) for x in value)
        return _expect(ok, "층 객체 1개 이상 목록이어야 한다")
    raise ValueError(f"schema 표에 모르는 칸 꼴 : {kind}")


def _expect(ok, message):
    if ok:
        return []
    return [(SCHEMA, message)]


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _number_problems(name, low, high, value):
    if name == "int" and not _is_int(value):
        return [(SCHEMA, "정수여야 한다")]
    if not values.is_number(value):
        return [(SCHEMA, "숫자여야 한다")]
    if low is not None and value < low:
        return [(SCHEMA, f"{low} 이상이어야 한다 (지금 {value})")]
    if high is not None and value > high:
        return [(SCHEMA, f"{high} 이하여야 한다 (지금 {value})")]
    return []


def _enum_problems(choices, later, value):
    if value in choices:
        return []
    if value in later:
        return [(UNSUPPORTED, f"{value!r} 는 2차로 미뤘다 (지금 받는 값 : {list(choices)})")]
    return [(SCHEMA, f"{value!r} 는 {list(choices)} 중 하나여야 한다")]


def _bursts_problems(value):
    if not isinstance(value, list):
        return [(SCHEMA, "bursts 는 [[t, n]] 이나 {t, n, cycles, interval} 목록이어야 한다")]
    for burst in value:
        if isinstance(burst, list):
            ok = len(burst) == 2 and values.is_number(burst[0]) and _is_int(burst[1]) and burst[0] >= 0 and burst[1] >= 0
        else:
            ok = _burst_object_ok(burst)
        if not ok:
            return [(SCHEMA, f"burst {burst} 꼴이 틀렸다 ([t, n] · n 은 0 이상 정수)")]
    return []


def _burst_object_ok(burst):
    if not isinstance(burst, dict) or set(burst) - {"t", "n", "cycles", "interval"}:
        return False
    if not values.is_number(burst.get("t")) or not _is_int(burst.get("n")):
        return False
    if burst["t"] < 0 or burst["n"] < 0:
        return False
    if not _is_int(burst.get("cycles", 1)) or burst.get("cycles", 1) < 1:
        return False
    return values.is_number(burst.get("interval", 0.01)) and burst.get("interval", 0.01) > 0


def _canvas_problems(value):
    if not isinstance(value, dict) or set(value) - {"texels", "scale"}:
        return [(SCHEMA, "canvas 는 {texels: [w, h], scale} 이어야 한다")]
    texels = value.get("texels", [64, 64])
    ok = isinstance(texels, list) and len(texels) == 2 and all(_is_int(x) and x > 0 for x in texels)
    scale = value.get("scale", 4)
    return _expect(ok and _is_int(scale) and scale > 0, "canvas texels 는 양의 정수 둘, scale 은 양의 정수여야 한다")
