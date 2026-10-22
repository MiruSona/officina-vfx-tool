"""변형 묶음 돌리기 — expanded 판을 이름 순으로 굽는다(변형묶음설계 6-4 · 7절 · D1 · 묶어굽기설계 4절).

판 폴더가 곧 고리 바퀴 폴더다(recipe.json · profile.json 사본 · tex/).
기본은 묶음 : 판마다 준비(check · job.json) → Unity 한 번(-vfxJobs) → 판마다 마무리(measure · sheet · gif).
--each 면 옛 동작 : 판마다 Unity 를 따로 띄워 고리 한 바퀴(run_pipeline)에 넣는다.
한 판이 실패해도 다음 판을 이어 하고, 판 하나 끝날 때마다 set.json 을 원자 쓰기(write_json)로 갱신한다 — 끊겨도 다시 부르면 남은 판부터.
"""

import time
from pathlib import Path

from vfxtool import report
from vfxtool.errors import VfxError
from vfxtool.loop_pipeline import RoundOutcome, finish_round, prepare_round, render_args, run_pipeline, unity_failed
from vfxtool.paths import ensure_inside, read_json, write_json
from vfxtool.unity import command as unity_command
from vfxtool.unity.job import DEFAULT_SAVE_ROOT, normalize_save_root, write_job_list
from vfxtool.unity.lock import check_lock
from vfxtool.unity.locate import locate_unity
from vfxtool.unity.run import (DEFAULT_TIMEOUT, TAIL, build_args, job_spans, list_error, log_issues, no_result_lines,
                               path_key, run_unity)
from vfxtool.variant_set import PROFILE_FILE, RECIPE_FILE, SET_FILE, ledger_entries, locked, read_ledger

STARTUP_HEAVY = 0.5   # --each 에서 Unity 밖 시간이 절반을 넘으면 묶어 굽기가 값어치 있다(D1)
BATCH_BASE = 60       # 묶음 상한 = 기동 한 번 60초 + 판당 20초(묶어굽기설계 A9, 초안 — 실측 뒤 고친다)
BATCH_PER_JOB = 20
JOBS_FILE = "jobs.json"
BATCH_LOGS = ("unity.log", "unity_retry.log")   # 첫 판 · 재시도 판 묶음 로그


def find_set_dir(work):
    """set.json 이 있는 묶음 폴더."""
    root = Path(work).resolve()
    if not (root / SET_FILE).is_file():
        raise VfxError(f"{SET_FILE} 이 없다 — {root} (먼저 variant expand, --work 는 묶음 폴더)")
    return root


def run_set(work, project, only=(), unity=None, timeout=None, save_root=DEFAULT_SAVE_ROOT, each=False):
    """expanded 판을 돌린다. (set.json 경로, 장부, 이번 판 issues). 인자 · 폴더 · 환경 오류는 VfxError(종료 2).

    timeout None 이면 --each 는 판 하나 300초, 묶음은 60 + 판 수 × 20초. 값을 주면 Unity 프로세스 하나의 상한(A15).
    """
    set_dir = find_set_dir(work)
    project_dir = Path(project).resolve()
    if not project_dir.is_dir():
        raise VfxError(f"Unity 프로젝트 폴더가 없다 — {project_dir}")
    if set_dir.is_relative_to(project_dir):
        raise VfxError(f"--work 는 Unity 프로젝트 밖이어야 한다 — {set_dir}")
    normalize_save_root(save_root)
    ledger_path = set_dir / SET_FILE
    with locked(set_dir):
        ledger = read_ledger(set_dir)
        entries = ledger_entries(ledger)
        targets, issues = pick_targets(entries, only)
        if targets:
            preflight(project_dir, unity)
        settings_base = {
            "templates": list((ledger.get("settings") or {}).get("templates") or []),
            "project": project_dir.as_posix(), "save_root": save_root, "unity": unity,
            "timeout": DEFAULT_TIMEOUT if timeout is None else timeout,
        }
        if targets and each:
            ledger["run"] = {"mode": "each"}
            for entry in targets:
                run_one(set_dir, entry, settings_base)
                write_json(ledger_path, ledger)
        elif targets:
            run_batch(set_dir, targets, settings_base, ledger, timeout)
    return ledger_path, ledger, issues


