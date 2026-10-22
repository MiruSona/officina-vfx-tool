"""고리 한 바퀴의 일 — check → render(Unity) → measure → sheet → gif. 장부는 안 만진다.

check 는 원본 레시피 폴더를 기준으로 돈다(profile · texture 상대 경로가 그대로 맞게).
"""

import argparse
import shutil
from pathlib import Path

from vfxtool import gif as gif_mod
from vfxtool import measure as measure_mod
from vfxtool import report
from vfxtool import sheet as sheet_mod
from vfxtool.errors import VfxError
from vfxtool.paths import read_json, write_json
from vfxtool.recipe.check import run_check
from vfxtool.unity import command as unity_command


class RoundOutcome:
    """한 바퀴 결과. issues 는 보고에 다 싣고, ranked(render · measure 것)만 순위 · clean 판정에 쓴다."""

    def __init__(self, issues, ranked, failed):
        self.issues = issues
        self.ranked = ranked
        self.failed = failed


def run_pipeline(folder, settings):
    """RoundOutcome. check fail · Unity error · 프레임 못 읽음은 바퀴를 못 쓸 실패(failed)다."""
    checked_issues, resolved_path = prepare_round(folder, settings)
    if resolved_path is None:
        return RoundOutcome(checked_issues, checked_issues, True)
    try:
        rendered = unity_command.execute(render_args(folder, resolved_path, settings))
    except VfxError as exc:
        return unity_failed(checked_issues, exc)
    return finish_round(folder, settings, checked_issues, rendered)


def prepare_round(folder, settings):
    """Unity 앞 토막 — check 하고 resolved.json 을 쓴다. (check issues, resolved 경로 또는 None=check 실패)."""
    recipe = read_json(folder / "recipe.json")
    base = Path(settings["source_dir"]) / "recipe.json"
    profile = None
    if settings["profile_override"]:
        profile = settings["profile"]
    checked = run_check(recipe, base, profile, settings["input_root"], settings["templates"])
    checked_issues = list(checked.issues)
    if checked.resolved is None:
        return checked_issues, None
    return checked_issues, write_json(folder / "resolved.json", checked.resolved)


def unity_failed(checked_issues, exc):
    """Unity 명령이 VfxError 로 끝났다(못 찾음 · 잠김 · 시간 넘김) — 바퀴 실패."""
    ranked = [report.issue("unity.error", "error", exc.message)]
    return RoundOutcome(checked_issues + ranked, ranked, True)


def finish_round(folder, settings, checked_issues, rendered):
    """Unity 뒤 토막 — render 보고를 판정하고 measure · sheet · gif."""
    ranked = list(rendered["issues"])
    if rendered["status"] == "error" or not rendered["metrics"].get("frames"):
        return RoundOutcome(checked_issues + ranked, ranked, True)
    _lift_result(folder)
    try:
        ranked += _measure_outputs(folder, settings)
    except VfxError as exc:
        ranked.append(report.issue("loop.measure", "error", exc.message))
        return RoundOutcome(checked_issues + ranked, ranked, True)
    return RoundOutcome(checked_issues + ranked, ranked, False)


def render_args(folder, resolved_path, settings):
    return argparse.Namespace(
        unity_mode="render", resolved=str(resolved_path), project=settings["project"],
        save_root=settings["save_root"], work=str(folder), unity=settings["unity"],
        timeout=settings["timeout"], fps=None, backgrounds=None,
        input_root=settings["input_root"] or settings["source_dir"],
    )


def _lift_result(folder):
    """result.json 이 frames/ 안에만 있으면 바퀴 폴더로 올린다(measure 는 바퀴 폴더에서 읽는다)."""
    top = folder / "result.json"
    inner = folder / "frames" / "result.json"
    if not top.is_file() and inner.is_file():
        shutil.copyfile(inner, top)


def _measure_outputs(folder, settings):
    measured = measure_mod.measure(folder, settings["profile"], template_dirs=settings["templates"])
    write_json(folder / "measure.json", measured)
    sheet_mod.make_sheet(folder, folder / "measure.json", False, settings["profile"])
    gif_mod.make_gif(folder)
    return measured["issues"]
