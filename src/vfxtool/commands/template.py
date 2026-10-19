"""`vfxtool template list|show` — 내장 + 더한 폴더의 템플릿 목록 · 내용(설계 6-1)."""

from vfxtool import report
from vfxtool.errors import VfxError
from vfxtool.recipe.schema import suggest
from vfxtool.template import load_all

NAME = "template"


def add_parser(sub):
    parser = sub.add_parser(NAME, help="템플릿 목록 · 내용 보기")
    actions = parser.add_subparsers(dest="template_action", metavar="동작")
    list_parser = actions.add_parser("list", help="내장 + 더한 폴더의 템플릿 목록")
    list_parser.add_argument("--templates", action="append", default=[], help="게임 쪽 템플릿 폴더 (여러 번)")
    show_parser = actions.add_parser("show", help="템플릿 JSON + params 표")
    show_parser.add_argument("name", help="템플릿 이름")
    show_parser.add_argument("--templates", action="append", default=[], help="게임 쪽 템플릿 폴더 (여러 번)")
    return parser


def run(args):
    action = getattr(args, "template_action", None)
    if action is None:
        raise VfxError("template 다음에 list 나 show 를 적는다")
    templates = load_all(args.templates)
    if action == "list":
        metrics = {"templates": [_summary(name, entry) for name, entry in templates.items()]}
    else:
        metrics = _show(args.name, templates)
    built = report.build([], metrics)
    report.emit(built)
    return report.exit_code(built)


def _summary(name, entry):
    data = entry["data"]
    return {
        "name": name,
        "title": data.get("title", ""),
        "source": entry["source"],
        "layers": [layer["name"] for layer in data["layers"]],
        "presets": sorted(data.get("presets", {})),
    }


def _show(name, templates):
    if name not in templates:
        guess = suggest(name, templates)
        hint = ""
        if guess is not None:
            hint = f" — 혹시 {guess!r}?"
        raise VfxError(f"모르는 템플릿 {name!r}{hint}")
    entry = templates[name]
    params = []
    for param, spec in entry["data"]["params"].items():
        params.append({"name": param, **spec})
    return {"template": entry["data"], "source": entry["source"], "params": params}
