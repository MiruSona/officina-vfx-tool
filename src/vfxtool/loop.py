"""고리(설계 7) — init · run · next · best. 바퀴의 일은 loop_pipeline, 장부 셈은 loop_state.

바퀴마다 round_N/ 에 recipe · resolved · patch · job · result · frames · measure · sheet · gif · critic 이 남는다.
"""

import re
from pathlib import Path

from vfxtool import loop_state as state
from vfxtool import report
from vfxtool.errors import VfxError
from vfxtool.loop_pipeline import run_pipeline
from vfxtool.paths import ensure_inside, read_json, write_json
from vfxtool.recipe.patch import apply
from vfxtool.recipe.schema import NAME_PATTERN
from vfxtool.unity.job import DEFAULT_SAVE_ROOT
from vfxtool.unity.run import DEFAULT_TIMEOUT


def init(recipe_path, work, project, profile=None, templates=(), save_root=DEFAULT_SAVE_ROOT,
         unity=None, timeout=DEFAULT_TIMEOUT, input_root=None, max_rounds=state.MAX_ROUNDS):
    """<work>/<name>/ 에 장부 · 시작 레시피 · round_1/recipe.json 을 둔다. 장부 폴더를 돌려준다."""
    source = Path(recipe_path).resolve()
    recipe = read_json(source)
    if not isinstance(recipe, dict):
        raise VfxError(f"레시피가 JSON 객체가 아니다 — {source}")
    name = recipe.get("name")
    if not isinstance(name, str) or re.fullmatch(NAME_PATTERN, name) is None:
        raise VfxError(f"레시피 name {name!r} 는 [a-z0-9_]+ 여야 한다 — 고리 폴더 이름으로 쓴다")
    if max_rounds < 1:
        raise VfxError(f"--max 는 1 이상이어야 한다 — {max_rounds}")
    work_root = Path(work).resolve()
    loop_dir = ensure_inside(work_root / name, work_root)
    if (loop_dir / state.LEDGER).exists():
        raise VfxError(f"고리가 이미 있다 — {loop_dir / state.LEDGER}")
    settings = {
        "source_dir": source.parent.as_posix(),
        "profile": _profile_path(recipe, source, profile),
        "profile_override": profile is not None,
        "input_root": _posix_or_none(input_root),
        "templates": [Path(folder).resolve().as_posix() for folder in templates],
        "project": Path(project).resolve().as_posix(),
        "save_root": save_root,
        "unity": unity,
        "timeout": timeout,
    }
    write_json(loop_dir / state.START_RECIPE, recipe)
    write_json(state.round_dir(loop_dir, 1) / "recipe.json", recipe)
    state.save(loop_dir, state.new_ledger(name, settings, max_rounds))
    return loop_dir


def _profile_path(recipe, source, profile):
    """measure · sheet 에 넘길 프로필 절대 경로. --profile 이 없으면 레시피 profile 칸을 원본 폴더 기준으로."""
    if profile is not None:
        return Path(profile).resolve().as_posix()
    if "profile" not in recipe:
        raise VfxError("레시피에 profile 칸이 없다 — --profile 을 준다")
    return (source.parent / recipe["profile"]).resolve().as_posix()


def _posix_or_none(path):
    if path is None:
        return None
    return Path(path).resolve().as_posix()


def run_round(loop_dir, ledger, extra_issues=()):
    """대기 중인 바퀴 하나를 돈다. 장부를 고쳐 저장하고 보고 dict 를 돌려준다."""
    if ledger["stopped"]:
        raise VfxError(f"고리가 멈췄다 — {ledger['stop_reason']} (loop best 로 최고점 판을 본다)")
    number = ledger["pending"]["round"]
    folder = state.round_dir(loop_dir, number)
    if not (folder / "recipe.json").is_file():
        raise VfxError(f"round_{number} 레시피가 없다 — loop next --patch 로 다음 판을 만든다")
    outcome = run_pipeline(folder, ledger["settings"])
    issues = list(extra_issues) + outcome.issues
    if outcome.failed:
        return _record_failure(loop_dir, ledger, number, issues, outcome.ranked)
    ledger["rounds"].append(_entry(ledger, number, outcome.ranked))
    ledger["pending"] = {"round": number + 1, "base": None}
    ledger["failures"] = 0
    _refresh(loop_dir, ledger)
    return _round_report(loop_dir, ledger, folder, issues, "")


def _entry(ledger, number, ranked, failed=False):
    """장부 한 줄. error · warn 수는 render · measure issue 만 센다(check issue 는 보고에만)."""
    patch = None
    if number > 1:
        patch = f"round_{number}/patch.json"
    return {
        "round": number,
        "base": ledger["pending"].get("base"),
        "patch": patch,
        "errors": sum(1 for item in ranked if item["severity"] == "error"),
        "warns": sum(1 for item in ranked if item["severity"] == "warn"),
        "score": None,
        "symptoms": [],
        "failed": failed,
        "rollback": None,
    }


