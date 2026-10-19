"""프레임 지표 → issues · 증상(설계 8-2 · 7-2).

묶음 규칙 : 어긋난 프레임 비율 > seq_tolerance.ratio 또는 연속 run 장 이상이면 warn, 그보다 적으면 info.
비율의 분모는 안 빈 프레임 수다(빈 프레임은 어긋날 것이 없다).
"""

import json
import math
from pathlib import Path

from vfxtool import report
# frame.palette 문턱 — Linear 꼭짓점 색 8비트 반올림 흡수. 근거는 변형묶음설계 「구현 뒤 정정」 표.
from vfxtool.measure_metrics import PALETTE_TOLERANCE

DENSE_MAX_COVERAGE = 40.0
LOPSIDED_TEXELS = 2.0
# 무게중심 평균이 우연(입자 수 · 흩어짐)으로 흔들리는 폭의 몇 배부터 치우침으로 보나.
# 도트풍 이펙트는 입자가 몇 개뿐이라 대칭 이펙트도 시드마다 2 텍셀쯤은 쉽게 치우친다(U4 실측).
LOPSIDED_SIGMA = 2.0
# 문턱 상한 = 캔버스 폭 / 이 값. 덩어리 2~3개가 넓게 퍼지면 우연 폭이 캔버스 절반을 넘어 진짜 쏠림을 놓친다.
LOPSIDED_MAX_WIDTH_DIV = 4.0
# 무게중심 규칙(frame.lopsided · template.symmetric_x · centroid_rise_max · centroid_rises)이 볼 장 = judged_frames.
#   절대 — 덮은 면적이 캔버스의 MIN_JUDGED_COVERAGE % 미만인 장은 뺀다 (낱알 한두 개뿐인 장, 10-15 실측 land_dust 9장 0.2%).
#   상대 — 최대 덮은 면적 장 **뒤**의 장은 그 면적 × MIN_JUDGED_SHARE 미만이면 꼬리로 뺀다. 바깥으로 흩어진 끝 장은
#          입자 몇 개뿐이라 좌우 텍셀 수 차가 무게중심을 크게 흔든다 (10-15 exp7 : land_dust f9 1.5% · 최대 10% →
#          시드 9개 중 6개 symmetric_x warn, hit_sparks 끝 장 0.1% 의 cx −10 이 lopsided 평균을 끌어 시드 11개 중 2개 warn).
#          머리 장(처음 뿜는 작은 장)은 상대 문턱을 안 쓴다 — 빼면 상승 · 초반 치우침의 기준 장이 사라진다(코드리뷰 10-15).
# 상대 문턱은 장마다 면적이 고른 성긴 효과의 장을 안 뺀다 — 절대 2% 같은 고정값은 그런 판의 장을 다 빼 조용히 통과시킨다.
# 다 빠지면 안 빈 장 모두로 판정한다(조용히 통과 금지).
MIN_JUDGED_COVERAGE = 0.5
MIN_JUDGED_SHARE = 0.25
BRIGHT_MIN_TEXELS = 4
BRIGHT_MIN_SHARE = 0.1
BRIGHT_WARN_RUN = 3  # 흰 번쩍이 이만큼 연속이면 warn(1~2장 번쩍은 도트 관례)
SHORT_MAX_FRAMES = 2
SYMPTOMS_PATH = Path(__file__).with_name("symptoms.json")


def load_rule_hints():
    """증상표 밖 규칙(주로 Unity 쪽)의 hint 표 {rule: [칸 …]}."""
    with SYMPTOMS_PATH.open(encoding="utf-8") as handle:
        return json.load(handle).get("rule_hints", {})


def load_symptoms():
    with open(SYMPTOMS_PATH, encoding="utf-8") as handle:
        return json.load(handle)["symptoms"]


def _modules(layer):
    """층 모듈은 층 바로 아래가 기본. modules 묶음으로 온 판도 받는다."""
    merged = dict(layer.get("modules") or {})
    merged.update(layer)
    return merged


