"""템플릿 층 — 찾기 · 펼치기 · fixed 지키기 · 템플릿 check(설계 4절).

값 순서 : 뼈대 < preset < params < override(템플릿 층 이름별 모듈 덮기). fixed 는 늘 이긴다.
펼친 층 이름은 `<레시피 층 이름>.<템플릿 층 이름>`. 내장은 templates/, 뒤에 준 --templates 폴더가 이긴다.
"""

import copy
import math
from pathlib import Path

from vfxtool import template_rules
from vfxtool.errors import VfxError
from vfxtool.paths import read_json
from vfxtool.recipe.patch import merge_patch
from vfxtool.report import issue
from vfxtool.template_values import param_values, substitute

# 내장 템플릿 주의 : Cone 은 로컬 +Z 로 쏘아 2D 위쪽은 shape.rotation [-90, 0, 0].
# land_dust 의 Edge 는 X 축 가로선, +Y 로 나간다(실측).
BUILTIN_DIR = Path(__file__).resolve().parent / "templates"
TEMPLATE_KEYS = {"version", "name", "title", "layers", "params", "fixed", "presets", "tiers", "check"}
# file 파라미터의 짝 키(변형묶음설계 5절) — size 는 필수 int 파라미터, tiles · color 는 있을 때만.
PAIR_KINDS = {"size": "int", "tiles": "tiles", "color": "color"}
TIER_KEYS = {"mul", "scale"}
MAX_TIER_MUL = 100  # 세기 배수 상한 — 곱이 inf 로 넘치지 않게
# 레시피의 템플릿 층에 적을 수 있는 칸. offset 은 펼친 층 모두에 들어간다.
CALL_KEYS = {"name", "template", "params", "preset", "override", "offset"}
CHECK_KEYS = {"rule", "kind", "layer", "args"}


def load_all(template_dirs=()):
    """이름 → {"data", "path", "source"}. source 는 "builtin" 이거나 더한 폴더 경로."""
    found = {}
    folders = [(BUILTIN_DIR, "builtin")] + [(Path(d), str(d)) for d in template_dirs]
    for folder, source in folders:
        if not folder.is_dir():
            raise VfxError(f"템플릿 폴더가 없다 : {folder}")
        for path in sorted(folder.glob("*.json")):
            data = _read_template(path)
            found[data["name"]] = {"data": data, "path": str(path), "source": source}
    return found


def _read_template(path):
    data = read_json(path)
    if not isinstance(data, dict) or set(data) - TEMPLATE_KEYS:
        raise VfxError(f"템플릿 파일 꼴이 틀렸다(모르는 칸) : {path}")
    for key in ("name", "layers", "params"):
        if key not in data:
            raise VfxError(f"템플릿 파일에 {key} 가 없다 : {path}")
    if data["name"] != path.stem:
        raise VfxError(f"템플릿 name 과 파일 이름이 다르다 : {path}")
    _check_rules_shape(data.get("check", []), path)
    _check_fallbacks(data["params"], path)
    _check_pairs(data["params"], path)
    _check_tiers(data.get("tiers", {}), data["params"], path)
    return data


def _check_fallbacks(params, path):
    """params 의 fallback — 다른 color 파라미터 이름이어야 한다. 틀리면 VfxError."""
    if not isinstance(params, dict):
        raise VfxError(f"템플릿 params 는 객체여야 한다 : {path}")
    for name, spec in params.items():
        if not isinstance(spec, dict) or "fallback" not in spec:
            continue
        target = spec["fallback"]
        if not isinstance(target, str) or target == name:
            raise VfxError(f"템플릿 params.{name} 의 fallback 은 자기 아닌 파라미터 이름이어야 한다 : {path}")
        if target not in params or not isinstance(params[target], dict) or params[target].get("type") != "color":
            raise VfxError(f"템플릿 params.{name} 의 fallback {target!r} 는 있는 color 파라미터여야 한다 : {path}")


