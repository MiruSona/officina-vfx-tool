"""Unity 에 줄 job.json 을 만든다. 프레임 시각은 여기서 세고 C# 은 따른다 (설계 5-4 · 6-2)."""

import math
from pathlib import Path, PurePosixPath

from vfxtool.errors import VfxError
from vfxtool.paths import write_json

MODES = ("build", "render", "both")
BACKGROUNDS = ("transparent", "black", "white")
DEFAULT_SAVE_ROOT = "Assets/Vfx/Generated"
MAX_FRAMES = 48
DEFAULT_FPS = 12
# main 에 칸이 없으면 Unity 기본값이 쓰인다.
_UNITY_DEFAULT_DELAY = 0.0
_UNITY_DEFAULT_LIFETIME = 5.0
_EPS = 1e-9


def value_max(value) -> float:
    """다형 값 넷(숫자 · random · curve · random_curve)이 가질 수 있는 가장 큰 값."""
    if isinstance(value, bool):
        raise VfxError(f"숫자 칸에 bool 이 왔다 — {value}")
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, dict):
        raise VfxError(f"모르는 다형 값 꼴 — {value!r}")

    if "random" in value:
        return max(float(v) for v in value["random"])
    if "curve" in value:
        curves = [value["curve"]]
    elif "random_curve" in value:
        curves = list(value["random_curve"])
    else:
        raise VfxError(f"모르는 다형 값 꼴 — {value!r}")

    # 키마다 mult 를 곱한 뒤 고른다(mult 가 음수여도 맞다).
    mult = float(value.get("mult", 1))
    return max(float(v) * mult for keys in curves for _, v in keys)


def _layer_peak(resolved: dict, field: str, default: float) -> float:
    peaks = []
    for layer in resolved.get("layers", []):
        main = layer.get("main", {})
        peaks.append(value_max(main.get(field, default)))
    if not peaks:
        return default
    return max(peaks)


def _full_count(resolved: dict, fps: int) -> tuple[int, float]:
    """상한을 대기 전 프레임 수와 첫 시각."""
    if fps <= 0:
        raise VfxError(f"fps 는 1 이상이어야 한다 — {fps}")
    duration = float(resolved["duration"])
    if resolved.get("loop", False):
        return math.ceil(duration * fps - _EPS), duration
    delay = _layer_peak(resolved, "startDelay", _UNITY_DEFAULT_DELAY)
    lifetime = _layer_peak(resolved, "startLifetime", _UNITY_DEFAULT_LIFETIME)
    return math.ceil((duration + delay + lifetime) * fps - _EPS), 0.0


def frame_times(resolved: dict, fps: int) -> list[dict]:
    """뽑을 프레임 [{i, t}]. t=0 은 빈 그림이라 안 뽑는다(i 는 1부터). one-shot · loop 둘 다 상한 48.

    t = start + (i - 0.5)/fps — 칸 가운데를 찍는다. i/fps 는 fps 12 플립북 칸 경계와 겹쳐 내림 오차로 칸이 빠졌고,
    (i + 0.5)/fps 는 첫 장이 1번 칸이라 플립북 0번 칸이 안 찍혔다. (i - 0.5)/fps 면 N 장이 0~N-1 칸을 하나씩 덮는다.
    """
    count, start = _full_count(resolved, fps)
    count = max(min(count, MAX_FRAMES), 1)
    return [{"i": i, "t": round(start + (i - 0.5) / fps, 6)} for i in range(1, count + 1)]


def frames_truncated(resolved: dict, fps: int) -> bool:
    """상한 48 에 걸려 뒤쪽 프레임을 못 뽑았나."""
    count, _ = _full_count(resolved, fps)
    return count > MAX_FRAMES


def normalize_save_root(save_root: str) -> str:
    """Assets/ 안의 상대 경로만 받는다. 절대 경로 · `..` 는 거절(설계 5-5).

    앞뒤 공백을 벗기지 않는다 — 조각 끝 공백 · 점(`bad `)은 Windows 가 몰래 벗겨 다른 폴더(`bad/`)에
    저장되니 C# 쪽 검사와 같이 거절한다.
    """
    text = save_root.replace("\\", "/")
    if not text or text.startswith("/") or ":" in text:
        raise VfxError(f"--save-root 는 Assets/ 로 시작하는 상대 경로여야 한다 — {save_root!r}")

    parts = [p for p in PurePosixPath(text).parts if p != "."]
    bad = [p for p in parts if p != ".." and p != p.rstrip(" .")]
    if bad:
        raise VfxError(f"--save-root 조각 끝에 공백 · 점이 있다 — {bad[0]!r} ({save_root!r})")
    if ".." in parts or not parts or parts[0] != "Assets":
        raise VfxError(f"--save-root 는 Assets/ 안이어야 한다 — {save_root!r}")
    return "/".join(parts)


def parse_backgrounds(text: str | None) -> list[str]:
    """`black,white` 꼴을 목록으로. 비면 투명 1회."""
    if not text:
        return ["transparent"]
    names = [name.strip() for name in text.split(",") if name.strip()]
    for name in names:
        if name not in BACKGROUNDS:
            raise VfxError(f"모르는 배경 — {name} (쓸 수 있는 것 : {', '.join(BACKGROUNDS)})")
    return names


def make_job(recipe: Path, mode: str, save_root: str, out_dir: Path,
             frames: list[dict], backgrounds: list[str]) -> dict:
    if mode not in MODES:
        raise VfxError(f"모르는 mode — {mode}")
    return {
        "recipe": str(recipe.resolve()),
        "mode": mode,
        "saveRoot": normalize_save_root(save_root),
        "outDir": str(out_dir.resolve()),
        "frames": frames,
        "backgrounds": backgrounds,
    }


def write_job(path: Path, job: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, job)
    return path