def _is_curve(value):
    return isinstance(value, dict) and ("curve" in value or "random_curve" in value)


def layer_flags(layers):
    """판에 additive · lit · 회전/크기 곡선 · 시트 텍스처 층이 있나."""
    flags = {"additive": False, "lit": False, "rotation_or_size": False, "sheet": False}
    for layer in layers:
        mods = _modules(layer)
        if mods.get("textureSheet"):
            flags["sheet"] = True
        if layer.get("blend") == "additive":
            flags["additive"] = True
        if layer.get("material") == "lit":
            flags["lit"] = True
        main = mods.get("main") or {}
        size = (mods.get("sizeOverLifetime") or {}).get("size")
        if main.get("startRotation") or mods.get("rotationOverLifetime") or _is_curve(size):
            flags["rotation_or_size"] = True
    return flags


def longest_run(bad):
    best, run = 0, 0
    for flag in bad:
        run = run + 1 if flag else 0
        best = max(best, run)
    return best


def bundle_severity(bad, denominator, tolerance):
    """묶음 규칙 심각도. 어긋남이 없으면 None."""
    count = sum(1 for flag in bad if flag)
    if count == 0:
        return None
    ratio = count / max(1, denominator)
    if ratio > float(tolerance["ratio"]) or longest_run(bad) >= int(tolerance["run"]):
        return "warn"
    return "info"


def _issue(rule, severity, frame, detail):
    return report.issue(rule, severity, detail, frame=frame)


def _bad_frames(frames, bad):
    return [f.i for f, flag in zip(frames, bad) if flag]


def _bundle_issue(rule, frames, bad, nonempty, tolerance, label, cap=None):
    severity = bundle_severity(bad, nonempty, tolerance)
    if severity is None:
        return []
    if cap is not None and severity == "warn":
        severity = cap
    hit = _bad_frames(frames, bad)
    detail = f"{label} — {len(hit)}/{nonempty} 장 어긋남, 연속 최대 {longest_run(bad)} 장 (프레임 {hit})"
    return [_issue(rule, severity, hit[0], detail)]


def _bundle_issues(frames, metrics, profile, flags, nonempty):
    tolerance = profile["seq_tolerance"]
    color_limit = int(profile["max_colors"]) * (2 if flags["additive"] else 1)
    grid_cap = None
    if flags["rotation_or_size"] or not profile["snap"]:
        grid_cap = "info"
    pixel_sizes = set(int(v) for v in profile["pixel_size"])
    issues = []
    issues += _bundle_issue("frame.grid", frames, [m["grid_ratio"] < 1.0 for m in metrics],
                            nonempty, tolerance, "경계가 텍셀 격자에 안 맞음", grid_cap)
    issues += _bundle_issue("frame.colors", frames, [len(m["colors"]) > color_limit for m in metrics],
                            nonempty, tolerance, f"색 수가 {color_limit} 넘음")
    if not flags["lit"]:
        issues += _bundle_issue("frame.palette", frames, [m["palette_dist"] > PALETTE_TOLERANCE for m in metrics],
                                nonempty, tolerance, "팔레트 · fx_extra 밖 색")
    bad_size = [m["particle_size"] is not None and m["particle_size"] not in pixel_sizes for m in metrics]
    # 시트 텍스처 층은 그림 폭이 입자 폭이라 pixel_size 집합을 못 지킨다 — 알리기만 한다.
    size_cap = None
    if flags["sheet"]:
        size_cap = "info"
    issues += _bundle_issue("frame.pixel_size", frames, bad_size, nonempty, tolerance,
                            f"입자 폭 최빈값이 pixel_size {sorted(pixel_sizes)} 밖", size_cap)
    return issues