def _check_pairs(params, path):
    """file 파라미터의 짝 키 — size(필수) · tiles · color 가 그 꼴의 있는 파라미터를 가리키나. 틀리면 VfxError.

    짝 없는 file 파라미터(짝 키를 하나도 안 적은 것)는 소재 치환 대상이 아니라 그대로 둔다.
    """
    for name, spec in params.items():
        if not isinstance(spec, dict) or spec.get("type") != "file":
            continue
        keys = [key for key in PAIR_KINDS if key in spec]
        if keys and "size" not in keys:
            raise VfxError(f"템플릿 params.{name} 의 짝 키에 size 가 없다 : {path}")
        for key in keys:
            target = spec[key]
            kind = PAIR_KINDS[key]
            if not isinstance(target, str) or not isinstance(params.get(target), dict) or params[target].get("type") != kind:
                raise VfxError(f"템플릿 params.{name} 의 {key} 짝 {target!r} 는 있는 {kind} 파라미터여야 한다 : {path}")


def _check_tiers(tiers, params, path):
    """tiers 꼴 — {이름: {mul: {int · float 파라미터: 0 초과 숫자}, scale: 1 이상 정수}}. 틀리면 VfxError."""
    if not isinstance(tiers, dict):
        raise VfxError(f"템플릿 tiers 는 객체여야 한다 : {path}")
    for tier, body in tiers.items():
        problem = tier_problem(body, params)
        if problem is not None:
            raise VfxError(f"템플릿 tiers.{tier} : {problem} : {path}")


def tier_problem(body, params):
    """세기 한 칸이 맞으면 None, 아니면 사람 말. 묶음의 즉석 세기도 같이 쓴다(name 칸은 부르는 쪽이 뗀다)."""
    if not isinstance(body, dict) or set(body) - TIER_KEYS:
        return f"칸은 {sorted(TIER_KEYS)} 만 적는다"
    mul = body.get("mul", {})
    if not isinstance(mul, dict):
        return "mul 은 {파라미터: 배수} 객체여야 한다"
    sizes = {spec.get("size") for spec in params.values() if isinstance(spec, dict) and spec.get("type") == "file"}
    for name, factor in mul.items():
        spec = params.get(name)
        if not isinstance(spec, dict) or spec.get("type") not in ("int", "float"):
            return f"mul.{name} 은 있는 int · float 파라미터여야 한다"
        if name in sizes:
            return f"mul.{name} 은 텍스처 크기 짝이라 배수를 못 건다 — 크기는 scale 로 키운다"
        if isinstance(factor, bool) or not isinstance(factor, (int, float)) or not math.isfinite(factor) or not 0 < factor <= MAX_TIER_MUL:
            return f"mul.{name} 배수는 0 보다 큰 {MAX_TIER_MUL} 이하 숫자여야 한다 (지금 {factor!r})"
    scale = body.get("scale", 1)
    if isinstance(scale, bool) or not isinstance(scale, int) or scale < 1:
        return f"scale 은 1 이상 정수여야 한다 (지금 {scale!r})"
    return None


def _check_rules_shape(rules, path):
    """check 항목 꼴 — 목록 · rule 은 글 · kind · layer 는 글 · args 는 객체. 틀리면 VfxError."""
    if not isinstance(rules, list):
        raise VfxError(f"템플릿 check 는 목록이어야 한다 : {path}")
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict) or set(rule) - CHECK_KEYS:
            raise VfxError(f"템플릿 check[{index}] 꼴이 틀렸다(객체 · 칸 {sorted(CHECK_KEYS)}) : {path}")
        if not isinstance(rule.get("rule"), str) or not rule["rule"]:
            raise VfxError(f"템플릿 check[{index}] 의 rule 은 빈칸 아닌 글이어야 한다 : {path}")
        for key in ("kind", "layer"):
            if key in rule and rule[key] is not None and not isinstance(rule[key], str):
                raise VfxError(f"템플릿 check[{index}] 의 {key} 는 글이어야 한다 : {path}")
        if not isinstance(rule.get("args", {}), dict):
            raise VfxError(f"템플릿 check[{index}] 의 args 는 객체여야 한다 : {path}")


def expand(recipe, profile, template_dirs=()):
    """(펼친 레시피, issues). 템플릿 층이 아닌 층은 그대로 둔다."""
    templates = load_all(template_dirs)
    found = []
    layers = []
    calls = []
    for layer in recipe["layers"]:
        if "template" not in layer:
            layers.append(layer)
            continue
        expanded, layer_issues = expand_layer(layer, templates, profile)
        layers.extend(expanded)
        found.extend(layer_issues)
        calls.append((layer, expanded))
    result = dict(recipe)
    result["layers"] = layers
    if found:
        return result, found
    for call, expanded in calls:
        found.extend(recipe_checks(result, call, expanded, templates[call["template"]]["data"]))
    return result, found


