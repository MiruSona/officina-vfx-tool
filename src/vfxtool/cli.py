"""`python -m vfxtool` — 하위 명령 등록 · 실행 · 종료 코드.

명령은 `vfxtool.commands.<이름>` 모듈이 `add_parser(sub)` · `run(args) -> int` 로 붙는다.
인자 오류 · 명령 없음도 보고 JSON(stdout) · 종료 2 로 끝낸다. 사람용 사용법은 stderr 로.
"""

import argparse
import sys
import traceback

from vfxtool import __version__, report
from vfxtool.commands import build, check, doctor, gif, lib, loop, measure, patch, profile, render, sheet, template, variant
from vfxtool.errors import VfxError

PROG = "vfxtool"

# 명령 표. 순서가 --help 순서다.
COMMANDS = {
    "profile": profile,
    "check": check,
    "patch": patch,
    "build": build,
    "render": render,
    "measure": measure,
    "sheet": sheet,
    "gif": gif,
    "loop": loop,
    "template": template,
    "lib": lib,
    "variant": variant,
    "doctor": doctor,
}


class UsageError(Exception):
    """argparse 인자 오류. main 이 보고 JSON 으로 바꾼다."""


class ReportingParser(argparse.ArgumentParser):
    """오류 때 바로 끝내지 않고 UsageError 를 던진다. 하위 파서도 이 꼴을 물려받는다."""

    def error(self, message):
        self.print_usage(sys.stderr)
        raise UsageError(f"{self.prog} : {message}")


def build_parser(modules=None):
    if modules is None:
        modules = COMMANDS
    parser = ReportingParser(
        prog=PROG,
        description="레시피 JSON 으로 Unity 파티클 이펙트를 조립 · 렌더 · 검수한다.",
    )
    parser.add_argument("--version", action="version", version=f"{PROG} {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="명령", parser_class=ReportingParser)
    for module in modules.values():
        command_parser = module.add_parser(sub)
        command_parser.set_defaults(handler=module.run)
    return parser


def main(argv=None):
    # 파이프로 받는 쪽이 늘 UTF-8 을 받게 한다(보고 JSON 과 같은 인코딩). 콘솔 화면 출력은 영향 없다.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except UsageError as exc:
        report.emit(report.error_report(f"인자 오류 — {exc}"))
        return 2
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help(sys.stderr)
        report.emit(report.error_report("명령이 없다 — vfxtool --help 로 명령 목록을 본다"))
        return 2
    try:
        return handler(args)
    except VfxError as exc:
        report.emit(report.error_report(exc.message))
        return 2
    except Exception as exc:  # 맨 바깥 경계 — 어떤 오류도 보고 JSON · 종료 2 로 끝낸다.
        traceback.print_exc(file=sys.stderr)
        report.emit(report.error_report(f"예상 못 한 오류 {type(exc).__name__} : {exc}"))
        return 2
