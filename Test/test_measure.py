"""measure.py — 지표 값 · 묶음 규칙(한 장 = info, 연속 3장 · 비율 초과 = warn) · 증상 힌트 · 종료 코드."""
import argparse
import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from vfxtool import measure, measure_rules

DATA = Path(__file__).parent / "data" / "frames" / "round_1"
PROFILE = {"palette": ["#FFFFFF", "#3080FF"], "source": {"palette": "png"}}


def _setup(tmp_path, shifted=(), clear=False):
    """round_1 을 복사하고 shifted 프레임은 1px 밀고, clear 면 전부 투명으로 만든다."""
    round_dir = tmp_path / "synth_dots" / "round_1"
    shutil.copytree(DATA, round_dir)
    for i in range(1, 9):
        path = round_dir / "frames" / f"f{i:03d}.png"
        arr = np.asarray(Image.open(path).convert("RGBA")).copy()
        if i == 5:
            arr = np.roll(arr, -1, axis=1)  # 원본의 1px 어긋남을 되돌려 정렬
        if i in shifted:
            arr = np.roll(arr, 1, axis=1)
        if clear:
            arr[:] = 0
        Image.fromarray(arr, "RGBA").save(path)
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps(PROFILE), encoding="utf-8")
    return round_dir, profile


def _rules(report):
    return {i["rule"]: i for i in report["issues"]}


def test_metrics_on_synthetic_round(tmp_path):
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps(PROFILE), encoding="utf-8")
    report = measure.measure(DATA, profile)
    m = report["metrics"]
    assert m["frames"] == 8
    assert m["colors"] == [1] * 8
    assert m["colors_total"] == 2
    assert m["color_list"] == ["#F0A040", "#FFFFFF"]
    assert m["grid_ratio"] == [1.0, 1.0, 1.0, 1.0, 0.5, 1.0, 1.0, 1.0]
    assert m["palette_dist"][2] > 0
    assert [d for k, d in enumerate(m["palette_dist"]) if k != 2] == [0.0] * 7
    assert m["coverage"] == [pytest.approx(1.5625)] * 8
    assert m["centroid"] == [[float(i - 5), 0.0] for i in range(1, 9)]
    assert m["semi_alpha"] == [0] * 8
    assert m["alpha_sum"] == [4.0] * 8
    assert m["max_luma"][0] == pytest.approx(1.0)
    assert m["max_luma"][2] < 1.0
    assert m["particle_size"] == [2] * 8
    assert m["blobs"] == [1] * 8
    assert m["spread_x"] == [0.0] * 8
    assert m["lopsided_limit"] == measure_rules.LOPSIDED_TEXELS
    assert m["clipped"] == [False] * 8


def test_single_off_frames_are_info(tmp_path):
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps(PROFILE), encoding="utf-8")
    report = measure.measure(DATA, profile)
    rules = _rules(report)
    assert rules["frame.grid"]["severity"] == "info"
    assert rules["frame.grid"]["frame"] == 5
    assert rules["frame.palette"]["severity"] == "info"
    assert rules["frame.palette"]["frame"] == 3
    assert rules["frame.last_not_empty"]["severity"] == "warn"
    assert report["status"] == "warn"
    assert report["metrics"]["symptoms"] == ["lingers"]
    assert "main.startLifetime" in rules["frame.last_not_empty"]["hint"]
    assert "material" in rules["frame.grid"]["hint"]


def test_three_in_a_row_is_warn(tmp_path):
    round_dir, profile = _setup(tmp_path, shifted=(4, 5, 6))
    report = measure.measure(round_dir, profile)
    grid = _rules(report)["frame.grid"]
    assert grid["severity"] == "warn"
    assert "off_grid" in report["metrics"]["symptoms"]


def test_ratio_over_tolerance_is_warn(tmp_path):
    round_dir, profile = _setup(tmp_path, shifted=(1, 3, 5, 7, 8))
    grid = _rules(measure.measure(round_dir, profile))["frame.grid"]
    assert grid["severity"] == "warn"


def test_two_in_a_row_stays_info(tmp_path):
    round_dir, profile = _setup(tmp_path, shifted=(4, 5))
    assert _rules(measure.measure(round_dir, profile))["frame.grid"]["severity"] == "info"