def pick_targets(entries, only):
    """돌릴 판(이름 순)과 info issue. --only 에 모르는 이름이면 VfxError, expanded 가 아닌 판은 건너뛴다."""
    names = {entry["name"] for entry in entries}
    wanted = []
    for item in only:
        wanted += [part.strip() for part in item.split(",") if part.strip()]
    unknown = sorted(set(wanted) - names)
    if unknown:
        raise VfxError(f"--only 에 모르는 판 이름 : {unknown}")
    issues = []
    picked = []
    for entry in sorted(entries, key=lambda e: e["name"]):
        if wanted and entry["name"] not in wanted:
            continue
        if entry["state"] != "expanded":
            if wanted:
                issues.append(report.issue("variant.skipped", "info", f"{entry['name']} 는 {entry['state']} 라 건너뛴다"))
            continue
        picked.append(entry)
    return picked, issues


def preflight(project_dir, unity):
    """Unity 를 못 찾거나 같은 프로젝트를 연 에디터가 있으면 판을 하나도 안 돌리고 종료 2."""
    locate_unity(project_dir, unity)
    check_lock(project_dir)


def _variant_settings(set_dir, entry, settings_base, missing_wall):
    """판 폴더와 그 판 고리 설정. recipe.json 이 없으면 (폴더, None) — 판 wall 은 missing_wall(묶음은 None)."""
    folder = ensure_inside(set_dir / entry["name"], set_dir)
    if not (folder / RECIPE_FILE).is_file():
        _mark_failed(entry, [], f"{entry['name']}/{RECIPE_FILE} 이 없다 — variant expand --force 로 다시 펼친다", missing_wall)
        return folder, None
    settings = dict(settings_base)
    settings.update({
        "source_dir": folder.as_posix(), "profile": (folder / PROFILE_FILE).as_posix(),
        "profile_override": False, "input_root": folder.as_posix(),
    })
    return folder, settings


def run_one(set_dir, entry, settings_base):
    """--each : 판 하나를 Unity 따로 띄워 돌리고 장부 칸을 고친다."""
    folder, settings = _variant_settings(set_dir, entry, settings_base, 0.0)
    if settings is None:
        return
    started = time.perf_counter()
    try:
        outcome = run_pipeline(folder, settings)
    except VfxError as exc:
        _mark_failed(entry, [], exc.message, time.perf_counter() - started)
        return
    except Exception as exc:  # 반쯤 쓴 PNG 같은 뜻밖의 오류도 이 판만 failed — 다음 판 · set.json 은 이어 간다
        _mark_failed(entry, [], f"{type(exc).__name__}: {exc}", time.perf_counter() - started)
        return
    finish_one(entry, folder, outcome, time.perf_counter() - started)


def finish_one(entry, folder, outcome, wall):
    """한 바퀴 결과로 장부 칸을 고친다. 성공 → done, 실패 → failed + variant.run issue. 묶음은 wall None(A16)."""
    entry["errors"] = sum(1 for item in outcome.ranked if item["severity"] == "error")
    entry["warns"] = sum(1 for item in outcome.ranked if item["severity"] == "warn")
    entry["seconds"] = _seconds(folder, wall)
    if outcome.failed:
        rules = sorted({item["rule"] for item in outcome.issues if item["severity"] == "error"})
        _mark_failed(entry, outcome.issues, f"돌리기 실패 : {', '.join(rules) or '까닭 모름'}", wall)
        entry["seconds"] = _seconds(folder, wall)
        return
    entry["state"] = "done"
    entry["issues"] = outcome.issues


# ── 묶음 경로 (묶어굽기설계 4-1) ──

