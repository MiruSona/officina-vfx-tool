"""레시피 단계 규칙(설계 8-1 표) — 칸 꼴이 맞은 뒤, 프로필 값과 견주는 규칙들.

칸 값은 아직 텍셀 단위다(resolve 전). 안 적은 칸은 Unity 기본값(startSize 1 단위 · maxParticles 1000)으로 본다.
"""

from PIL import Image

from vfxtool import material_lib
from vfxtool.errors import VfxError
from vfxtool.paths import ensure_inside
from vfxtool.recipe import colors, values
from vfxtool.recipe.resolve import TEXTURE_BUILTINS
from vfxtool.report import has_errors, issue

UNITY_DEFAULT_MAX_PARTICLES = 1000
UNITY_DEFAULT_LIFETIME = 5
SIZE_TOLERANCE = 1e-6
# 수명은 장 수 ÷ 12 를 소수 셋째 자리로 적는다(0.416 · 0.833). 반올림 차이로 warn 이 나지 않게 둔다.
LIFE_TOLERANCE = 1e-3


def recipe_rules(recipe, profile):
    """레시피 전체에 걸린 규칙 — lit_light · bloom_later."""
    found = []
    lit_layers = [layer["name"] for layer in recipe["layers"] if layer.get("material") == "lit"]
    if lit_layers and recipe.get("light") == "none":
        found.append(issue("recipe.lit_light", "error", f"light 가 none 인데 lit 층이 있다 : {lit_layers}", hint=["light", "material"]))
    if recipe.get("bloom", profile["bloom"]):
        found.append(issue("recipe.bloom_later", "warn", "블룸은 1차에서 받기만 하고 미리보기에 안 켠다", hint=["bloom"]))
    return found


def layer_rules(layer, profile, recipe_dir, root):
    found = []
    found.extend(_pixel_size(layer, profile))
    found.extend(_rotation(layer, profile))
    found.extend(_color_rules(layer, profile))
    found.extend(_blend(layer))
    found.extend(_max_particles(layer, profile))
    found.extend(_texture(layer, profile, recipe_dir, root))
    return found


def _pixel_size(layer, profile):
    name = layer["name"]
    main = layer.get("main", {})
    sizes = [profile["ppu"]]
    if "startSize" in main:
        sizes = values.numbers_of(main["startSize"])
    size_value = _size_over_lifetime(layer)
    mults = [1]
    if size_value is not None:
        mults = values.numbers_of(size_value)
    allowed = profile["pixel_size"]
    found = []
    if layer.get("texture", "px1") not in TEXTURE_BUILTINS:
        # 시트 텍스처 층은 입자 하나가 타일 한 장(여러 텍셀)이라 pixel_size 대신 정수 텍셀만 본다.
        bad = sorted({round(s * m, 6) for s in sizes for m in mults if not _in_set(s * m, [round(s * m)])})
        if bad:
            found.append(issue("recipe.pixel_size", "error", f"시트 층 입자 크기(텍셀) {bad} 가 정수가 아니다", layer=name, hint=["main.startSize"]))
        return found
    bad = sorted({round(s * m, 6) for s in sizes for m in mults if not _in_set(s * m, allowed)})
    if bad:
        found.append(issue(
            "recipe.pixel_size", "error",
            f"입자 크기(텍셀) {bad} 가 프로필 pixel_size {allowed} 밖이다 (startSize × 크기 곡선 키)",
            layer=name, hint=["main.startSize", "sizeOverLifetime.size"],
        ))
    if isinstance(size_value, dict) and size_value.get("step") is False:
        found.append(issue("recipe.pixel_size", "warn", "크기 곡선 step 이 꺼졌다 — 중간 크기는 도트가 깨진다", layer=name, hint=["sizeOverLifetime.size"]))
    return found


def _in_set(size, allowed):
    return any(abs(size - n) <= SIZE_TOLERANCE for n in allowed)


def _rotation(layer, profile):
    if profile["allow_rotation"]:
        return []
    used = []
    if "startRotation" in layer.get("main", {}):
        used.append("main.startRotation")
    if "rotationOverLifetime" in layer:
        used.append("rotationOverLifetime")
    if not used:
        return []
    return [issue("recipe.rotation", "error", f"프로필이 회전을 막았다(allow_rotation false) : {used}", layer=layer["name"], hint=used)]


