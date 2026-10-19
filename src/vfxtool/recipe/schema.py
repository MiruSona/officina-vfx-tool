"""레시피 칸 표 — 최상위 · 층 · 모듈(설계 2-1 ~ 2-3). 길이 단위 칸 표도 여기 한 곳에 둔다.

칸 꼴 : ("value",) 다형 값 · ("color",) 색 값 · ("int"|"number", 최소, 최대) · ("bool",) · ("str",)
· ("enum", 받는 값, 2차로 미룬 값) · ("vec", 받는 길이들) · ("bursts",) · ("tiles",) · ("row",) · ("canvas",) · ("layers",)
"""

import difflib
import re

NAME_PATTERN = r"[a-z0-9_]+"
# 층 이름 규칙 — C# SafeFileName 과 같은 규칙(파일 이름으로도 쓴다). fullmatch 로만 쓴다.
LAYER_NAME_PATTERN = r"[A-Za-z0-9_][A-Za-z0-9_.\-]*"
LAYER_NAME_MAX = 40
RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}
RECIPE_VERSION = 1
MAX_LAYERS = 6

TOP_FIELDS = {
    "version": ("int", 1, None),
    "name": ("str",),
    "profile": ("str",),
    "seed": ("int", None, None),
    "fixedTimeStep": ("bool",),
    "duration": ("number", 0, None),
    "fps": ("int", 1, None),
    "loop": ("bool",),
    "canvas": ("canvas",),
    "bloom": ("bool",),
    "light": ("enum", ("none", "global"), ()),
    "layers": ("layers",),
}
TOP_REQUIRED = ("version", "name", "profile", "seed", "fixedTimeStep", "duration", "layers")

TEMPLATE_FIELDS = ("template", "params", "preset", "override")

LAYER_FIELDS = {
    "name": ("str",),
    "material": ("enum", ("unlit", "lit"), ()),
    "blend": ("enum", ("alpha", "additive"), ()),
    "texture": ("str",),
    "sortOrder": ("int", None, None),
    "space": ("enum", ("local", "world"), ()),
    "offset": ("vec", (2,)),
}

SHAPE_TYPES = ("Circle", "Cone", "Box", "Edge", "Sphere")
SHAPE_LATER = ("Mesh", "MeshRenderer", "SkinnedMeshRenderer", "Sprite", "SpriteRenderer", "Hemisphere", "Donut", "Rectangle")
RENDER_LATER = ("Stretch", "StretchedBillboard", "HorizontalBillboard", "VerticalBillboard", "Mesh", "None")

# 모듈 이름 → {칸 이름: 칸 꼴}. 표 순서가 resolved.json 의 칸 순서다.
MODULES = {
    "main": {
        "startDelay": ("value",),
        "startLifetime": ("value",),
        "startSpeed": ("value",),
        "startSize": ("value",),
        "startColor": ("color",),
        "gravityModifier": ("value",),
        "maxParticles": ("int", 1, None),
        "startRotation": ("value",),
    },
    "emission": {
        "rateOverTime": ("value",),
        "bursts": ("bursts",),
    },
    "shape": {
        "type": ("enum", SHAPE_TYPES, SHAPE_LATER),
        "radius": ("number", 0, None),
        "angle": ("number", 0, 90),
        "arc": ("number", 0, 360),
        "box": ("vec", (2, 3)),
        "position": ("vec", (2, 3)),
        "rotation": ("vec", (3,)),
        "radiusThickness": ("number", 0, 1),
    },
    "velocityOverLifetime": {
        "x": ("value",),
        "y": ("value",),
        "radial": ("value",),
        "orbitalZ": ("value",),
        "space": ("enum", ("local", "world"), ()),
    },
    "colorOverLifetime": {"color": ("color",)},
    "sizeOverLifetime": {"size": ("value",)},
    "rotationOverLifetime": {"z": ("value",)},
    "noise": {
        "strength": ("value",),
        "frequency": ("number", 0, None),
        "scrollSpeed": ("value",),
        "octaves": ("int", 1, 4),
        "quality": ("enum", ("Low", "Medium", "High"), ()),
    },
    "textureSheet": {
        "tiles": ("tiles",),
        "fps": ("number", 0, None),
        "startFrame": ("value",),
        "cycles": ("int", 1, None),
        # 시트의 한 줄만 쓴다(Single Row) — 0 부터 센 줄 번호나 "random"(입자마다 줄을 고름). 소재묶음설계 4-1.
        "row": ("row",),
    },
    "renderer": {"renderMode": ("enum", ("Billboard",), RENDER_LATER)},
}

