"""템플릿이 적어 둔 프레임 단계 규칙(check 의 kind=frame)을 프레임 지표로 판정한다.

규칙 이름은 `template.<규칙>`, 어기면 warn. 프레임은 층을 나눠 뽑지 않으므로 판 전체 그림으로 잰다.
"""

from vfxtool import report
# 판정 장 고르기는 frame.lopsided 와 같은 것을 쓴다 — 까닭은 measure_rules 의 MIN_JUDGED_* 주석.
from vfxtool.measure_rules import dropped_note, judged_frames

SEVERITY = "warn"


def _judged(metrics):
    """무게중심 규칙이 볼 (번호 자리, 지표) 목록, 뺀 장 수, 꼬리 문턱(%) — measure_rules.judged_frames."""
    judged, dropped, tail = judged_frames(metrics)
    return [(index, metrics[index]) for index in judged], dropped, tail


def _issue(check, detail, frame=None):
    rule = f"template.{check['rule']}"
    return report.issue(rule, SEVERITY, f"{check['template']} : {detail}", layer=check.get("layer"), frame=frame)


def _last_frame_empty(check, frames, metrics):
    if metrics[-1]["covered"] == 0:
        return []
    return [_issue(check, "끝 프레임이 비어야 한다", frames[-1].i)]


def _first_frame_not_empty(check, frames, metrics):
    if metrics[0]["covered"] > 0:
        return []
    return [_issue(check, "첫 프레임부터 보여야 한다", frames[0].i)]


def _coverage_max(check, frames, metrics):
    limit = float(check["args"].get("percent", 100))
    worst = max(range(len(metrics)), key=lambda index: metrics[index]["coverage"])
    value = metrics[worst]["coverage"]
    if value <= limit:
        return []
    return [_issue(check, f"덮은 면적 {value:.1f}% > {limit:g}%", frames[worst].i)]


def _max_luma(check, frames, metrics):
    limit = float(check["args"].get("max", 1.0))
    worst = max(range(len(metrics)), key=lambda index: metrics[index]["max_luma"])
    value = metrics[worst]["max_luma"]
    if value <= limit:
        return []
    return [_issue(check, f"최대 밝기 {value:.3f} > {limit:g}", frames[worst].i)]


def _centroid_rise_max(check, frames, metrics):
    """첫 판정 프레임의 무게중심 y 보다 얼마나 올라갔나. 판정 장은 judged_frames."""
    shown, dropped, floor = _judged(metrics)
    if not shown:
        return []
    limit = float(check["args"].get("texels", 0))
    start_y = shown[0][1]["centroid"][1]
    index, top = max(shown, key=lambda pair: pair[1]["centroid"][1])
    rise = top["centroid"][1] - start_y
    if rise <= limit:
        return []
    detail = f"무게중심이 {rise:.1f} 텍셀 올라갔다 > {limit:g}{dropped_note(dropped, floor)}"
    return [_issue(check, detail, frames[index].i)]


def _centroid_rises(check, frames, metrics):
    """첫 판정 장보다 끝 판정 장의 무게중심 y 가 높아야 한다. 판정 장은 judged_frames."""
    shown, _, _ = _judged(metrics)
    if len(shown) < 2:
        return []
    first_y = shown[0][1]["centroid"][1]
    index, last = shown[-1]
    if last["centroid"][1] > first_y:
        return []
    return [_issue(check, f"무게중심이 안 올라갔다 (y {first_y:.1f} → {last['centroid'][1]:.1f})", frames[index].i)]


def _symmetric_x(check, frames, metrics):
    """무게중심 x 가 가운데서 얼마나 치우쳤나. 판정 장은 judged_frames."""
    shown, dropped, floor = _judged(metrics)
    if not shown:
        return []
    limit = float(check["args"].get("texels", 0))
    index, worst = max(shown, key=lambda pair: abs(pair[1]["centroid"][0]))
    offset = worst["centroid"][0]
    if abs(offset) <= limit:
        return []
    detail = f"무게중심 x 가 {offset:+.1f} 텍셀 치우쳤다 > {limit:g}{dropped_note(dropped, floor)}"
    return [_issue(check, detail, frames[index].i)]


RULES = {
    "last_frame_empty": _last_frame_empty,
    "first_frame_not_empty": _first_frame_not_empty,
    "coverage_max": _coverage_max,
    "max_luma": _max_luma,
    "centroid_rise_max": _centroid_rise_max,
    "centroid_rises": _centroid_rises,
    "symmetric_x": _symmetric_x,
}


def evaluate(checks, frames, metrics):
    """checks = template.frame_checks(...) 결과. 모르는 규칙은 info 로 알리고 넘어간다."""
    issues = []
    for check in checks:
        judge = RULES.get(check["rule"])
        if judge is None:
            detail = f"{check['template']} : 모르는 프레임 규칙 {check['rule']}"
            issues.append(report.issue("template.unknown_rule", "info", detail, layer=check.get("layer")))
            continue
        issues.extend(judge(check, frames, metrics))
    return issues