def _layer_colors(layer):
    """층의 색 값들 (칸 이름, 값)."""
    found = []
    if "startColor" in layer.get("main", {}):
        found.append(("main.startColor", layer["main"]["startColor"]))
    if "color" in layer.get("colorOverLifetime", {}):
        found.append(("colorOverLifetime.color", layer["colorOverLifetime"]["color"]))
    return found


def _color_rules(layer, profile):
    name = layer["name"]
    found = []
    palette = profile["palette"]
    allowed = {c[:7] for c in palette + profile["fx_extra"]}
    used_rgb = set()
    for where, value in _layer_colors(layer):
        found.extend(_alpha_steps(value, where, name, profile))
        for ref in colors.refs_of(value):
            try:
                hex_value = colors.to_hex(ref, palette)
            except IndexError as exc:
                found.append(issue("recipe.palette", "error", f"{where} : {exc}", layer=name, hint=[where]))
                continue
            used_rgb.add(hex_value[:7])
            if hex_value[:7] not in allowed:
                found.append(issue("recipe.palette", "warn", f"{where} : 팔레트 · fx_extra 밖 색 {ref}", layer=name, hint=[where]))
    if len(used_rgb) > profile["max_colors"]:
        found.append(issue("recipe.max_colors", "warn", f"한 층 색 {len(used_rgb)}개 > max_colors {profile['max_colors']}", layer=name, hint=["main.startColor", "colorOverLifetime.color"]))
    found.extend(_color_multiply(layer, palette))
    if layer.get("blend") == "additive":
        found.append(issue("recipe.additive", "info", "additive 층은 겹치면 색 수가 는다", layer=name, hint=["blend"]))
    return found


def _non_white(value, palette):
    """색 값 안에 흰색(#FFFFFF)이 아닌 색이 있나. 팔레트 번호가 틀리면 다른 규칙이 잡으니 넘긴다."""
    for ref in colors.refs_of(value):
        try:
            hex_value = colors.to_hex(ref, palette)
        except IndexError:
            continue
        if hex_value[:7] != "#FFFFFF":
            return True
    return False


def _color_multiply(layer, palette):
    """Unity 는 startColor × colorOverLifetime 색을 곱한다. 둘 다 색이 있으면 팔레트 밖 색이 나온다."""
    start = layer.get("main", {}).get("startColor")
    over = layer.get("colorOverLifetime", {}).get("color")
    if start is None or over is None:
        return []
    if not (_non_white(start, palette) and _non_white(over, palette)):
        return []
    detail = "startColor 와 colorOverLifetime 색이 곱해진다 — 한쪽 색 키를 #FFFFFF 로 두고 알파만 쓴다"
    hint = ["main.startColor", "colorOverLifetime.color"]
    return [issue("recipe.color_multiply", "warn", detail, layer=layer["name"], hint=hint)]


def _alpha_steps(value, where, layer_name, profile):
    if profile["alpha_steps"] != "binary":
        return []
    found = []
    if colors.uses_blend(value):
        found.append(issue("recipe.alpha_steps", "error", f"{where} : alpha_steps binary 인데 mode blend", layer=layer_name, hint=[where]))
    half = [a for a in colors.alphas_of(value) if a not in (0, 1)]
    if half:
        found.append(issue("recipe.alpha_steps", "error", f"{where} : alpha_steps binary 인데 반투명 알파 {sorted(set(round(a, 3) for a in half))}", layer=layer_name, hint=[where]))
    return found


def _blend(layer):
    if layer.get("material") == "lit" and layer.get("blend") == "additive":
        return [issue("recipe.blend", "error", "lit 머티리얼은 additive 를 못 쓴다(알파 블렌드만)", layer=layer["name"], hint=["material", "blend"])]
    return []


def _max_particles(layer, profile):
    count = layer.get("main", {}).get("maxParticles", UNITY_DEFAULT_MAX_PARTICLES)
    if count <= profile["max_particles"]:
        return []
    return [issue("recipe.max_particles", "error", f"maxParticles {count} > 프로필 상한 {profile['max_particles']} (안 적으면 Unity 기본 {UNITY_DEFAULT_MAX_PARTICLES})", layer=layer["name"], hint=["main.maxParticles"])]