# 2차로 미룬 모듈. 적으면 recipe.unsupported error (조용히 버리지 않는다, 설계 2-3).
UNSUPPORTED_MODULES = (
    "trails", "subEmitters", "collision", "triggers", "lights", "externalForces",
    "forceOverLifetime", "inheritVelocity", "limitVelocityOverLifetime", "customData",
    "colorBySpeed", "sizeBySpeed", "rotationBySpeed", "lifetimeByEmitterSpeed",
)

# 텍셀 길이(속도는 텍셀/초) 칸 — check 가 ppu 로 나눠 Unity 단위로 바꾼다(설계 2-2).
# 시간 · 각도 · 배수(sizeOverLifetime · gravityModifier) · 주파수 칸은 그대로 둔다.
LENGTH_FIELDS = {
    ("layer", "offset"),
    ("main", "startSize"),
    ("main", "startSpeed"),
    ("shape", "radius"),
    ("shape", "box"),
    ("shape", "position"),
    ("velocityOverLifetime", "x"),
    ("velocityOverLifetime", "y"),
    ("velocityOverLifetime", "radial"),
    ("noise", "strength"),
}

# 각도 칸 — 레시피는 도(도/초), Unity API 는 라디안이라 resolve 가 바꾼다.
# shape 의 angle · arc · rotation 은 API 도 도라 여기 없다.
ANGLE_FIELDS = {
    ("main", "startRotation"),
    ("rotationOverLifetime", "z"),
}

# 크기 곡선은 기본 계단 — 중간 크기는 텍셀에 반쯤 걸쳐 도트가 깨진다(설계 2-4).
STEP_DEFAULT_FIELDS = {("sizeOverLifetime", "size")}


def is_length(module, field):
    return (module, field) in LENGTH_FIELDS


def known_layer_keys():
    """층에 적을 수 있는 이름 전부(오타 제안용)."""
    return list(LAYER_FIELDS) + list(TEMPLATE_FIELDS) + list(MODULES) + list(UNSUPPORTED_MODULES)


def suggest(name, known):
    """모르는 칸 이름에 가장 가까운 아는 이름. 없으면 None."""
    matches = difflib.get_close_matches(name, list(known), n=1, cutoff=0.6)
    if not matches:
        return None
    return matches[0]


def unknown_detail(where, name, known):
    """모르는 칸 issue 의 사람 말 — 가까운 이름이 있으면 같이 적는다."""
    guess = suggest(name, known)
    if guess is None:
        return f"{where} : 모르는 칸 {name!r}"
    return f"{where} : 모르는 칸 {name!r} — 혹시 {guess!r}?"


def layer_name_problem(name):
    """층 이름이 틀렸으면 까닭 글, 맞으면 None. C# SafeFileName 과 같은 규칙."""
    if not isinstance(name, str) or re.fullmatch(LAYER_NAME_PATTERN, name) is None:
        return f"층 이름 {name!r} 는 {LAYER_NAME_PATTERN} 꼴이어야 한다"
    if len(name) > LAYER_NAME_MAX:
        return f"층 이름 {name!r} 가 {LAYER_NAME_MAX}자를 넘는다"
    if ".." in name or name.endswith("."):
        return f"층 이름 {name!r} 에 '..' 이나 끝 '.' 은 못 쓴다"
    if name.split(".")[0].upper() in RESERVED_NAMES:
        return f"층 이름 {name!r} 는 Windows 예약 이름이다"
    return None
