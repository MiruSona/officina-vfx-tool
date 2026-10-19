"""기본값 < PNG < 화풍 조각 < 손 덮기 순으로 프로필을 합친다. 칸마다 source 를 적는다(설계 3-2)."""
from vfxtool.errors import VfxError
from vfxtool.profile.common import DEFAULTS, PROFILE_VERSION, defaults, make_issue, normalize

# 손 덮기에 이전 profile.json 을 그대로 넣어도 되게 이 둘은 말없이 넘긴다.
_PASS_KEYS = ("version", "source")


def _apply_override(profile: dict, source: dict, override: dict) -> list:
    issues = []
    for key, value in override.items():
        if key in _PASS_KEYS:
            continue
        if key not in DEFAULTS:
            issues.append(make_issue("profile.unknown_key", "warn", f"손 덮기의 모르는 칸 {key} 를 건너뛴다", ["--override"]))
            continue
        try:
            profile[key] = normalize(key, value, profile[key])
        except ValueError as error:
            raise VfxError(f"손 덮기 칸 {key} 값이 틀렸다 — {error}") from error
        source[key] = "override"
    return issues


def merge(png_fields: dict, style_fields: dict, override) -> dict:
    """{"profile": {...}, "issues": [...]}. png·style 칸은 이미 다듬어진 값이라 그대로 덮는다."""
    profile = defaults()
    source = {key: "default" for key in DEFAULTS}
    for layer_name, fields in (("png", png_fields), ("style", style_fields)):
        for key, value in fields.items():
            profile[key] = value
            source[key] = layer_name

    issues = []
    if override is not None:
        if not isinstance(override, dict):
            raise VfxError("손 덮기 파일은 JSON 객체여야 한다")
        issues = _apply_override(profile, source, override)

    low, high = profile["fps_range"]
    if not low <= profile["fps"] <= high:
        issues.append(make_issue("profile.fps_range", "warn", f"fps {profile['fps']} 가 fps_range {profile['fps_range']} 밖이다",
                                 ["fps", "fps_range"]))

    result = {"version": PROFILE_VERSION}
    result.update(profile)
    result["source"] = source
    return {"profile": result, "issues": issues}
