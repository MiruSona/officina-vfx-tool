"""`vfxtool measure` — 바퀴 폴더 프레임을 재서 measure.json 을 쓴다(설계 8-2 · 7-2).

지표 계산은 measure_metrics, 규칙 · 증상은 measure_rules 가 맡는다.
"""

from pathlib import Path

from vfxtool import frames as frames_mod
from vfxtool import measure_metrics as mm
from vfxtool import measure_rules as rules
from vfxtool import measure_template
from vfxtool import template as template_mod
from vfxtool import report as report_mod
from vfxtool.errors import VfxError
from vfxtool.paths import read_json, write_json
from vfxtool.recipe.profile_view import load_profile
from vfxtool.unity.job import MAX_FRAMES

def allowed_colors(profile):
    try:
        return [mm.parse_hex(c) for c in list(profile["palette"]) + list(profile["fx_extra"])]
    except ValueError as exc:
        raise VfxError(f"프로필 색이 hex 가 아니다 — {exc}") from exc


def _hex(rgb):
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def _nonempty_mean(metrics, key):
    """안 빈 장들의 key 평균(소수 넷째 자리). 다 비었으면 0. 값이 None(판정 불가)이면 None."""
    if any(m.get(key, 0.0) is None for m in metrics):
        return None
    picked = [m.get(key, 0.0) for m in metrics if m["covered"] > 0]
    if not picked:
        return 0.0
    return round(sum(picked) / len(picked), 4)


def _metrics_block(metrics, lopsided):
    all_colors = set()
    for m in metrics:
        all_colors |= m["colors"]
    return {
        "frames": len(metrics),
        "colors": [len(m["colors"]) for m in metrics],
        "colors_total": len(all_colors),
        "color_list": sorted(_hex(c) for c in all_colors),
        "grid_ratio": [round(m["grid_ratio"], 4) for m in metrics],
        "palette_dist": [round(m["palette_dist"], 3) for m in metrics],
        # 팔레트 밖 칸 비율(장마다)과 안 빈 장 평균 — 실험 2 의 additive 관문(평균 ≤ 0.02)이 이 값을 본다.
        # 허용 색이 비면 장마다 None(판정 불가) · measure.no_palette info.
        "palette_out": [_round_or_none(m.get("palette_out", 0.0), 4) for m in metrics],
        "palette_out_mean": _nonempty_mean(metrics, "palette_out"),
        # 덮은 텍셀 수가 오르내림을 바꾼 횟수 — 보고만 한다(규칙 없음, 실험 3).
        "flicker": mm.flicker([m["covered"] for m in metrics]),
        "semi_alpha": [m["semi_alpha"] for m in metrics],
        "alpha_sum": [round(m["alpha_sum"], 3) for m in metrics],
        "coverage": [round(m["coverage"], 4) for m in metrics],
        "centroid": [m["centroid"] for m in metrics],
        "max_luma": [round(m["max_luma"], 4) for m in metrics],
        "bright_count": [m["bright_count"] for m in metrics],
        "particle_size": [m["particle_size"] for m in metrics],
        "blobs": [m["blobs"] for m in metrics],
        "spread_x": [m["spread_x"] for m in metrics],
        # frame.lopsided 가 쓴 문턱(텍셀) — critic · patch 가 걸림 · 안 걸림 까닭을 본다.
        "lopsided_limit": round(lopsided, 4),
        "clipped": [m["clipped"] for m in metrics],
    }


def _round_or_none(value, digits):
    if value is None:
        return None
    return round(value, digits)


def _template_checks(round_dir, source_path, template_dirs):
    """템플릿 프레임 규칙. 펼치기 전 레시피(--source, 없으면 바퀴 폴더 recipe.json)에서 읽는다."""
    path = Path(round_dir) / "recipe.json"
    if source_path is not None:
        path = Path(source_path)
        if not path.is_file():
            raise VfxError(f"--source 레시피가 없다 — {path}")
    if not path.is_file():
        return []
    source = read_json(path)
    if not isinstance(source, dict) or not isinstance(source.get("layers"), list):
        return []
    return template_mod.frame_checks(source, template_dirs)


def measure(round_dir, profile_path, recipe_path=None, use_bw=False, source_path=None, template_dirs=()):
    """바퀴 폴더를 재서 보고 dict 를 돌려준다(파일은 안 씀)."""
    profile = load_profile(profile_path)
    allowed = allowed_colors(profile)
    result = frames_mod.load_result(round_dir)
    resolved = frames_mod.load_resolved(round_dir, recipe_path)
    info = frames_mod.load_round(round_dir, result, resolved)
    frames = frames_mod.load_frames(round_dir, result, use_bw, frames_mod.expected_size(info))
    metrics = [mm.frame_metrics(f.rgba, info.scale, info.texels, allowed) for f in frames]
    truncated = not info.loop and len(frames) >= MAX_FRAMES
    lopsided = rules.lopsided_limit(metrics)
    issues = rules.evaluate(frames, metrics, profile, info.layers, info.loop, truncated, lopsided)
    if not allowed:
        detail = "프로필 palette · fx_extra 가 비었다 — 팔레트 밖 판정(palette_out · frame.palette)을 못 한다"
        issues.append(report_mod.issue("measure.no_palette", "info", detail, hint=["profile.palette"]))
    checks = _template_checks(round_dir, source_path, template_dirs)
    if any(m["covered"] > 0 for m in metrics):
        # 전부 빈 판은 all_empty 하나로 충분하다 — 템플릿 규칙은 건너뛴다.
        issues += measure_template.evaluate(checks, frames, metrics)
    block = _metrics_block(metrics, lopsided)
    block["symptoms"] = rules.attach_symptoms(issues, rules.load_symptoms())
    block["frame_index"] = [f.i for f in frames]
    block["frame_t"] = [round(f.t, 4) for f in frames]
    block["template_checks"] = [f"{c['template']}.{c['rule']}" for c in checks]
    block["truncated"] = truncated
    return report_mod.build(issues, block)


def add_parser(sub):
    parser = sub.add_parser("measure", help="바퀴 폴더 프레임을 재서 measure.json 을 쓴다")
    parser.add_argument("round_dir", help="round_N 폴더(result.json · frames/)")
    parser.add_argument("--profile", required=True, help="VFX 프로필 profile.json")
    parser.add_argument("--recipe", help="resolved.json (없으면 바퀴 폴더의 resolved.json)")
    parser.add_argument("--bw", action="store_true", help="흑백 짝 f###_k/_w 가 있으면 알파를 복원해 잰다")
    parser.add_argument("--out", help="measure.json 자리 (기본 <round_dir>/measure.json)")
    parser.add_argument("--source", help="템플릿 프레임 규칙을 읽을 펼치기 전 레시피 (기본 <round_dir>/recipe.json)")
    parser.add_argument("--templates", action="append", default=[], help="게임 쪽 템플릿 폴더 (여러 번)")
    return parser


def run(args):
    """종료 코드 : 0 ok · warn / 1 fail / 2 error."""
    try:
        report = measure(args.round_dir, args.profile, args.recipe, args.bw, args.source, args.templates)
    except VfxError as exc:
        report_mod.emit(report_mod.error_report(str(exc)))
        return 2
    out = Path(args.round_dir) / "measure.json"
    if args.out:
        out = Path(args.out)
    write_json(out, report)
    report_mod.emit(report)
    errors = sum(1 for i in report["issues"] if i["severity"] == "error")
    warns = sum(1 for i in report["issues"] if i["severity"] == "warn")
    report_mod.say(f"measure {report['status']} — error {errors} · warn {warns} · {out}")
    return report_mod.exit_code(report)