def expand_layer(layer, templates, profile):
    name = layer["name"]
    template_name = layer["template"]
    if template_name not in templates:
        return [], [issue("recipe.template_missing", "error", f"모르는 템플릿 {template_name!r} (있는 것 : {sorted(templates)})", layer=name, hint=["template"])]
    data = templates[template_name]["data"]
    extra = sorted(set(layer) - CALL_KEYS)
    if extra:
        return [], [issue("recipe.schema", "error", f"템플릿 층에는 {sorted(CALL_KEYS)} 만 적는다 (모르는 칸 {extra})", layer=name)]
    params, found = param_values(data, layer, profile["palette"])
    override = layer.get("override", {})
    found.extend(_override_issues(override, data, name))
    if found:
        return [], found
    expanded = []
    for skeleton in data["layers"]:
        body = _build_layer(skeleton, params, profile, override, data, template_name)
        if body is None:
            continue
        body["name"] = f"{name}.{skeleton['name']}"
        if "offset" in layer:
            body["offset"] = layer["offset"]
        expanded.append(body)
    return expanded, []


def _build_layer(skeleton, params, profile, override, data, template_name):
    """뼈대 한 층 → 레시피 층. `when` 파라미터가 false 면 None(층을 뺀다)."""
    body = substitute(copy.deepcopy(skeleton), params, profile, template_name)
    when = body.pop("when", True)
    if when is not True:
        return None
    short = skeleton["name"]
    body = merge_patch(body, override.get(short, {}))
    for path, value in data.get("fixed", {}).items():
        parts = path.split(".")
        if parts[0] == short:
            _set_path(body, parts[1:], value)
    return body


def _set_path(node, parts, value):
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = copy.deepcopy(value)


def _override_issues(override, data, layer_name):
    if not isinstance(override, dict):
        return [issue("recipe.schema", "error", "override 는 {템플릿 층 이름: 덮을 값} 객체여야 한다", layer=layer_name)]
    short_names = [skeleton["name"] for skeleton in data["layers"]]
    found = []
    for short, body in override.items():
        if short not in short_names:
            found.append(issue("recipe.schema", "error", f"override 의 템플릿 층 {short!r} 가 없다 (있는 것 : {short_names})", layer=layer_name))
            continue
        if not isinstance(body, dict):
            found.append(issue("recipe.schema", "error", f"override.{short} 는 덮을 값 객체여야 한다", layer=layer_name, hint=["override"]))
            continue
        for leaf in _leaf_paths(body, short):
            for fixed in data.get("fixed", {}):
                if leaf == fixed or leaf.startswith(fixed + ".") or fixed.startswith(leaf + "."):
                    found.append(issue("recipe.fixed", "error", f"override 가 템플릿이 못 박은 {fixed} 를 건드린다", layer=layer_name, hint=["override"]))
    return found


def _leaf_paths(node, prefix):
    if not isinstance(node, dict) or not node:
        return [prefix]
    paths = []
    for key, value in node.items():
        paths.extend(_leaf_paths(value, f"{prefix}.{key}"))
    return paths


def recipe_checks(recipe, call, expanded, data):
    """템플릿 check[] 중 레시피 단계 규칙(kind 가 frame 이 아닌 것). frame 규칙은 measure 몫이다."""
    # 레시피 층 이름에 점이 들어도 되게 앞머리 `<레시피 층 이름>.` 를 길이로 떼어 낸다.
    prefix_length = len(call["name"]) + 1
    by_short = {}
    for body in expanded:
        by_short[body["name"][prefix_length:]] = body
    found = []
    for rule in data.get("check", []):
        if rule.get("kind") == "frame":
            continue
        found.extend(template_rules.run(rule, recipe, call["name"], by_short))
    return found


def frame_checks(recipe, template_dirs=()):
    """measure 가 쓸 프레임 단계 템플릿 규칙 목록 [{rule, layer, args, template}] (층 이름은 펼친 이름)."""
    templates = load_all(template_dirs)
    found = []
    for layer in recipe["layers"]:
        if "template" not in layer or layer["template"] not in templates:
            continue
        for rule in templates[layer["template"]]["data"].get("check", []):
            if rule.get("kind") != "frame":
                continue
            item = {"rule": rule["rule"], "layer": None, "args": rule.get("args", {}), "template": layer["template"]}
            if rule.get("layer"):
                item["layer"] = f"{layer['name']}.{rule['layer']}"
            found.append(item)
    return found