def _texture(layer, profile, recipe_dir, root):
    """recipe.paths(텍스처 파일 자리) · recipe.flipbook(시트)."""
    name = layer["name"]
    texture = layer.get("texture", "px1")
    sheet = layer.get("textureSheet")
    if texture in TEXTURE_BUILTINS:
        if sheet is None:
            return []
        return [issue("recipe.flipbook", "error", f"textureSheet 가 있는데 시트 파일이 없다(texture {texture})", layer=name, hint=["texture"])]
    if material_lib.is_lib(texture):
        # 툴 안 소재는 경로 감옥(--input-root) 대상이 아니다 — 레시피가 경로를 안 적는다.
        return _lib_texture(layer, profile)
    try:
        path = ensure_inside(recipe_dir / texture, root)
    except VfxError as exc:
        detail = f"texture : {exc.message} — 레시피 폴더 밖 파일이면 --input-root 로 그 위 폴더를 준다"
        return [issue("recipe.paths", "error", detail, layer=name, hint=["texture", "--input-root"])]
    if not path.is_file():
        return [issue("recipe.paths", "error", f"texture 파일이 없다 : {texture}", layer=name, hint=["texture"])]
    if sheet is None:
        return []
    return _flipbook(path, sheet, name, profile) + _sheet_size_fixed(layer)


def _lib_texture(layer, profile):
    """`lib:` 층 — 이름 · tiles · row(recipe.lib) 뒤에 시트 규칙 · 크기 배수 · 플립북 수명. 메타는 한 번만 읽는다."""
    texture = layer["texture"]
    try:
        meta = material_lib.load(material_lib.lib_name(texture))
    except VfxError as exc:
        return [issue(material_lib.RULE, "error", f"texture {texture!r} : {exc.message}", layer=layer["name"], hint=["texture"])]
    found = _lib_meta_rules(layer, meta)
    if has_errors(found):
        return found
    sheet = layer.get("textureSheet")
    if sheet is not None:
        filled = {"tiles": meta["tiles"]}
        filled.update(sheet)
        png = material_lib.LIB_DIR / f"{meta['name']}.png"
        found.extend(_flipbook(png, filled, layer["name"], profile))
    found.extend(_lib_size(layer, meta, profile))
    found.extend(_flipbook_life(layer, meta, sheet, profile))
    return found


def _lib_meta_rules(layer, meta):
    """recipe.lib — tiles 가 메타와 다름 · row 범위 밖 = error, 변형 줄 소재에 row 없음 = warn."""
    name = layer["name"]
    sheet = layer.get("textureSheet")
    found = []
    if sheet is not None and "tiles" in sheet and sheet["tiles"] != meta["tiles"]:
        detail = f"textureSheet.tiles {sheet['tiles']} 가 소재 {meta['name']} 의 {meta['tiles']} 와 다르다 — 안 적으면 메타에서 채운다"
        found.append(issue(material_lib.RULE, "error", detail, layer=name, hint=["textureSheet.tiles"]))
    row = None
    if sheet is not None:
        row = sheet.get("row")
    if isinstance(row, int) and not 0 <= row < meta["rows"]:
        detail = f"textureSheet.row {row} 가 소재 {meta['name']} 의 줄 수 {meta['rows']} 밖이다"
        found.append(issue(material_lib.RULE, "error", detail, layer=name, hint=["textureSheet.row"]))
    if row is None and meta["kind"] == "grain" and meta["rows"] > 1:
        detail = f"소재 {meta['name']} 는 변형 {meta['rows']} 줄짜리 — textureSheet.row 를 안 적으면 시트 전체가 넘어간다"
        found.append(issue(material_lib.RULE, "warn", detail, layer=name, hint=["textureSheet.row"]))
    return found


def _size_over_lifetime(layer):
    """sizeOverLifetime.size 값. 없으면 None."""
    return layer.get("sizeOverLifetime", {}).get("size")


def _sheet_size_fixed(layer):
    """recipe.lib_size(error) — 시트 · 소재 층의 크기가 입자마다 · 생애 동안 하나로 고정돼 있지 않다.

    크기 곡선(sizeOverLifetime)이나 startSize 의 random · 곡선은 키(끝점)가 정수 배여도 사이 값에서
    소재 픽셀이 텍셀에 안 맞아 모양이 깨진다. 생애 동안 바뀌면 장마다 깨지는 자리가 달라 깜박인다(실험 3).
    크기를 바꾸고 싶으면 크기가 다른 소재 장을 플립북으로 넘긴다.
    """
    found = []
    size_value = _size_over_lifetime(layer)
    if size_value is not None and len(set(values.numbers_of(size_value))) > 1:
        detail = "시트 · 소재 층에 크기 곡선(sizeOverLifetime)이 걸렸다 — 사이 크기에서 도트가 깨지고 깜박인다. 크기 변화는 플립북 장으로 낸다"
        found.append(issue("recipe.lib_size", "error", detail, layer=layer["name"], hint=["sizeOverLifetime.size", "texture"]))
    start = layer.get("main", {}).get("startSize")
    if start is not None and len(set(values.numbers_of(start))) > 1:
        detail = "시트 · 소재 층의 startSize 가 상수가 아니다(random · 곡선) — 사이 크기에서 도트가 깨진다. 크기가 다른 입자는 층을 나눈다"
        found.append(issue("recipe.lib_size", "error", detail, layer=layer["name"], hint=["main.startSize"]))
    return found