def test_rotation_layer_caps_grid_at_info(tmp_path):
    round_dir, profile = _setup(tmp_path, shifted=(4, 5, 6))
    resolved = json.loads((round_dir / "resolved.json").read_text(encoding="utf-8"))
    resolved["layers"][0]["main"]["startRotation"] = {"random": [0, 360]}
    recipe = tmp_path / "resolved_rot.json"
    recipe.write_text(json.dumps(resolved), encoding="utf-8")
    report = measure.measure(round_dir, profile, recipe)
    assert _rules(report)["frame.grid"]["severity"] == "info"
    assert "off_grid" not in report["metrics"]["symptoms"]


def test_all_empty_is_fail_with_hint(tmp_path):
    round_dir, profile = _setup(tmp_path, clear=True)
    report = measure.measure(round_dir, profile)
    assert report["status"] == "fail"
    assert [i["rule"] for i in report["issues"]] == ["frame.all_empty"]
    assert report["metrics"]["symptoms"] == ["empty"]
    assert "emission" in report["issues"][0]["hint"]


def test_bundle_severity_rules():
    tol = {"ratio": 0.5, "run": 3}
    assert measure_rules.bundle_severity([False] * 8, 8, tol) is None
    assert measure_rules.bundle_severity([True] + [False] * 7, 8, tol) == "info"
    assert measure_rules.bundle_severity([False, True, True, True] + [False] * 4, 8, tol) == "warn"
    assert measure_rules.bundle_severity([True, False] * 4 + [True], 9, tol) == "warn"


def test_symptom_table_has_ten_rows():
    names = [s["name"] for s in measure_rules.load_symptoms()]
    assert len(names) == 10
    assert names[0] == "empty" and "jittery" in names


def _run(capsys, argv):
    parser = argparse.ArgumentParser()
    measure.add_parser(parser.add_subparsers(dest="command"))
    args = parser.parse_args(["measure"] + argv)
    code = measure.run(args)
    return code, json.loads(capsys.readouterr().out)


def test_cli_writes_measure_json(tmp_path, capsys):
    round_dir, profile = _setup(tmp_path)
    code, report = _run(capsys, [str(round_dir), "--profile", str(profile)])
    assert code == 0
    saved = json.loads((round_dir / "measure.json").read_text(encoding="utf-8"))
    assert saved == report


def test_cli_exit_codes(tmp_path, capsys):
    round_dir, profile = _setup(tmp_path, clear=True)
    code, _ = _run(capsys, [str(round_dir), "--profile", str(profile)])
    assert code == 1
    code, report = _run(capsys, [str(tmp_path / "nope"), "--profile", str(profile)])
    assert code == 2
    assert report["status"] == "error"


def test_empty_palette_is_error(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"palette": []}), encoding="utf-8")
    code, _ = _run(capsys, [str(DATA), "--profile", str(bad), "--out", str(tmp_path / "m.json")])
    assert code == 2


def test_sheet_layer_caps_pixel_size_at_info():
    from types import SimpleNamespace

    frames = [SimpleNamespace(i=i) for i in range(1, 9)]
    metrics = [{"grid_ratio": 1.0, "colors": [1], "palette_dist": 0, "particle_size": 5} for _ in frames]
    profile = {"seq_tolerance": {"ratio": 0.25, "run": 3}, "max_colors": 8, "snap": True, "pixel_size": [1, 2]}
    plain = measure_rules.layer_flags([{"name": "a", "main": {}}])
    sheet = measure_rules.layer_flags([{"name": "a", "main": {}}, {"name": "b", "textureSheet": {"tiles": [4, 1]}}])
    assert sheet["sheet"] is True and plain["sheet"] is False

    def severity(flags):
        found = {i["rule"]: i for i in measure_rules._bundle_issues(frames, metrics, profile, flags, 8)}
        return found["frame.pixel_size"]["severity"]

    assert severity(plain) == "warn"
    assert severity(sheet) == "info"


@pytest.mark.parametrize("dist, flagged", [(0.0, False), (3.74, False), (measure_rules.PALETTE_TOLERANCE, False), (4.5, True), (40.0, True)])
def test_palette_tolerance_absorbs_linear_vertex_rounding(dist, flagged):
    """Linear 색 공간 꼭짓점 색 반올림(#F2751A → #F2751C 등, 거리 ≤ 3.74)은 frame.palette 로 안 친다."""
    from types import SimpleNamespace

    frames = [SimpleNamespace(i=i) for i in range(1, 9)]
    metrics = [{"grid_ratio": 1.0, "colors": [1], "palette_dist": dist, "particle_size": 1} for _ in frames]
    profile = {"seq_tolerance": {"ratio": 0.25, "run": 3}, "max_colors": 8, "snap": True, "pixel_size": [1, 2]}
    flags = measure_rules.layer_flags([{"name": "a", "main": {}}])
    rules = {i["rule"] for i in measure_rules._bundle_issues(frames, metrics, profile, flags, 8)}
    assert ("frame.palette" in rules) is flagged


