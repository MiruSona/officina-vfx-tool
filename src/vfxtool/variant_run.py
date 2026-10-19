"""변형 묶음 돌리기 — expanded 판을 이름 순으로 하나씩 고리 한 바퀴(run_pipeline)에 넣는다(변형묶음설계 6-4 · 7절 · D1).

판 폴더가 곧 고리 바퀴 폴더다(recipe.json · profile.json 사본 · tex/). Unity 는 판마다 따로 띄우고 한 판씩 순차로 돈다.
한 판이 실패해도 다음 판을 이어 하고, 판 하나 끝날 때마다 set.json 을 원자 쓰기(write_json)로 갱신한다 — 끊겨도 다시 부르면 남은 판부터.
"""

import time
from pathlib import Path

from vfxtool import report
from vfxtool.errors import VfxError
from vfxtool.loop_pipeline import run_pipeline
from vfxtool.paths import ensure_inside, read_json, write_json
from vfxtool.unity.job import DEFAULT_SAVE_ROOT, normalize_save_root
from vfxtool.unity.lock import check_lock
from vfxtool.unity.locate import locate_unity
from vfxtool.unity.run import DEFAULT_TIMEOUT
from vfxtool.variant_set import PROFILE_FILE, RECIPE_FILE, SET_FILE, ledger_entries, locked, read_ledger

STARTUP_HEAVY = 0.5   # Unity 밖 시간이 절반을 넘으면 「묶어 돌리기(2차)」가 값어치 있다(D1)


def find_set_dir(work):
    """set.json 이 있는 묶음 폴더."""
    root = Path(work).resolve()
    if not (root / SET_FILE).is_file():
        raise VfxError(f"{SET_FILE} 이 없다 — {root} (먼저 variant expand, --work 는 묶음 폴더)")
    return root


def run_set(work, project, only=(), unity=None, timeout=DEFAULT_TIMEOUT, save_root=DEFAULT_SAVE_ROOT):
    """expanded 판을 돌린다. (set.json 경로, 장부, 이번 판 issues). 인자 · 폴더 · 환경 오류는 VfxError(종료 2)."""
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
            "project": project_dir.as_posix(), "save_root": save_root, "unity": unity, "timeout": timeout,
        }
        for entry in targets:
            run_one(set_dir, entry, settings_base)
            write_json(ledger_path, ledger)
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


def run_one(set_dir, entry, settings_base):
    """판 하나를 돌려 장부 칸을 고친다. 성공 → done, 실패 → failed + variant.run issue."""
    folder = ensure_inside(set_dir / entry["name"], set_dir)
    if not (folder / RECIPE_FILE).is_file():
        _mark_failed(entry, [], f"{entry['name']}/{RECIPE_FILE} 이 없다 — variant expand --force 로 다시 펼친다", 0.0)
        return
    settings = dict(settings_base)
    settings.update({
        "source_dir": folder.as_posix(), "profile": (folder / PROFILE_FILE).as_posix(),
        "profile_override": False, "input_root": folder.as_posix(),
    })
    started = time.perf_counter()
    try:
        outcome = run_pipeline(folder, settings)
    except VfxError as exc:
        _mark_failed(entry, [], exc.message, time.perf_counter() - started)
        return
    except Exception as exc:  # 반쯤 쓴 PNG 같은 뜻밖의 오류도 이 판만 failed — 다음 판 · set.json 은 이어 간다
        _mark_failed(entry, [], f"{type(exc).__name__}: {exc}", time.perf_counter() - started)
        return
    wall = time.perf_counter() - started
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


def _mark_failed(entry, issues, detail, wall):
    entry["state"] = "failed"
    entry["issues"] = [report.issue("variant.run", "error", detail)] + list(issues)
    entry["errors"] = max(1, entry.get("errors") or 0)
    entry["seconds"] = {"wall": round(wall, 3), "unity_build": None, "unity_render": None}


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
    return {"wall": round(wall, 3), "unity_build": inside.get("build"), "unity_render": inside.get("render")}


def timing(entries):
    """done 판 중 Unity 안 시간(build · render)이 하나라도 있는 판의 시간 합. 그런 판이 없으면 None.

    startup_ratio = 1 − (Unity 안 build + render 합 ÷ 벽시계 합) — Unity 기동 · 가져오기 · measure 등 밖 시간의 몫.
    """
    rows = [entry["seconds"] for entry in entries if entry.get("state") == "done" and _measured(entry.get("seconds"))]
    if not rows:
        return None
    wall = sum(row.get("wall") or 0.0 for row in rows)
    inside = sum((row.get("unity_build") or 0.0) + (row.get("unity_render") or 0.0) for row in rows)
    ratio = None
    if wall > 0:
        ratio = round(1.0 - inside / wall, 3)
    return {"wall_total": round(wall, 3), "unity_inside": round(inside, 3),
            "per_variant_mean": round(wall / len(rows), 3), "startup_ratio": ratio, "measured": len(rows)}


def _measured(seconds):
    return isinstance(seconds, dict) and (seconds.get("unity_build") is not None or seconds.get("unity_render") is not None)


def timing_issues(summary):
    if summary is None or summary["startup_ratio"] is None or summary["startup_ratio"] <= STARTUP_HEAVY:
        return []
    detail = (f"startup_ratio {summary['startup_ratio']} — 벽시계의 대부분이 Unity 밖(기동 등)이다. "
              f"Unity 한 번에 여러 판 굽기(2차)가 값어치 있다")
    return [report.issue("variant.startup_heavy", "info", detail)]
