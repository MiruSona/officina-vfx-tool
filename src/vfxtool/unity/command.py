"""`vfxtool build` · `vfxtool render` — 검사 → Unity 찾기 → 잠금 → job 쓰기 → 실행 → result.json 을 보고로 (설계 6-1).

Unity 찾기 · 잠금 · 경로 검사가 다 통과한 뒤에야 work 를 만들고 지난 판 결과를 지운다.
"""

import argparse
import shutil
from pathlib import Path

from vfxtool import report as reports
from vfxtool.errors import VfxError
from vfxtool.measure_rules import load_rule_hints
from vfxtool.paths import read_json
from vfxtool.unity import job as jobs
from vfxtool.unity.guard import positive_float, positive_int, texture_issues, work_path
from vfxtool.unity.lock import STALE, check_lock
from vfxtool.unity.locate import locate_unity
from vfxtool.unity.run import DEFAULT_TIMEOUT, build_args, log_issues, no_result_lines, run_unity

_RESULT_EXIT = {"ok": 0, "issues": 1, "error": 2}
_EXIT_STATUS = {0: "ok", 1: "fail", 2: "error"}


def add_build_parser(sub) -> argparse.ArgumentParser:
    """`commands/build.py` 가 add_parser 로 그대로 쓴다."""
    build = sub.add_parser("build", help="resolved.json 으로 프리팹을 만든다(Unity 배치)")
    _add_common(build, work_required=False)
    build.set_defaults(unity_mode="build")
    return build


def add_render_parser(sub) -> argparse.ArgumentParser:
    """`commands/render.py` 가 add_parser 로 그대로 쓴다."""
    render = sub.add_parser("render", help="resolved.json 을 프레임 PNG 로 뽑는다(Unity 배치)")
    _add_common(render, work_required=True)
    render.add_argument("--fps", type=positive_int, help="판정 fps (없으면 레시피 fps, 그것도 없으면 12)")
    render.add_argument("--backgrounds", help="배경 목록, 예 black,white (기본 transparent)")
    render.set_defaults(unity_mode="render")
    return render


def _add_common(parser: argparse.ArgumentParser, work_required: bool) -> None:
    parser.add_argument("resolved", help="check 가 만든 resolved.json")
    parser.add_argument("--project", required=True, help="Unity 프로젝트 폴더")
    parser.add_argument("--save-root", default=jobs.DEFAULT_SAVE_ROOT, help="프리팹 저장 자리(Assets/ 안)")
    parser.add_argument("--work", required=work_required, help="job · log · 프레임 자리(Unity 프로젝트 밖)")
    parser.add_argument("--input-root", help="texture 가 있어도 되는 폴더 (기본 : resolved.json 폴더)")
    parser.add_argument("--unity", help="Unity.exe 경로(또는 명령). 없으면 VFXTOOL_UNITY · ProjectVersion.txt")
    parser.add_argument("--timeout", type=positive_float, default=DEFAULT_TIMEOUT, help="초. 넘으면 끊고 종료 2")


def run(args: argparse.Namespace) -> int:
    """명령 하나를 끝까지 돌리고 보고 JSON 을 stdout 에 쓴다."""
    try:
        report = _execute(args)
    except VfxError as exc:
        report = _report(2, [_issue("unity.error", str(exc))], {})
    reports.emit(report)
    for item in report["issues"]:
        reports.say(f"[{item['severity']}] {item['rule']} : {item['detail']}")
    return reports.exit_code(report)


def execute(args: argparse.Namespace) -> dict:
    """보고 dict 만 돌려준다(stdout 에 안 씀). 고리(loop)가 바퀴마다 부른다. 실패는 VfxError."""
    return _execute(args)


def _execute(args: argparse.Namespace) -> dict:
    prepared = prepare(args)
    if "report" in prepared:
        return prepared["report"]
    try:
        code = run_unity(prepared["unity"], build_args(prepared["project"], prepared["log_file"], prepared["job_file"]),
                         args.timeout)
    except VfxError as exc:
        return unity_error(prepared, str(exc))
    return finish(prepared, code)


def prepare(args: argparse.Namespace) -> dict:
    """Unity 앞 토막 — 검사 · Unity 찾기 · 잠금 · job 쓰기 · 옛 결과 지우기 · resolved 사본.

    돌려주는 dict 를 finish 에 넘긴다. texture 경로가 틀리면 {"report": 보고} 하나만(Unity 를 안 띄운다).
    """
    mode = args.unity_mode
    resolved_path = Path(args.resolved).resolve()
    if not resolved_path.is_file():
        raise VfxError(f"resolved.json 이 없다 — {resolved_path}")
    resolved = read_json(resolved_path)

    project = Path(args.project).resolve()
    if not project.is_dir():
        raise VfxError(f"Unity 프로젝트 폴더가 없다 — {project}")
    work = work_path(args.work, resolved_path, project)
    path_issues = texture_issues(resolved, _input_root(args, resolved_path))
    if path_issues:
        return {"report": _report(1, path_issues, {"mode": mode})}

    frames, backgrounds = [], ["transparent"]
    metrics = {"mode": mode}
    if mode == "render":
        fps = _fps(args, resolved)
        frames = jobs.frame_times(resolved, fps)
        backgrounds = jobs.parse_backgrounds(args.backgrounds)
        metrics["truncated"] = jobs.frames_truncated(resolved, fps)
    unity = locate_unity(project, args.unity)
    lock_state = check_lock(project)

    work.mkdir(parents=True, exist_ok=True)
    _keep_resolved(resolved_path, work)
    out_dir, log_file, job_file = work / "frames", work / "unity.log", work / "job.json"
    jobs.write_job(job_file, jobs.make_job(resolved_path, mode, args.save_root, out_dir, frames, backgrounds))
    _clear_old_results(work, out_dir)

    metrics.update({"job": str(job_file), "lock": lock_state})
    issues = []
    if lock_state == STALE:
        issues.append(_issue("unity.stale_lock", "남은 Temp/UnityLockfile 을 무시하고 진행했다", "info"))
    return {"mode": mode, "unity": unity, "project": project, "work": work, "out_dir": out_dir,
            "job_file": job_file, "log_file": log_file, "metrics": metrics, "issues": issues,
            "resolved_loop": resolved.get("loop", False)}


