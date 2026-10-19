"""`vfxtool check <recipe>` — 레시피 검사 + resolved.json(설계 6-1 · 8-1)."""

from pathlib import Path

from vfxtool import report
from vfxtool.paths import read_json, write_json
from vfxtool.recipe.check import run_check

NAME = "check"


def add_parser(sub):
    parser = sub.add_parser(NAME, help="레시피를 검사하고 resolved.json 을 만든다 (Unity 안 띄움)")
    parser.add_argument("recipe", help="레시피 JSON 경로")
    parser.add_argument("--profile", help="레시피의 profile 칸 대신 쓸 프로필 JSON")
    parser.add_argument("--out", help="resolved.json 을 저장할 자리 (error 가 있으면 안 쓴다)")
    parser.add_argument("--input-root", help="texture · profile 이 있어도 되는 폴더 (기본 : 레시피 폴더)")
    parser.add_argument("--templates", action="append", default=[], help="게임 쪽 템플릿 폴더 (여러 번)")
    return parser


def run(args):
    recipe_path = Path(args.recipe)
    recipe = read_json(recipe_path)
    result = run_check(recipe, recipe_path, args.profile, args.input_root, args.templates)
    metrics = {"layers": 0, "out": None}
    if result.resolved is not None:
        metrics["layers"] = len(result.resolved["layers"])
        if args.out:
            metrics["out"] = str(write_json(args.out, result.resolved))
    built = report.build(result.issues, metrics)
    report.emit(built)
    return report.exit_code(built)