def run_batch(set_dir, targets, settings_base, ledger, timeout):
    """① 판마다 준비 → ② Unity 한 번 → ③ result 없는 판만 한 번 더 → ④ 판마다 마무리. 판마다 set.json 을 쓴다."""
    ledger_path = set_dir / SET_FILE
    started = time.perf_counter()
    for name in BATCH_LOGS:  # 지난 판 재시도 로그를 이번 것으로 잘못 읽지 않게
        (set_dir / name).unlink(missing_ok=True)
    pending = []
    for entry in targets:
        item = _prepare_one(set_dir, entry, settings_base)
        if item is None:
            write_json(ledger_path, ledger)
        else:
            pending.append(item)
    sent = [item["entry"]["name"] for item in pending]

    unity_wall, codes, retries = 0.0, [], 0
    for attempt, log_name in enumerate(BATCH_LOGS):
        if not pending:
            break
        if attempt:
            retries += 1
            # 첫 빈 판은 Unity 를 죽인 판일 가능성이 크다 — 맨 뒤로 보내 또 죽어도 그 판만 잃게(설계 9-1 대안 1)
            pending = pending[1:] + pending[:1]
        log_file = set_dir / log_name
        jobs_file = write_job_list(set_dir / JOBS_FILE, [item["prepared"]["job_file"] for item in pending])
        first = pending[0]["prepared"]
        limit = timeout if timeout is not None else BATCH_BASE + BATCH_PER_JOB * len(pending)
        unity_started = time.perf_counter()
        try:
            codes.append(str(run_unity(first["unity"], build_args(first["project"], log_file, jobs_file=jobs_file), limit)))
        except VfxError as exc:  # 시간 넘김 · 못 띄움 — 결과 없는 판은 재시도로
            codes.append(exc.message)
        unity_wall += time.perf_counter() - unity_started
        refused = list_error(log_file)
        if refused is not None:  # 목록 오류는 다시 돌려도 같다 — 판은 expanded 그대로, 종료 2(A14)
            raise VfxError(f"Unity 가 묶음 목록을 거절했다 — {refused} ({log_file})")
        spans = job_spans(log_file)
        missing = []
        for item in pending:
            if unity_command.has_result(item["prepared"]):
                _finish_batch_one(item, log_file, spans)
                write_json(ledger_path, ledger)
            else:
                missing.append(item)
        if not missing:
            break
        why = _no_retry_reason(attempt, log_file, first["project"])
        if why is not None:
            tail = no_result_lines(log_file, spans[TAIL])
            issues = log_issues(log_file, spans[TAIL])
            for item in missing:
                _mark_lost(item["entry"], f"{why}(종료 {' · '.join(codes)})", tail, issues)
                write_json(ledger_path, ledger)
            break
        pending = missing

    ledger["run"] = {"mode": "batch", "wall": round(time.perf_counter() - started, 3),
                     "unity_wall": round(unity_wall, 3), "retries": retries, "variants": sent}
    write_json(ledger_path, ledger)


def _no_retry_reason(attempt, log_file, project):
    """빈 판을 다시 안 돌릴 까닭. 다시 돌려도 되면 None."""
    if attempt == len(BATCH_LOGS) - 1:
        return "Unity 가 두 번 다 이 판 result.json 을 안 남겼다"
    if any("error CS" in item["detail"] for item in log_issues(log_file)):  # 컴파일 오류는 다시 돌려도 같다(A14 처럼)
        return "스크립트 컴파일 오류라 다시 안 돌렸다"
    try:
        check_lock(project)
    except VfxError as exc:
        return f"재시도 전 잠금 검사에 막혀 다시 안 돌렸다 — {exc.message} "
    return None


def _prepare_one(set_dir, entry, settings_base):
    """판 하나 준비. 굽기 목록에 넣을 {entry, folder, settings, checked, prepared}, 여기서 떨어지면 장부를 고치고 None."""
    folder, settings = _variant_settings(set_dir, entry, settings_base, None)
    if settings is None:
        return None
    try:
        checked, resolved_path = prepare_round(folder, settings)
        if resolved_path is None:
            finish_one(entry, folder, RoundOutcome(checked, checked, True), None)
            return None
        try:
            prepared = unity_command.prepare(render_args(folder, resolved_path, settings))
        except VfxError as exc:
            finish_one(entry, folder, unity_failed(checked, exc), None)
            return None
        if "report" in prepared:  # texture 경로 틀림 — Unity 를 안 띄우고 그 보고로 마무리
            finish_one(entry, folder, finish_round(folder, settings, checked, prepared["report"]), None)
            return None
    except VfxError as exc:
        _mark_failed(entry, [], exc.message, None)
        return None
    except Exception as exc:  # run_one 과 같은 까닭 — 이 판만 failed
        _mark_failed(entry, [], f"{type(exc).__name__}: {exc}", None)
        return None
    return {"entry": entry, "folder": folder, "settings": settings, "checked": checked, "prepared": prepared}


