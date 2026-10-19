"""템플릿 프레임 규칙(template.<규칙>) — 합성 바퀴(점 하나가 x -4 → +3 으로 움직임)로 잰다."""

import json
import shutil
from pathlib import Path

from vfxtool import measure, measure_rules, measure_template
from vfxtool.frames import Frame

DATA = Path(__file__).parent / "data" / "frames" / "round_1"
PROFILE = {"palette": ["#FFFFFF", "#3080FF"]}


def _round(tmp_path, layers):
    round_dir = tmp_path / "synth" / "round_1"
    shutil.copytree(DATA, round_dir)
    (round_dir / "recipe.json").write_text(json.dumps({"name": "synth", "layers": layers}), encoding="utf-8")
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps(PROFILE), encoding="utf-8")
    return round_dir, profile


def _template_issues(report):
    return {i["rule"]: i for i in report["issues"] if i["rule"].startswith("template.")}


def test_land_dust_symmetric_x_warns(tmp_path):
    round_dir, profile = _round(tmp_path, [{"name": "dust", "template": "land_dust"}])
    report = measure.measure(round_dir, profile)
    found = _template_issues(report)
    assert set(found) == {"template.symmetric_x"}  # y 는 그대로라 centroid_rise_max 는 통과
    assert found["template.symmetric_x"]["severity"] == "warn" and found["template.symmetric_x"]["frame"] == 1
    assert report["metrics"]["template_checks"] == ["land_dust.centroid_rise_max", "land_dust.symmetric_x"]


def test_hit_and_heal_rules(tmp_path):
    layers = [{"name": "hit", "template": "hit_sparks"}, {"name": "heal", "template": "heal_rise"}]
    round_dir, profile = _round(tmp_path, layers)
    found = _template_issues(measure.measure(round_dir, profile))
    assert set(found) == {"template.last_frame_empty", "template.centroid_rises", "template.max_luma"}
    assert found["template.max_luma"]["layer"] == "heal.glow"


def test_ambient_passes_and_no_recipe_means_no_checks(tmp_path):
    round_dir, profile = _round(tmp_path, [{"name": "motes", "template": "ambient_motes"}])
    report = measure.measure(round_dir, profile)
    assert _template_issues(report) == {}
    (round_dir / "recipe.json").unlink()
    assert measure.measure(round_dir, profile)["metrics"]["template_checks"] == []


def test_source_flag_overrides_round_recipe(tmp_path):
    round_dir, profile = _round(tmp_path, [{"name": "motes", "template": "ambient_motes"}])
    source = tmp_path / "other.json"
    source.write_text(json.dumps({"layers": [{"name": "hit", "template": "hit_sparks"}]}), encoding="utf-8")
    found = _template_issues(measure.measure(round_dir, profile, source_path=source))
    assert set(found) == {"template.last_frame_empty"}


def _metric(covered, y, x=0.0, cov=1.0, luma=0.5):
    return {"covered": covered, "centroid": [x, y] if covered else None, "coverage": cov, "max_luma": luma}


def test_evaluate_rising_and_rise_limit():
    frames = [Frame(i=k + 1, t=0.1 * k, rgba=None) for k in range(3)]
    metrics = [_metric(4, 0.0), _metric(4, 3.0), _metric(0, 0.0)]
    rises = {"rule": "centroid_rises", "args": {}, "template": "t", "layer": None}
    limit = {"rule": "centroid_rise_max", "args": {"texels": 2}, "template": "t", "layer": None}
    unknown = {"rule": "nope", "args": {}, "template": "t", "layer": None}
    issues = measure_template.evaluate([rises, limit, unknown], frames, metrics)
    assert [(i["rule"], i["severity"]) for i in issues] == [
        ("template.centroid_rise_max", "warn"), ("template.unknown_rule", "info")]
    assert issues[0]["frame"] == 2


def _centroid_checks():
    sym = {"rule": "symmetric_x", "args": {"texels": 2}, "template": "t", "layer": None}
    rise = {"rule": "centroid_rise_max", "args": {"texels": 2}, "template": "t", "layer": None}
    return [sym, rise]


def test_centroid_rules_skip_tail_frames_below_min_coverage():
    """꼬리 장(덮은 면적 0.5% 미만)만 치우치거나 올라가면 통과."""
    frames = [Frame(i=k + 1, t=0.1 * k, rgba=None) for k in range(4)]
    tail = measure_rules.MIN_JUDGED_COVERAGE - 0.3
    metrics = [_metric(40, 0.0), _metric(30, 0.5, x=0.5), _metric(1, 9.0, x=7.5, cov=tail), _metric(0, 0.0)]
    assert measure_template.evaluate(_centroid_checks(), frames, metrics) == []


def test_centroid_rules_warn_on_main_frames_and_count_dropped():
    """본장이 치우치거나 올라가면 warn, detail 에 뺀 장 수."""
    frames = [Frame(i=k + 1, t=0.1 * k, rgba=None) for k in range(3)]
    tail = measure_rules.MIN_JUDGED_COVERAGE - 0.3
    metrics = [_metric(40, 0.0), _metric(30, 5.0, x=4.0), _metric(1, 0.0, x=-7.0, cov=tail)]
    issues = measure_template.evaluate(_centroid_checks(), frames, metrics)
    assert [(i["rule"], i["frame"]) for i in issues] == [("template.symmetric_x", 2), ("template.centroid_rise_max", 2)]
    assert all("1장 뺌" in i["detail"] for i in issues)


