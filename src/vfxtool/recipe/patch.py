"""patch = 부분 덮기(설계 7-3). JSON Merge Patch(RFC 7396) 꼴에 `layers` 만 층 이름 열쇠로 가리킨다.

객체는 겹쳐 합치고, 배열 · 값은 통째로 바꾸고, null 은 지운다. 없는 층 이름은 새 층으로 덧붙인다(warn).
`layers` 배열 · profile · name · version 바꾸기는 막는다.
"""

import copy

from vfxtool.errors import VfxError
from vfxtool.report import has_errors, issue

FIXED_FIELDS = ("profile", "name", "version")


def merge_patch(target, patch):
    """RFC 7396 그대로. 원본은 안 고치고 새 값을 돌려준다."""
    if not isinstance(patch, dict):
        return copy.deepcopy(patch)
    result = {}
    if isinstance(target, dict):
        result = copy.deepcopy(target)
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
            continue
        result[key] = merge_patch(result.get(key), value)
    return result


def apply(recipe, patch):
    """(새 레시피, issues). error 가 있으면 새 레시피는 None. patch 가 객체가 아니면 VfxError."""
    if not isinstance(patch, dict):
        raise VfxError("patch 는 JSON 객체여야 한다")
    issues = [_fixed_issue(key) for key in FIXED_FIELDS if key in patch and patch[key] != recipe.get(key)]
    layer_patch = patch.get("layers")
    if isinstance(layer_patch, list):
        issues.append(issue("patch.layers_array", "error", "patch 의 layers 는 배열이 아니라 {층 이름: 덮을 값} 객체다",
                            hint=["layers"]))
    elif layer_patch is not None and not isinstance(layer_patch, dict):
        raise VfxError("patch 의 layers 는 {층 이름: 덮을 값} 객체여야 한다")
    if has_errors(issues):
        return None, issues
    rest = {key: value for key, value in patch.items() if key != "layers"}
    result = merge_patch(recipe, rest)
    if layer_patch is None:
        return result, issues
    layers, layer_issues = _patch_layers(result.get("layers", []), layer_patch)
    issues.extend(layer_issues)
    if has_errors(issues):
        return None, issues
    result["layers"] = layers
    return result, issues


def _fixed_issue(key):
    return issue("patch.fixed_field", "error", f"patch 로 {key} 칸은 못 바꾼다", hint=[key])


def _patch_layers(layers, layer_patch):
    patched = []
    seen = set()
    for layer in layers:
        name = layer.get("name")
        if name not in layer_patch:
            patched.append(layer)
            continue
        seen.add(name)
        change = layer_patch[name]
        if change is None:
            continue
        if not isinstance(change, dict):
            raise VfxError(f"patch layers.{name} 는 객체나 null 이어야 한다")
        patched.append(merge_patch(layer, change))
    issues = []
    for name, change in layer_patch.items():
        if name in seen or change is None:
            continue
        if not isinstance(change, dict):
            raise VfxError(f"patch layers.{name} 는 객체여야 한다(새 층은 전체를 적는다)")
        issues.extend(_new_layer_issues(name, change))
        new_layer = copy.deepcopy(change)
        new_layer["name"] = name
        patched.append(new_layer)
    return patched, issues


def _new_layer_issues(name, change):
    """새 층은 warn 으로 알린다. 점 든 이름(펼친 템플릿 층 이름) · main 없는 층은 error."""
    if "." in name:
        return [issue("patch.new_layer", "error", f"새 층 {name!r} — 점 든 이름은 템플릿 층이다. 템플릿 층은 params · override 로 고친다",
                      layer=name, hint=["params", "override"])]
    if "main" not in change and "template" not in change:
        return [issue("patch.new_layer", "error", f"새 층 {name!r} 에 main 이 없다 — 새 층은 전체를 적는다", layer=name, hint=["main"])]
    return [issue("patch.new_layer", "warn", f"없던 층 {name!r} 를 새로 더했다 — 오타가 아닌지 본다", layer=name)]
