"""`vfxtool patch <recipe> <patch> --out <새 recipe>` — 부분 덮기 뒤 check 까지(설계 7-3).

새 레시피는 --out 자리에 늘 쓰고, check 는 그 자리 기준(profile · texture 상대 경로)으로 돈다.
"""

from pathlib import Path

from vfxtool import report
from vfxtool.paths import read_json, write_json
from vfxtool.recipe.check import run_check
from vfxtool.recipe.patch import apply

NAME = "patch"


def add_parser(sub):
    parser = sub.add_parser(NAME, help="레시피에 patch(부분 덮기)를 대고 check 한다")
    parser.add_argument("recipe", help="고칠 레시피 JSON (템플릿 펼치기 전)")
    parser.add_argument("patch", help="patch JSON — layers 는 층 이름 열쇠")
    parser.add_argument("--out", required=True, help="새 레시피 JSON 자리")
    parser.add_argument("--profile", help="레시피의 profile 칸 대신 쓸 프로필 JSON")
    parser.add_argument("--input-root", help="texture · profile 이 있어도 되는 폴더 (기본 : --out 폴더)")
    parser.add_argument("--templates", action="append", default=[], help="게임 쪽 템플릿 폴더 (여러 번)")
    return parser


def run(args):
    patched, patch_issues = apply(read_json(args.recipe), read_json(args.patch))
    if patched is None:
        built = report.build(patch_issues, {"out": None})
        report.emit(built)
        return report.exit_code(built)
    out = write_json(args.out, patched)
    result = run_check(patched, Path(out), args.profile, args.input_root, args.templates)
    metrics = {"out": str(out), "layers": len(patched.get("layers", [])), "check": report.status_of(result.issues)}
    built = report.build(patch_issues + result.issues, metrics)
    report.emit(built)
    return report.exit_code(built)