def _finish_batch_one(item, log_file, spans):
    """result.json 이 있는 판의 마무리. 판 issue 에는 묶음 로그 중 그 판 토막만 붙인다(A5)."""
    entry, folder = item["entry"], item["folder"]
    span = spans.get(path_key(folder))
    try:
        # 종료 코드는 묶음 전체의 최댓값이라 판을 못 가른다 — None 을 줘 판별 result status 만 믿는다(A4)
        rendered = unity_command.finish(item["prepared"], None, log_file, span or (0, 0))  # 토막이 없으면 아무 줄도 안 붙인다
        outcome = finish_round(folder, item["settings"], item["checked"], rendered)
    except VfxError as exc:
        _mark_failed(entry, [], exc.message, None)
    except Exception as exc:  # run_one 과 같은 까닭 — 이 판만 failed
        _mark_failed(entry, [], f"{type(exc).__name__}: {exc}", None)
    else:
        finish_one(entry, folder, outcome, None)
    if span is None:
        entry["issues"].append(report.issue("variant.log_span", "info", f"묶음 로그 토막 못 찾음 — {log_file.name} 줄을 안 붙였다"))


def _mark_lost(entry, detail, tail, issues):
    """result.json 이 끝내 없다 — Unity 가 이 판에서(또는 앞에서) 죽었다. issues 는 죽은 토막의 로그 오류 줄."""
    if tail:
        detail += " — " + " | ".join(tail)
    _mark_failed(entry, issues, detail, None, "variant.unity_lost")


def _mark_failed(entry, issues, detail, wall, rule="variant.run"):
    entry["state"] = "failed"
    entry["issues"] = [report.issue(rule, "error", detail)] + list(issues)
    entry["errors"] = max(1, entry.get("errors") or 0)
    entry["seconds"] = {"wall": _round(wall), "unity_build": None, "unity_render": None}


def _round(wall):
    if wall is None:
        return None
    return round(wall, 3)


def _seconds(folder, wall):
    """판 시간 — 벽시계와 result.json seconds(build · render, C# 이 잰 Unity 안 시간)."""
    inside = {}
    result_path = folder / "result.json"
    if result_path.is_file():
        try:
            inside = read_json(result_path)
        except VfxError:
            inside = {}
    inside = inside.get("seconds") if isinstance(inside, dict) else None
    if not isinstance(inside, dict):
        inside = {}
    return {"wall": _round(wall), "unity_build": inside.get("build"), "unity_render": inside.get("render")}


def timing(entries, run=None):
    """done 판 중 Unity 안 시간(build · render)이 하나라도 있는 판의 시간 합. 그런 판이 없으면 None.

    startup_ratio = 1 − (Unity 안 build + render 합 ÷ 벽시계) — Unity 기동 · 가져오기 · measure 등 밖 시간의 몫.
    벽시계는 --each 면 판 wall 합, 묶음(run mode batch)이면 묶음 한 번(묶어굽기설계 5-1). 묶음은 그 판에 든 판만 센다.
    """
    batch = isinstance(run, dict) and run.get("mode") == "batch"
    if batch:
        names = set(run.get("variants") or [])
        entries = [entry for entry in entries if entry.get("name") in names]
    rows = [entry["seconds"] for entry in entries if entry.get("state") == "done" and _measured(entry.get("seconds"))]
    if not rows:
        return None
    inside = sum((row.get("unity_build") or 0.0) + (row.get("unity_render") or 0.0) for row in rows)
    if batch:
        wall = run.get("wall") or 0.0
    else:
        wall = sum(row.get("wall") or 0.0 for row in rows)
    ratio = None
    if wall > 0:
        ratio = round(1.0 - inside / wall, 3)
    return {"wall_total": round(wall, 3), "unity_inside": round(inside, 3),
            "unity_wall": run.get("unity_wall") if batch else None,
            "per_variant_mean": round(wall / len(rows), 3),
            "mode": "batch" if batch else "each", "retries": run.get("retries", 0) if batch else 0,
            "startup_ratio": ratio, "measured": len(rows)}


def _measured(seconds):
    return isinstance(seconds, dict) and (seconds.get("unity_build") is not None or seconds.get("unity_render") is not None)


def timing_issues(summary):
    """--each 에서만 낸다 — 「묶어 굽기를 하라」는 뜻이라 이미 묶음이면 안 낸다(묶어굽기설계 A19)."""
    if summary is None or summary.get("mode") == "batch":
        return []
    if summary["startup_ratio"] is None or summary["startup_ratio"] <= STARTUP_HEAVY:
        return []
    detail = (f"startup_ratio {summary['startup_ratio']} — 벽시계의 대부분이 Unity 밖(기동 등)이다. "
              f"묶어 굽기(--each 빼기)가 값어치 있다")
    return [report.issue("variant.startup_heavy", "info", detail)]
