"""화풍 조각 JSON(ArtTool 산출물)에서 아는 키만 프로필 칸으로 옮긴다.
키 대응표 : VFXTool/Docs/Guide/화풍조각대응표.md — 그쪽 형식이 바뀌면 STYLE_KEYS 와 그 표만 고친다."""
from vfxtool.profile.common import make_issue, normalize

# 화풍 조각 키 → 프로필 칸. 순서대로 읽으므로 같은 칸이면 뒤 키가 이긴다(frame_ms < fps).
STYLE_KEYS = [
    ("palette", "palette"),
    ("ppu", "ppu"),
    ("pixels_per_unit", "ppu"),
    ("pixel_size", "pixel_size"),
    ("max_colors", "max_colors"),
    ("frame_ms", "fps"),
    ("fps", "fps"),
    ("fps_range", "fps_range"),
    ("outline", "outline"),
]
_KNOWN = {key for key, _ in STYLE_KEYS}


def _palette_value(value):
    # {"colors": [...]} 꼴도 받는다.
    if isinstance(value, dict) and "colors" in value:
        return value["colors"]
    return value


def _frame_ms_to_fps(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"양수 ms 여야 한다 : {value!r}")
    return max(1, round(1000 / value))


def map_style(style: dict) -> dict:
    """{"fields": {...}, "issues": [...], "ignored": [모르는 키]} 를 돌려준다. 틀린 값은 warn 으로 건너뛴다."""
    fields = {}
    issues = []
    for key, field in STYLE_KEYS:
        if key not in style:
            continue
        value = style[key]
        if key == "palette":
            value = _palette_value(value)
        try:
            if key == "frame_ms":
                value = _frame_ms_to_fps(value)
            fields[field] = normalize(field, value, None)
        except ValueError as error:
            issues.append(make_issue("profile.style_value", "warn", f"화풍 조각 {key} 를 못 읽어 건너뛴다 — {error}", ["--style"]))
    ignored = sorted(key for key in style if key not in _KNOWN)
    return {"fields": fields, "issues": issues, "ignored": ignored}
