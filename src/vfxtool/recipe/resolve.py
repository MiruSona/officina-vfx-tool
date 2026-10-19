"""레시피 → resolved.json. 템플릿 펼치기 · 프로필 기본값 · p<n> → hex · 텍셀 → Unity 단위 · from/to/ease → curve.

resolved.json 은 C# 이 그대로 Unity 객체로 옮기는 꼴이다(설계 1-2 · 2-4). C# 은 단위 · 팔레트를 모른다.
"""

import math
from pathlib import Path

from vfxtool import material_lib, template
from vfxtool.recipe import colors, schema, values
from vfxtool.report import issue

TEXTURE_BUILTINS = ("px1", "px2")
DEFAULT_CANVAS = {"texels": [64, 64], "scale": 4}
BURST_INTERVAL = 0.01
# Simulate 의 fixedTimeStep 걸음(초). C# 이 프로젝트 설정 대신 이 값을 쓴다 — 프로젝트마다 그림이 안 달라지게.
FIXED_DELTA_TIME = 0.02
DEG_TO_RAD = math.pi / 180


def has_templates(recipe):
    return any("template" in layer for layer in recipe["layers"])


def expand_templates(recipe, profile, template_dirs=()):
    """템플릿 층을 펼친다 — (펼친 레시피, issues). 템플릿 층이 없으면 그대로."""
    if not has_templates(recipe):
        return recipe, []
    return template.expand(recipe, profile, list(template_dirs))


def resolve(recipe, profile, recipe_dir):
    """검사를 통과한(펼친) 레시피를 resolved 꼴로 바꾼다. 칸 순서는 schema 표 순서로 고정한다."""
    lit = any(layer.get("material") == "lit" for layer in recipe["layers"])
    light = recipe.get("light")
    if light is None:
        light = "none"
        if lit:
            light = "global"
    canvas = dict(DEFAULT_CANVAS)
    canvas.update(recipe.get("canvas", {}))
    resolved = {
        "version": recipe["version"],
        "name": recipe["name"],
        "profile": recipe["profile"],
        "seed": recipe["seed"],
        "fixedTimeStep": recipe["fixedTimeStep"],
        "fixedDeltaTime": FIXED_DELTA_TIME,
        "duration": recipe["duration"],
        "fps": recipe.get("fps", profile["fps"]),
        "loop": recipe.get("loop", False),
        "canvas": canvas,
        "bloom": recipe.get("bloom", profile["bloom"]),
        "light": light,
        "ppu": profile["ppu"],
        "sortingLayer": profile["sorting_layer"],
        "snap": profile["snap"],
        "layers": [resolve_layer(layer, profile, recipe_dir) for layer in recipe["layers"]],
    }
    return resolved


def resolve_layer(layer, profile, recipe_dir):
    ppu = profile["ppu"]
    layer = fill_lib_sheet(layer, profile)
    offset = layer.get("offset", [0, 0])
    resolved = {
        "name": layer["name"],
        "material": layer.get("material", "unlit"),
        "blend": layer.get("blend", "alpha"),
        "texture": resolve_texture(layer.get("texture", "px1"), recipe_dir),
        "sortOrder": layer.get("sortOrder", 0),
        "space": layer.get("space", "local"),
        "offset": [values.texels_to_units(x, ppu) for x in offset],
    }
    for module, table in schema.MODULES.items():
        if module not in layer:
            continue
        body = layer[module]
        resolved[module] = {
            field: _resolve_field(module, field, kind, body[field], profile)
            for field, kind in table.items()
            if field in body
        }
    return resolved


def fill_lib_sheet(layer, profile):
    """textureSheet 를 채운 새 층. 채울 게 없으면 그대로.

    `lib:` 층은 메타의 tiles 를 채운다(소재묶음설계 4-2). 한 칸짜리 낱알(disc)은 textureSheet 를 안 만든다.
    lib 이든 파일 시트든 여러 장을 넘기는 시트는 fps 가 없으면 프로필 fps 를 넣는다 —
    C# 은 늘 FPS 모드라 fps 를 안 주면 Unity 기본값으로 돈다. 파일 시트의 장 수는 tiles 곱(row 를 고르면 tiles[0]).
    """
    texture = layer.get("texture")
    given = layer.get("textureSheet")
    if material_lib.is_lib(texture):
        meta = material_lib.load(material_lib.lib_name(texture))
        if given is None and meta["tiles"] == [1, 1]:
            return layer
        sheet = {"tiles": meta["tiles"]}
        sheet.update(given or {})
        frames = material_lib.frames_of(meta, sheet)
    elif isinstance(given, dict):
        sheet = dict(given)
        frames = _file_sheet_frames(sheet)
    else:
        return layer
    if "fps" not in sheet and frames > 1:
        sheet["fps"] = profile["fps"]
    filled = dict(layer)
    filled["textureSheet"] = sheet
    return filled


def _file_sheet_frames(sheet):
    """파일 시트가 한 생에 넘기는 장 수. tiles 가 없거나 꼴이 틀리면 1(검사는 check 몫)."""
    tiles = sheet.get("tiles")
    if not (isinstance(tiles, list) and len(tiles) == 2 and all(isinstance(n, int) for n in tiles)):
        return 1
    if "row" in sheet:
        return tiles[0]
    return tiles[0] * tiles[1]


def resolve_texture(texture, recipe_dir):
    """내장 이름표는 그대로, `lib:<이름>` 은 툴 안 소재 PNG, 파일이면 레시피 폴더 기준 절대 경로(슬래시)로."""
    if texture in TEXTURE_BUILTINS:
        return texture
    if material_lib.is_lib(texture):
        return material_lib.path(material_lib.lib_name(texture)).as_posix()
    return (Path(recipe_dir) / texture).resolve().as_posix()


def _resolve_field(module, field, kind, value, profile):
    ppu = profile["ppu"]
    length = schema.is_length(module, field)
    if kind[0] == "value":
        step_default = (module, field) in schema.STEP_DEFAULT_FIELDS
        normalized = values.normalize(value, step_default=step_default)
        if length:
            return values.scale(normalized, 1 / ppu)
        if (module, field) in schema.ANGLE_FIELDS:
            return values.scale(normalized, DEG_TO_RAD)
        return normalized
    if kind[0] == "color":
        return colors.resolve(value, profile["palette"])
    if kind[0] == "number" and length:
        return values.texels_to_units(value, ppu)
    if kind[0] == "vec" and length:
        return [values.texels_to_units(x, ppu) for x in value]
    if kind[0] == "bursts":
        return [_burst_object(burst) for burst in value]
    return value


def _burst_object(burst):
    """[t, n] 과 {t, n, cycles, interval} 을 한 꼴로 맞춘다."""
    if isinstance(burst, list):
        return {"t": burst[0], "n": burst[1], "cycles": 1, "interval": BURST_INTERVAL}
    return {
        "t": burst["t"],
        "n": burst["n"],
        "cycles": burst.get("cycles", 1),
        "interval": burst.get("interval", BURST_INTERVAL),
    }