def _empty_issues(frames, metrics, loop, nonempty, truncated=False):
    issues = []
    if metrics[0]["covered"] == 0:
        issues.append(_issue("frame.first_empty", "warn", frames[0].i, "첫 프레임이 빔"))
    if not loop and metrics[-1]["covered"] > 0:
        severity, detail = "warn", "one-shot 인데 끝 프레임이 안 빔"
        if truncated:
            severity, detail = "info", "프레임 상한에 걸려 끝까지 못 뽑았다 — 끝 프레임 판정은 참고만"
        issues.append(_issue("frame.last_not_empty", severity, frames[-1].i, detail))
    if nonempty <= SHORT_MAX_FRAMES:
        issues.append(_issue("frame.too_short", "warn", None, f"안 빈 프레임이 {nonempty} 장뿐"))
    return issues


def judged_frames(metrics):
    """무게중심 규칙이 볼 장. (판정 장 번호 자리 목록, 뺀 장 수, 꼬리 문턱 %) 를 돌려준다.

    안 빈 장(덮은 칸 > 0 · 무게중심 있음)만 본다. 최대 덮은 면적 장(같으면 앞 장)까지는 절대 문턱,
    그 뒤는 max(절대 문턱, 최대 × MIN_JUDGED_SHARE). 다 빠지면 안 빈 장 모두. coverage 가 없는 옛 지표는 0 으로 본다.
    """
    shown = [i for i, m in enumerate(metrics) if m.get("covered") and m.get("centroid") is not None]
    if not shown:
        return [], 0, MIN_JUDGED_COVERAGE
    cover = [metrics[i].get("coverage", 0.0) for i in shown]
    peak_at = cover.index(max(cover))
    tail = max(MIN_JUDGED_COVERAGE, MIN_JUDGED_SHARE * cover[peak_at])
    judged = [i for k, (i, c) in enumerate(zip(shown, cover))
              if c >= (MIN_JUDGED_COVERAGE if k <= peak_at else tail)]
    if not judged:
        judged = shown
    return judged, len(shown) - len(judged), tail


def dropped_note(dropped, tail):
    """뺀 장이 있으면 detail 끝에 붙일 문구. 없으면 빈 글."""
    if dropped == 0:
        return ""
    return (f" (덮은 면적 문턱 미만 {dropped}장 뺌 — 최대 장까지 {MIN_JUDGED_COVERAGE:.2f}%,"
            f" 그 뒤 꼬리 {tail:.2f}%)")


def centroid_noise(m):
    """한 장 무게중심 x 가 우연으로 흔들리는 폭(텍셀) = 덩어리 무게중심 x 표준편차 / √덩어리 수.

    덩어리 하나로 합쳐진 판(빛 · 빽빽한 먼지)은 0 이라 문턱이 고정 2 텍셀로 돌아간다.
    덩어리 수 · 흩어짐이 없는 지표(빈 그림 · 옛 지표)도 0.
    """
    blobs = m.get("blobs") or 0
    if blobs <= 0:
        return 0.0
    return float(m.get("spread_x") or 0.0) / math.sqrt(blobs)


def noise_limit(base, noise):
    """고정 문턱 base 와 우연 폭의 LOPSIDED_SIGMA 배 중 큰 것."""
    return max(base, LOPSIDED_SIGMA * noise)


def lopsided_limit(metrics):
    """치우침 문턱(텍셀). 판정 장(judged_frames)의 우연 폭 평균으로 잰다 — 평균을 내는 장과 같은 집합.

    입자가 적고 넓게 흩어진 판일수록 문턱이 커진다. 고정 문턱 LOPSIDED_TEXELS 아래로는 안 내린다.
    지표에 캔버스 폭(width)이 있으면 폭 / LOPSIDED_MAX_WIDTH_DIV 를 넘지 않는다(고정 문턱보다는 안 낮춘다).
    """
    judged, _, _ = judged_frames(metrics)
    noises = [centroid_noise(metrics[i]) for i in judged]
    if not noises:
        return LOPSIDED_TEXELS
    limit = noise_limit(LOPSIDED_TEXELS, sum(noises) / len(noises))
    widths = [m["width"] for m in metrics if m.get("width")]
    if widths:
        limit = min(limit, max(LOPSIDED_TEXELS, min(widths) / LOPSIDED_MAX_WIDTH_DIV))
    return limit