def _lib_size(layer, meta, profile):
    """recipe.lib_size(error) — 입자 크기(startSize × 상수 크기 배율)가 소재 칸의 정수 배가 아니면 도트가 깨진다.

    크기가 고정이 아니면(_sheet_size_fixed) 그것만 알린다 — 그 뒤엔 startSize · 배율이 각각 숫자 하나다.
    """
    fixed = _sheet_size_fixed(layer)
    if fixed:
        return fixed
    size = profile["ppu"]
    if "startSize" in layer.get("main", {}):
        size = values.numbers_of(layer["main"]["startSize"])[0]
    size_value = _size_over_lifetime(layer)
    if size_value is not None:
        size *= values.numbers_of(size_value)[0]
    cell = meta["cell"]
    if _whole_multiple(size, cell):
        return []
    detail = f"입자 크기(텍셀) {round(size, 6)} 가 소재 {meta['name']} 칸 {cell} 의 정수 배가 아니다 — 소재 픽셀이 텍셀에 안 맞는다"
    return [issue("recipe.lib_size", "error", detail, layer=layer["name"], hint=["main.startSize", "sizeOverLifetime.size"])]


def _whole_multiple(size, cell):
    ratio = size / cell
    return ratio >= 1 - SIZE_TOLERANCE and abs(ratio - round(ratio)) <= SIZE_TOLERANCE


def _flipbook_life(layer, meta, sheet, profile):
    """recipe.flipbook_life — 최대 수명이 장 수 ÷ fps 보다 길면 FPS 모드가 남는 시간에 처음부터 다시 돈다."""
    frames = material_lib.frames_of(meta, sheet)
    if frames <= 1:
        return []
    fps = profile["fps"]
    if sheet is not None:
        fps = sheet.get("fps", fps)
    if fps <= 0:
        return []
    lifetime = layer.get("main", {}).get("startLifetime", UNITY_DEFAULT_LIFETIME)
    longest = max(values.numbers_of(lifetime))
    span = frames / fps
    if longest <= span + LIFE_TOLERANCE:
        return []
    detail = f"최대 수명 {longest}초 > 소재 {meta['name']} {frames}장 ÷ fps {fps} = {span:.3f}초 — 플립북이 다시 돈다"
    return [issue("recipe.flipbook_life", "warn", detail, layer=layer["name"], hint=["main.startLifetime", "textureSheet.fps"])]


def _flipbook(path, sheet, layer_name, profile):
    found = []
    try:
        with Image.open(path) as image:
            width, height = image.size
    except OSError:
        return [issue("recipe.flipbook", "error", f"시트를 그림으로 못 읽었다 : {path.name}", layer=layer_name, hint=["texture"])]
    tiles = sheet.get("tiles", [1, 1])
    if width % tiles[0] != 0 or height % tiles[1] != 0:
        found.append(issue("recipe.flipbook", "error", f"시트 {width}×{height} 가 tiles {tiles} 로 안 나눠진다", layer=layer_name, hint=["textureSheet.tiles"]))
    row = sheet.get("row")
    if isinstance(row, int) and row >= tiles[1]:
        found.append(issue("recipe.flipbook", "error", f"textureSheet.row {row} 가 줄 수 {tiles[1]} 밖이다", layer=layer_name, hint=["textureSheet.row"]))
    fps = sheet.get("fps", profile["fps"])
    low, high = profile["fps_range"]
    if not low <= fps <= high:
        found.append(issue("recipe.flipbook", "error", f"플립북 fps {fps} 가 프로필 fps_range {profile['fps_range']} 밖이다", layer=layer_name, hint=["textureSheet.fps"]))
    return found
