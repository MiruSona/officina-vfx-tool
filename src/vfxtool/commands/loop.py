"""`vfxtool loop init|run|next|best` — 고리 장부와 바퀴 돌리기(설계 7). 본문은 vfxtool.loop."""

from vfxtool import loop as loop_mod
from vfxtool import loop_state as state
from vfxtool import report
from vfxtool.unity.guard import positive_float, positive_int
from vfxtool.unity.job import DEFAULT_SAVE_ROOT
from vfxtool.unity.run import DEFAULT_TIMEOUT

NAME = "loop"


def add_parser(sub):
    parser = sub.add_parser(NAME, help="check → render → measure → sheet · gif 고리를 바퀴 단위로 돈다")
    actions = parser.add_subparsers(dest="loop_action", metavar="동작")
    actions.required = True

    init = actions.add_parser("init", help="<work>/<name>/loop.json 장부와 round_1 레시피를 만든다")
    init.add_argument("recipe", help="시작 레시피 JSON (템플릿 펼치기 전)")
    init.add_argument("--work", required=True, help="고리 폴더를 둘 자리(Unity 프로젝트 밖)")
    init.add_argument("--project", required=True, help="Unity 프로젝트 폴더")
    init.add_argument("--profile", help="레시피 profile 칸 대신 쓸 프로필 JSON")
    init.add_argument("--templates", action="append", default=[], help="게임 쪽 템플릿 폴더 (여러 번)")
    init.add_argument("--save-root", default=DEFAULT_SAVE_ROOT, help="프리팹 저장 자리(Assets/ 안)")
    init.add_argument("--input-root", help="texture · profile 이 있어도 되는 폴더 (기본 : 레시피 폴더)")
    init.add_argument("--unity", help="Unity.exe 경로(또는 명령)")
    init.add_argument("--timeout", type=positive_float, default=DEFAULT_TIMEOUT, help="Unity 한 판 상한(초)")
    init.add_argument("--max", type=positive_int, default=state.MAX_ROUNDS, help="바퀴 상한 (기본 4)")

    run = actions.add_parser("run", help="대기 중인 바퀴 하나를 돈다")
    run.add_argument("--work", required=True, help="loop.json 폴더(또는 그 위 폴더)")

    step = actions.add_parser("next", help="critic 을 붙여 판정하고 patch 로 다음 바퀴를 돈다")
    step.add_argument("--work", required=True, help="loop.json 폴더(또는 그 위 폴더)")
    step.add_argument("--patch", help="patch JSON — 최고점 판 레시피에 댄다. 없으면 판정만")
    step.add_argument("--critic", help="마지막 판 critic.json (없으면 그 바퀴 폴더의 critic.json)")

    best = actions.add_parser("best", help="최고점 판 경로 · 점수")
    best.add_argument("--work", required=True, help="loop.json 폴더(또는 그 위 폴더)")
    return parser


def run(args):
    action = args.loop_action
    if action == "init":
        loop_dir = loop_mod.init(args.recipe, args.work, args.project, args.profile, args.templates,
                                 args.save_root, args.unity, args.timeout, args.input_root, args.max)
        built = report.build([], {"loop": str(loop_dir / state.LEDGER), "next": "loop run"})
        return _finish(built)

    loop_dir = state.find_loop_dir(args.work)
    if action == "best":
        return _finish(loop_mod.best(loop_dir, state.load(loop_dir)))
    try:
        with state.locked(loop_dir):
            ledger = state.load(loop_dir)
            if action == "run":
                built = loop_mod.run_round(loop_dir, ledger)
            else:
                built = loop_mod.next_round(loop_dir, ledger, args.patch, args.critic)
    except state.LoopLocked as exc:
        hint = [f"다른 판이 끝났는데 남았으면 {exc.lock_file} 를 지운다"]
        built = {"status": "error", "issues": [report.issue("loop.locked", "error", exc.message, hint=hint)], "metrics": {}}
    return _finish(built)


def _finish(built):
    report.emit(built)
    metrics = built["metrics"]
    if metrics.get("stopped"):
        report.say(f"loop 멈춤 — {metrics['stop_reason']}")
    return report.exit_code(built)