def unity_error(prepared: dict, detail: str) -> dict:
    """Unity 를 못 띄웠거나 시간을 넘겼다 — 종료 2 보고."""
    issues = [_issue("unity.error", detail)] + prepared["issues"] + log_issues(prepared["log_file"])
    return _report(2, issues, prepared["metrics"])


def finish(prepared: dict, code: int, log_file: Path | None = None, span=None) -> dict:
    """Unity 뒤 토막 — result.json 을 보고로. 묶어 굽기는 묶음 로그와 그 판 토막(span)을 준다."""
    metrics = prepared["metrics"]
    metrics["exit_code"] = code
    if prepared["mode"] == "render" and not prepared["resolved_loop"]:
        metrics["t0_skipped"] = True
    return _merge_result(code, _find_result(prepared["work"], prepared["out_dir"]), prepared["issues"], metrics,
                         log_file or prepared["log_file"], span)


def _input_root(args: argparse.Namespace, resolved_path: Path) -> Path:
    root = getattr(args, "input_root", None)
    if root:
        return Path(root).resolve()
    return resolved_path.parent


def _merge_result(code: int, result_path: Path | None, issues: list, metrics: dict,
                  log_file: Path, span=None) -> dict:
    """result.json 의 status 와 프로세스 종료 코드 중 더 나쁜 쪽을 따른다."""
    if result_path is None:
        detail = f"Unity 가 result.json 을 안 남겼다(종료 {code})"
        lines = no_result_lines(log_file, span)
        if lines:
            detail += " — " + " | ".join(lines)
        issues = [_issue("unity.no_result", detail)]
        return _report(2, issues + log_issues(log_file, span), metrics)

    result = read_json(result_path)
    status = result.get("status")
    if status not in _RESULT_EXIT:
        issues.append(_issue("unity.result", f"result.json status 를 모른다 — {status!r}"))
        return _report(2, issues, metrics)

    exit_code = max(_RESULT_EXIT[status], _process_exit(code))
    rule_hints = load_rule_hints()
    issues += [_result_issue(item, rule_hints) for item in result.get("issues", [])]
    if exit_code != 0:
        issues += log_issues(log_file, span)

    metrics.update({
        "result": str(result_path),
        "unity": result.get("unity"),
        "prefab": result.get("prefab"),
        "frames": len(result.get("frames", [])),
        "renderApi": result.get("renderApi"),
        "graphicsDevice": result.get("graphicsDevice"),
        "seconds": result.get("seconds", {}),
    })
    return _report(exit_code, issues, metrics)


def has_result(prepared: dict) -> bool:
    """이번 Unity 가 이 판 result.json 을 남겼나(옛 결과는 prepare 가 지웠다)."""
    return _find_result(prepared["work"], prepared["out_dir"]) is not None


def _process_exit(code: int | None) -> int:
    if code is None:  # 묶어 굽기 — 묶음 종료 코드로는 판을 못 가른다, result status 만 믿는다(A4)
        return 0
    if code in (0, 1, 2):
        return code
    return 2


def _keep_resolved(resolved_path: Path, work: Path) -> None:
    """measure 가 --recipe 없이도 이 판 레시피를 읽게 work 에 resolved.json 사본을 둔다."""
    target = work / "resolved.json"
    if target.resolve() != resolved_path:
        shutil.copyfile(resolved_path, target)


def _fps(args: argparse.Namespace, resolved: dict) -> int:
    if args.fps is not None:
        return args.fps
    return int(resolved.get("fps", jobs.DEFAULT_FPS))


def _clear_old_results(work: Path, out_dir: Path) -> None:
    """지난 판 result.json · unity.log 를 이번 판 것으로 잘못 읽지 않게 지운다."""
    for folder in (out_dir, work):
        (folder / "result.json").unlink(missing_ok=True)
    (work / "unity.log").unlink(missing_ok=True)


def _find_result(work: Path, out_dir: Path) -> Path | None:
    """C# 은 job.json 옆(work)에, 가짜 Unity 는 outDir 에 쓴다. 둘 다 받는다."""
    for folder in (out_dir, work):
        candidate = folder / "result.json"
        if candidate.is_file():
            return candidate
    return None


def _issue(rule: str, detail: str, severity: str = "error") -> dict:
    return reports.issue(rule, severity, detail)


def _result_issue(item: dict, rule_hints: dict) -> dict:
    """result.json issue 하나를 보고 꼴로. C# 이 hint 를 안 주면 증상표의 rule_hints 로 채운다."""
    severity = item.get("severity", "error")
    if severity not in reports.SEVERITIES:
        severity = "error"
    rule = item.get("rule", "unity.issue")
    hint = item.get("hint")
    if not hint:
        hint = rule_hints.get(rule)
    return reports.issue(rule, severity, item.get("detail", ""),
                         layer=item.get("layer"), frame=item.get("frame"), hint=hint)


def _report(exit_code: int, issues: list, metrics: dict) -> dict:
    return {"status": _EXIT_STATUS[exit_code], "issues": issues, "metrics": metrics}