def _record_failure(loop_dir, ledger, number, issues, ranked):
    """실패는 바퀴를 안 쓴다. 두 번 연달아면 실패한 판 하나로 센다(설계 7-4)."""
    ledger["failures"] += 1
    note = "바퀴를 안 썼다 — 같은 바퀴에 patch 를 다시 댄다(loop next)"
    if ledger["failures"] >= state.FAIL_LIMIT:
        ledger["rounds"].append(_entry(ledger, number, ranked, failed=True))
        ledger["pending"] = {"round": number + 1, "base": None}
        ledger["failures"] = 0
        note = "두 번 연달아 실패해 한 바퀴로 셌다"
    _refresh(loop_dir, ledger)
    built = _round_report(loop_dir, ledger, state.round_dir(loop_dir, number), issues, note)
    if any(item["rule"].startswith("unity.") and item["severity"] == "error" for item in issues):
        built["status"] = "error"
    return built


def _refresh(loop_dir, ledger):
    """판정 · 멈춤을 다시 셈해 장부에 쓴다. 마지막 판 critic.json 이 폴더에 있으면 읽는다."""
    if ledger["rounds"]:
        latest = ledger["rounds"][-1]
        critic_file = state.round_dir(loop_dir, latest["round"]) / "critic.json"
        if latest["score"] is None and not latest["failed"] and critic_file.is_file():
            state.attach_critic(latest, state.read_critic(critic_file))
    state.judge_latest(ledger)
    reason = state.stop_reason(ledger)
    if reason is not None:
        ledger["stopped"] = True
        ledger["stop_reason"] = reason
    state.save(loop_dir, ledger)


def _round_report(loop_dir, ledger, folder, issues, note):
    metrics = {"round": folder.name, "dir": str(folder), "note": note,
               "measure": str(folder / "measure.json"), "sheet": str(folder / "sheet.png"),
               "gif": str(folder / "preview.gif")}
    metrics.update(state.summary(ledger, loop_dir))
    return report.build(issues, metrics)


def next_round(loop_dir, ledger, patch_path=None, critic_path=None):
    """critic 을 마지막 판에 붙여 판정하고, 안 멈췄고 patch 가 있으면 최고점 판에 대 다음 바퀴를 돈다."""
    if critic_path is not None:
        if not ledger["rounds"]:
            raise VfxError("critic 을 붙일 판이 없다 — 먼저 loop run")
        latest = ledger["rounds"][-1]
        critic = state.read_critic(critic_path)
        write_json(state.round_dir(loop_dir, latest["round"]) / "critic.json", critic)
        state.attach_critic(latest, critic)
    _refresh(loop_dir, ledger)
    _set_next_base(loop_dir, ledger)
    if ledger["stopped"] or patch_path is None:
        note = "patch 없음 — 판정만 했다"
        if ledger["stopped"]:
            note = f"고리가 멈췄다 — {ledger['stop_reason']}"
        return report.build([], dict(state.summary(ledger, loop_dir), note=note))
    patch_issues = _prepare_round(loop_dir, ledger, read_json(patch_path))
    if report.has_errors(patch_issues):
        return report.build(patch_issues, dict(state.summary(ledger, loop_dir), note="patch 를 거절했다 — 바퀴를 안 썼다"))
    return run_round(loop_dir, ledger, patch_issues)


def _set_next_base(loop_dir, ledger):
    """판정 뒤 다음 바퀴의 base 를 최고점 판으로 정해 둔다(rollback 이면 전 판, 아니면 이 판).

    아직 돈 판이 없으면(round_1 대기) 건드리지 않는다. 쓸 판이 없으면 0(시작 레시피).
    """
    if not ledger["rounds"]:
        return
    best = state.best_round(ledger)
    base_no = 0
    if best is not None:
        base_no = best["round"]
    ledger["pending"]["base"] = base_no
    state.save(loop_dir, ledger)


def _prepare_round(loop_dir, ledger, patch):
    """최고점 판(없으면 시작 레시피)에 patch 를 대 대기 바퀴의 recipe.json · patch.json 을 쓴다. patch issues 를 돌려준다."""
    best = state.best_round(ledger)
    base_file = Path(loop_dir) / state.START_RECIPE
    base_no = 0
    if best is not None:
        base_file = state.round_dir(loop_dir, best["round"]) / "recipe.json"
        base_no = best["round"]
    patched, issues = apply(read_json(base_file), patch)
    if patched is None:
        return issues
    folder = state.round_dir(loop_dir, ledger["pending"]["round"])
    write_json(folder / "recipe.json", patched)
    write_json(folder / "patch.json", patch)
    ledger["pending"]["base"] = base_no
    state.save(loop_dir, ledger)
    return issues


def best(loop_dir, ledger):
    """최고점 판 보고. 판이 없으면 VfxError."""
    if state.best_round(ledger) is None:
        raise VfxError("아직 쓸 만한 판이 없다 — loop run 을 먼저 돈다")
    return report.build([], state.summary(ledger, loop_dir))