def test_centroid_rules_skip_relative_tail_frames():
    """최대 덮은 면적이 크면 그 × MIN_JUDGED_SHARE 미만 꼬리 장(절대 문턱은 넘는 1.56%)도 빠져 통과."""
    frames = [Frame(i=k + 1, t=0.1 * k, rgba=None) for k in range(4)]
    tail = 1.56
    assert measure_rules.MIN_JUDGED_COVERAGE < tail < measure_rules.MIN_JUDGED_SHARE * 10.0
    metrics = [_metric(40, 0.0, cov=10.0), _metric(30, 0.5, x=0.5, cov=8.0), _metric(6, 9.0, x=3.1, cov=tail), _metric(0, 0.0)]
    assert measure_template.evaluate(_centroid_checks(), frames, metrics) == []


def test_centroid_rules_keep_even_sparse_frames_and_note_relative_floor():
    """장마다 면적이 고르게 작으면(1.56%) 상대 문턱이 안 빼서 warn 이 남고, 꼬리를 빼면 detail 에 쓴 문턱이 찍힌다."""
    frames = [Frame(i=k + 1, t=0.1 * k, rgba=None) for k in range(3)]
    even = [_metric(4, 0.0, cov=1.56), _metric(4, 5.0, x=4.0, cov=1.56), _metric(4, 0.0, cov=1.56)]
    issues = measure_template.evaluate(_centroid_checks(), frames, even)
    assert [(i["rule"], i["frame"]) for i in issues] == [("template.symmetric_x", 2), ("template.centroid_rise_max", 2)]
    assert all("뺌" not in i["detail"] for i in issues)
    with_tail = [_metric(40, 0.0, cov=10.0), _metric(30, 5.0, x=4.0, cov=8.0), _metric(6, 0.0, x=-7.0, cov=1.56)]
    issues = measure_template.evaluate(_centroid_checks(), frames, with_tail)
    assert [(i["rule"], i["frame"]) for i in issues] == [("template.symmetric_x", 2), ("template.centroid_rise_max", 2)]
    assert all("1장 뺌" in i["detail"] and "꼬리 2.50%" in i["detail"] for i in issues)


def _frames(count):
    return [Frame(i=k + 1, t=0.1 * k, rgba=None) for k in range(count)]


def test_head_frames_before_peak_keep_absolute_floor_only():
    """리뷰 1 : 처음 뿜는 작은 장(1%)은 최대 장 앞이라 상대 문턱으로 안 빠진다 — 상승 기준 · 초반 치우침을 지킨다."""
    rise = {"rule": "centroid_rise_max", "args": {"texels": 2}, "template": "t", "layer": None}
    metrics = [_metric(4, 0.0, cov=1.0), _metric(40, 3.0, cov=10.0), _metric(40, 4.0, cov=10.0)]
    issues = measure_template.evaluate([rise], _frames(3), metrics)
    assert [(i["rule"], i["frame"]) for i in issues] == [("template.centroid_rise_max", 3)]
    assert "4.0 텍셀" in issues[0]["detail"]
    sym = {"rule": "symmetric_x", "args": {"texels": 2}, "template": "t", "layer": None}
    skewed_head = [_metric(4, 0.0, x=3.0, cov=1.0), _metric(40, 0.0, cov=10.0), _metric(40, 0.0, cov=10.0)]
    assert [i["frame"] for i in measure_template.evaluate([sym], _frames(3), skewed_head)] == [1]


def test_all_frames_dropped_falls_back_to_every_nonempty_frame():
    """리뷰 2 : 장이 다 절대 문턱(0.5%) 아래면 안 빈 장 모두로 판정 — 조용히 통과하지 않는다."""
    metrics = [_metric(1, 0.0, x=5.0, cov=0.2), _metric(1, 5.0, x=5.0, cov=0.2), _metric(0, 0.0)]
    issues = measure_template.evaluate(_centroid_checks(), _frames(3), metrics)
    assert [i["rule"] for i in issues] == ["template.symmetric_x", "template.centroid_rise_max"]
    assert all("뺌" not in i["detail"] for i in issues)


def test_centroid_rises_uses_last_judged_frame():
    """리뷰 4 : 끝 꼬리 장(0.1%)이 아래로 처져도 끝 판정 장이 올라갔으면 통과."""
    rises = {"rule": "centroid_rises", "args": {}, "template": "t", "layer": None}
    metrics = [_metric(8, 0.0, cov=2.0), _metric(16, 3.0, cov=4.0), _metric(1, -5.0, cov=0.1)]
    assert measure_template.evaluate([rises], _frames(3), metrics) == []
    sinking = [_metric(8, 0.0, cov=2.0), _metric(16, -3.0, cov=4.0)]
    assert len(measure_template.evaluate([rises], _frames(2), sinking)) == 1


def test_dropped_note_is_shared_and_two_decimals():
    """리뷰 5 · 6 : 뺀 장 문구는 measure_rules 한 곳에서 나오고, 문턱은 실제 값을 소수 둘째 자리로 적는다."""
    assert measure_template.dropped_note is measure_rules.dropped_note
    assert measure_template.judged_frames is measure_rules.judged_frames
    note = measure_rules.dropped_note(1, 2.5075)
    assert "1장 뺌" in note and "2.51%" in note and "0.50%" in note
    assert measure_rules.dropped_note(0, 2.5) == ""
