"""`vfxtool lib list|show|build|cut` — 소재 묶음 보기 · 기하 소재 다시 찍기 · CC0 원본 자르기(소재묶음설계 3절)."""

from vfxtool import lib_cut, lib_draw, material_lib, report
from vfxtool.errors import VfxError
from vfxtool.recipe import colors
from vfxtool.recipe.profile_view import load_profile

NAME = "lib"


def add_parser(sub):
    parser = sub.add_parser(NAME, help="소재 묶음(lib:) 목록 · 생성 · 자르기")
    actions = parser.add_subparsers(dest="lib_action", metavar="동작")
    actions.add_parser("list", help="소재 이름 · 칸 · tiles · 종류")
    show_parser = actions.add_parser("show", help="소재 메타 + PNG 경로")
    show_parser.add_argument("name", help="소재 이름")
    build_parser = actions.add_parser("build", help="기하 소재 7종을 문자 그림 표에서 다시 찍는다")
    build_parser.add_argument("--only", help="이 소재만 찍는다")
    build_parser.add_argument("--out", help="쓸 폴더 (기본 : 툴 안 소재 폴더를 덮는다)")
    cut_parser = actions.add_parser("cut", help="CC0 원본 띠를 sources.json 의 창으로 잘라 흰 실루엣 소재로 만든다")
    cut_parser.add_argument("--source", "--src", dest="source", required=True, help="원본 PNG (sha256 이 sources.json 과 같아야 한다)")
    cut_parser.add_argument("--name", required=True, help="만들 소재 이름 (sources.json 열쇠)")
    cut_parser.add_argument("--out", help="쓸 폴더 (기본 : 툴 안 소재 폴더)")
    cut_parser.add_argument("--tones", type=int, choices=lib_cut.TONES,
                            help="1 = 흰 1단, 2 = 흰 + 회색 50%% (기본 : sources.json 의 tones, 없으면 1)")
    cut_parser.add_argument("--ramp", help="팔레트 램프 — p<n> 을 쉼표로 (예 : p0,p1,p2,p3). 칸마다 휘도가 가장 가까운 색을 "
                                           "고르므로 순서는 상관없고 휘도가 같으면 앞 것. --profile · --out 이 같이 있어야 하고 "
                                           "<이름>_ramp.png 하나만 쓴다")
    cut_parser.add_argument("--profile", help="--ramp 의 p<n> 을 풀 프로필 JSON")
    return parser


def run(args):
    action = getattr(args, "lib_action", None)
    if action is None:
        raise VfxError("lib 다음에 list · show · build · cut 중 하나를 적는다")
    issues = []
    if action == "list":
        metrics = {"lib": [_summary(material_lib.load(name)) for name in material_lib.names()]}
    elif action == "show":
        metrics = {"meta": material_lib.load(args.name), "path": material_lib.path(args.name).as_posix()}
    elif action == "build":
        metrics, issues = _build(args)
    else:
        metrics, issues = _cut(args)
    built = report.build(issues, metrics)
    report.emit(built)
    return report.exit_code(built)


def _summary(meta):
    return {key: meta[key] for key in ("name", "cell", "tiles", "kind", "variants", "made", "license")}


def _out_dir(args):
    if args.out:
        return args.out
    return material_lib.LIB_DIR


def _build(args):
    try:
        written = lib_draw.build(_out_dir(args), args.only)
    except ValueError as exc:
        raise VfxError(str(exc)) from None
    return {"written": written, "out": str(_out_dir(args))}, []


def _cut(args):
    if args.ramp is not None or args.profile is not None:
        return _cut_ramp(args)
    clipped, problem = lib_cut.cut(args.source, args.name, _out_dir(args), tones=args.tones)
    metrics = {"name": args.name, "clipped": clipped, "out": str(_out_dir(args))}
    return metrics, _clip_issues(problem)


def _cut_ramp(args):
    if args.ramp is None or args.profile is None or args.out is None:
        raise VfxError("--ramp 는 --profile · --out 과 같이 쓴다")
    if args.tones is not None:
        raise VfxError("--ramp 와 --tones 는 같이 못 쓴다")
    ramp = _ramp_colors(args.ramp, load_profile(args.profile)["palette"])
    clipped, problem, mapping, frames = lib_cut.cut_ramp(args.source, args.name, args.out, ramp)
    metrics = {"name": args.name, "clipped": clipped, "out": str(args.out), "ramp": ramp}
    if problem is None:
        metrics.update({"file": lib_cut.ramp_file(args.name), "mapping": mapping,
                        "recipe": {"texture": lib_cut.ramp_file(args.name), "main": {"startColor": "#FFFFFF"},
                                   "textureSheet": {"tiles": [frames, 1]}}})
    return metrics, _clip_issues(problem)


def _ramp_colors(text, palette):
    """"p0,p1" → hex 목록. p<n> 만 받는다(램프 색은 팔레트에서 와야 한다)."""
    refs = [ref.strip() for ref in text.split(",") if ref.strip()]
    if not refs or any(colors.palette_index(ref) is None for ref in refs):
        raise VfxError(f"--ramp 는 p<n> 을 쉼표로 잇는다 : {text!r}")
    try:
        return [colors.to_hex(ref, palette) for ref in refs]
    except IndexError as exc:
        raise VfxError(str(exc)) from None


def _clip_issues(problem):
    if problem is None:
        return []
    return [report.issue("lib.clip", "error", problem, hint=["sources.json window"])]