def _shape_metric(x, blobs, spread):
    return {"centroid": [x, 0.0], "covered": blobs * 4, "coverage": 1.0, "clipped": False,
            "blobs": blobs, "spread_x": spread, "semi_alpha": 0}


def _lopsided(metrics):
    from types import SimpleNamespace

    frames = [SimpleNamespace(i=i + 1) for i in range(len(metrics))]
    flags = {"additive": False, "lit": False, "rotation_or_size": False, "sheet": False}
    issues = measure_rules._shape_issues(frames, metrics, {"alpha_steps": "binary"}, flags)
    return [i for i in issues if i["rule"] == "frame.lopsided"]


def test_lopsided_forgives_sampling_noise_of_few_particles():
    # 입자 4개가 넓게(σ 12) 흩어진 판 — 평균 4 텍셀 치우침은 우연 폭(2 × 12/√4 = 12) 안이다.
    assert _lopsided([_shape_metric(4.0, 4, 12.0) for _ in range(5)]) == []


def test_lopsided_still_catches_real_bias():
    # 덩어리 하나가 오른쪽 6 텍셀 — 흩어짐이 거의 없어 고정 문턱 2 가 그대로 문턱이다.
    found = _lopsided([_shape_metric(6.0, 1, 0.5) for _ in range(5)])
    assert len(found) == 1 and "문턱 2.00" in found[0]["detail"]
    # 많은 입자가 모두 오른쪽으로 몰림(평균 10, 우연 폭 2 × 3/√16 = 1.5) → 잡는다.
    assert len(_lopsided([_shape_metric(10.0, 16, 3.0) for _ in range(5)])) == 1


def test_lopsided_limit_ignores_old_metrics_without_blobs():
    assert measure_rules.lopsided_limit([{"covered": 4, "centroid": [3.0, 0.0]}]) == measure_rules.LOPSIDED_TEXELS


def _blob_frame(spans, size=64):
    """한 장(scale 1). spans = [(x0, x1, y0, y1)] 칸을 흰색으로 덮는다."""
    rgba = np.zeros((size, size, 4), dtype=np.uint8)
    for x0, x1, y0, y1 in spans:
        rgba[y0:y1, x0:x1] = 255
    return rgba


def test_blob_centroid_spread_ignores_texel_spread_inside_one_blob():
    from vfxtool import measure_metrics as mm

    one = mm.frame_metrics(_blob_frame([(30, 50, 30, 34)]), 1, (64, 64), [(255, 255, 255)])
    assert one["blobs"] == 1 and one["spread_x"] == 0.0 and one["covered"] == 80
    two = mm.frame_metrics(_blob_frame([(10, 12, 30, 32), (50, 52, 30, 32)]), 1, (64, 64), [(255, 255, 255)])
    assert two["blobs"] == 2 and two["spread_x"] == pytest.approx(20.0)


def test_lopsided_catches_one_wide_blob_off_center():
    # 빛 · 빽빽한 먼지처럼 하나로 합쳐진 폭 20 덩어리가 +8 텍셀 — 덩어리 안 퍼짐에 문턱이 안 커진다.
    from vfxtool import measure_metrics as mm

    m = mm.frame_metrics(_blob_frame([(30, 50, 30, 34)]), 1, (64, 64), [(255, 255, 255)])
    assert m["centroid"][0] == pytest.approx(8.0)
    found = _lopsided([m] * 5)
    assert len(found) == 1 and "문턱 2.00" in found[0]["detail"]


def test_lopsided_limit_capped_by_canvas_width():
    # 32 텍셀 캔버스, 덩어리 둘이 x=+4 · +24 — 우연 폭 2 × 10/√2 = 14.1 이 캔버스 폭 1/4(8)로 깎여 쏠림을 잡는다.
    m = dict(_shape_metric(14.0, 2, 10.0), width=32)
    assert measure_rules.lopsided_limit([m] * 5) == pytest.approx(8.0)
    found = _lopsided([m] * 5)
    assert len(found) == 1 and found[0]["severity"] == "warn" and "문턱 8.00" in found[0]["detail"]
    # 폭 정보가 없는 옛 지표는 상한 없이 그대로.
    assert measure_rules.lopsided_limit([_shape_metric(14.0, 2, 10.0)] * 5) == pytest.approx(14.1421, abs=1e-3)