def _shape_issues(frames, metrics, profile, flags, limit=None):
    """limit = frame.lopsided 문턱. None 이면 metrics 로 잰다(measure 는 한 번 재서 넘긴다)."""
    issues = []
    clipped = _bad_frames(frames, [m["clipped"] for m in metrics])
    if clipped:
        issues.append(_issue("frame.clipped", "warn", clipped[0], f"테두리 칸을 덮음 (프레임 {clipped})"))
    dense = max(m["coverage"] for m in metrics)
    if dense > DENSE_MAX_COVERAGE:
        worst = frames[[m["coverage"] for m in metrics].index(dense)].i
        issues.append(_issue("frame.dense", "warn", worst, f"덮은 면적 {dense:.1f}% > {DENSE_MAX_COVERAGE:.0f}%"))
    judged, dropped, tail = judged_frames(metrics)
    if judged:
        mean_x = sum(metrics[i]["centroid"][0] for i in judged) / len(judged)
        if limit is None:
            limit = lopsided_limit(metrics)
        if abs(mean_x) > limit:
            detail = f"무게중심 x 평균 {mean_x:.2f} 텍셀 > 문턱 {limit:.2f}{dropped_note(dropped, tail)}"
            issues.append(_issue("frame.lopsided", "warn", None, detail))
    if flags["additive"]:
        bright = [m["bright_count"] >= max(BRIGHT_MIN_TEXELS, BRIGHT_MIN_SHARE * m["covered"]) for m in metrics]
        hit = _bad_frames(frames, bright)
        if hit:
            # 흰 번쩍 1~2장은 도트 관례라 info. 연속 BRIGHT_WARN_RUN 장 이상만 warn.
            run = longest_run(bright)
            severity = "warn" if run >= BRIGHT_WARN_RUN else "info"
            issues.append(_issue("frame.bright", severity, hit[0],
                                 f"선형 밝기 0.98 이상 칸이 넓음 — 연속 최대 {run} 장 (프레임 {hit})"))
    if not flags["additive"]:
        semi = _bad_frames(frames, [m["semi_alpha"] > 0 for m in metrics])
        if semi:
            severity = "warn" if profile["alpha_steps"] == "binary" else "info"
            issues.append(_issue("frame.semi_alpha", severity, semi[0], f"반투명 칸이 있음 (프레임 {semi})"))
    return issues


def evaluate(frames, metrics, profile, layers, loop, truncated=False, lopsided=None):
    """issues 목록. 모든 프레임이 비면 all_empty 하나만 돌려준다(나머지는 뜻이 없다).

    lopsided = 미리 잰 치우침 문턱(없으면 여기서 잰다).
    """
    nonempty = sum(1 for m in metrics if m["covered"] > 0)
    if nonempty == 0:
        return [_issue("frame.all_empty", "error", None, "모든 프레임 덮은 면적 0")]
    flags = layer_flags(layers)
    issues = _empty_issues(frames, metrics, loop, nonempty, truncated)
    issues += _shape_issues(frames, metrics, profile, flags, lopsided)
    issues += _bundle_issues(frames, metrics, profile, flags, nonempty)
    return issues


def attach_symptoms(issues, symptoms):
    """warn · error issue 에 증상표 힌트를 달고, 잡힌 증상 낱말 목록을 돌려준다(표 순서)."""
    found = set()
    for issue in issues:
        for symptom in symptoms:
            if issue["rule"] not in symptom["detect"]:
                continue
            issue["hint"] = list(symptom["params"])
            if issue["severity"] != "info":
                found.add(symptom["name"])
    return [s["name"] for s in symptoms if s["name"] in found]