def _bright(flashes):
    """flashes = 장마다 흰 번쩍인가. additive 판의 frame.bright issue 목록."""
    from types import SimpleNamespace

    frames = [SimpleNamespace(i=i + 1) for i in range(len(flashes))]
    metrics = [dict(_shape_metric(0.0, 1, 0.5), bright_count=8 if on else 0) for on in flashes]
    flags = {"additive": True, "lit": False, "rotation_or_size": False, "sheet": False}
    issues = measure_rules._shape_issues(frames, metrics, {"alpha_steps": "binary"}, flags)
    return [i for i in issues if i["rule"] == "frame.bright"]


def test_bright_one_or_two_flash_frames_is_info():
    # 흰 번쩍 1~2장은 도트 관례(첫 장 번쩍) — info.
    for flashes in ([True, False, False, False], [True, True, False, False], [True, False, True, False]):
        found = _bright(flashes)
        assert len(found) == 1 and found[0]["severity"] == "info"


def test_bright_three_in_a_row_is_warn():
    found = _bright([False, True, True, True, False])
    assert len(found) == 1 and found[0]["severity"] == "warn" and "연속 최대 3 장" in found[0]["detail"]
    assert _bright([False, False, False]) == []


def test_lopsided_mean_skips_tail_frames():
    # hit_sparks 시드 9 꼴 : 본장은 −1 안팎인데 끝 장(0.1%, 덩어리 하나)이 −10 이라 평균을 문턱 밖으로 끈다 → 꼬리는 빼고 본다.
    main = [dict(_shape_metric(-1.0, 1, 0.0), coverage=2.0) for _ in range(4)]
    tail = dict(_shape_metric(-10.0, 1, 0.0), coverage=0.1)
    assert _lopsided(main + [tail]) == []
    # 본장이 치우치면 그대로 잡고, 뺀 꼬리 장 수를 detail 에 적는다.
    biased = [dict(_shape_metric(-4.0, 1, 0.0), coverage=2.0) for _ in range(4)]
    found = _lopsided(biased + [tail])
    assert len(found) == 1 and "1장 뺌" in found[0]["detail"]


def test_lopsided_keeps_all_frames_when_every_frame_is_tail():
    # 장이 다 절대 문턱(0.5%) 아래인 아주 성긴 판은 장을 안 빼고 그대로 판정한다(조용히 통과 금지).
    sparse = [dict(_shape_metric(6.0, 1, 0.0), coverage=0.2) for _ in range(5)]
    found = _lopsided(sparse)
    assert len(found) == 1 and "뺌" not in found[0]["detail"]


def test_lopsided_limit_uses_same_judged_frames_as_mean():
    # 리뷰 3 : 꼬리 장(0.1%) 하나가 덩어리 4개 · 흩어짐 40 이라 우연 폭을 키우던 판 — 문턱도 판정 장으로만 잰다.
    main = [dict(_shape_metric(-3.0, 1, 0.0), coverage=2.0) for _ in range(4)]
    tail = dict(_shape_metric(0.0, 4, 40.0), coverage=0.1)
    assert measure_rules.lopsided_limit(main + [tail]) == measure_rules.LOPSIDED_TEXELS
    found = _lopsided(main + [tail])
    assert len(found) == 1 and "문턱 2.00" in found[0]["detail"] and "1장 뺌" in found[0]["detail"]


def test_lopsided_keeps_head_frame_before_peak():
    # 리뷰 1 (lopsided) : 최대 장 앞의 작은 머리 장(1%)은 상대 문턱으로 안 빠진다.
    head = dict(_shape_metric(-9.0, 1, 0.0), coverage=1.0)
    rest = [dict(_shape_metric(-1.0, 1, 0.0), coverage=10.0) for _ in range(2)]
    judged, dropped, _ = measure_rules.judged_frames([head] + rest)
    assert judged == [0, 1, 2] and dropped == 0
    assert len(_lopsided([head] + rest)) == 1  # 평균 (−9 −1 −1)/3 = −3.67 > 2
