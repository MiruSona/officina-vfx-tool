"""`vfxtool variant expand|run|sheet` — 변형 묶음 펼치기 · 돌리기 · 격자 접촉판(변형묶음설계 7절)."""

from vfxtool import report
from vfxtool import variant_run, variant_sheet
from vfxtool.errors import VfxError
from vfxtool.unity.guard import positive_float
from vfxtool.unity.job import DEFAULT_SAVE_ROOT
from vfxtool.unity.run import DEFAULT_TIMEOUT
from vfxtool.variant_expand import expand_set
from vfxtool.variant_set import SET_FILE, SetLocked

NAME = "variant"
STATES = ("expanded", "failed", "done")


def add_parser(sub):
    parser = sub.add_parser(NAME, help="변형 묶음 — 속성 × 세기 × 시드로 펼치기")
    actions = parser.add_subparsers(dest="variant_action", metavar="동작")
    expand = actions.add_parser("expand", help="묶음 JSON 을 판 폴더 · set.json 으로 펼친다 (Unity 안 띄움)")
    expand.add_argument("set", help="변형 묶음 JSON 경로")
    expand.add_argument("--work", required=True, help="작업 폴더 — <work>/<묶음 name>/ 에 쓴다")
    expand.add_argument("--variants", action="append", default=[], help="게임 쪽 변형 사전 폴더 (여러 번, 뒤가 이김)")
    expand.add_argument("--templates", action="append", default=[], help="게임 쪽 템플릿 폴더 (여러 번)")
    expand.add_argument("--lib-src", help="램프 굽기용 CC0 원본 폴더 (ramp: 치환 때만)")
    expand.add_argument("--input-root", help="profile · 게임 텍스처가 있어도 되는 폴더 (기본 : 묶음 파일 폴더)")
    expand.add_argument("--force", action="store_true", help="이미 있는 묶음 폴더에서 done 이 아닌 판만 다시 쓴다")

    run = actions.add_parser("run", help="expanded 판을 이름 순으로 하나씩 Unity 로 돌리고 끝에 sheet")
    run.add_argument("--work", required=True, help="묶음 폴더(set.json 이 있는 곳, Unity 프로젝트 밖)")
    run.add_argument("--project", required=True, help="Unity 프로젝트 폴더")
    run.add_argument("--only", action="append", default=[], help="이 판만 (여러 번 또는 쉼표로)")
    run.add_argument("--unity", help="Unity.exe 경로(또는 명령)")
    run.add_argument("--timeout", type=positive_float, default=DEFAULT_TIMEOUT, help="Unity 한 판 상한(초)")
    run.add_argument("--save-root", default=DEFAULT_SAVE_ROOT, help="프리팹 저장 자리(Assets/ 안)")
    run.add_argument("--no-sheet", action="store_true", help="끝에 overview · strips 를 안 그린다")

    sheet = actions.add_parser("sheet", help="overview.png · strips_N.png 를 다시 그린다")
    sheet.add_argument("--work", required=True, help="묶음 폴더(set.json 이 있는 곳)")
    return parser


def run(args):
    action = getattr(args, "variant_action", None)
    if action == "expand":
        try:
            ledger_path, ledger = expand_set(args.set, args.work, args.variants, args.templates, args.lib_src, args.input_root, args.force)
        except SetLocked as exc:
            return _locked(exc)
        return _finish(report.build(set_issues(ledger), set_metrics(ledger_path, ledger, "variant run")))
    if action == "run":
        return _run_set(args)
    if action == "sheet":
        set_dir = variant_run.find_set_dir(args.work)
        made, issues = variant_sheet.make_sheets(set_dir)
        return _finish(report.build(issues, {"set": (set_dir / SET_FILE).as_posix(), "sheets": _sheet_list(made)}))
    raise VfxError("variant 다음에 expand · run · sheet 중 하나를 적는다")


def _run_set(args):
    """판을 돌리고 끝에 sheet. 판 실패는 종료 1, 묶음 · 인자 · 환경 오류는 VfxError(종료 2)."""
    try:
        ledger_path, ledger, extra = variant_run.run_set(args.work, args.project, args.only, args.unity, args.timeout, args.save_root)
    except SetLocked as exc:
        return _locked(exc)
    sheets = None
    sheet_issues = []
    if not args.no_sheet:
        made, sheet_issues = variant_sheet.make_sheets(ledger_path.parent)
        sheets = _sheet_list(made)
    metrics = set_metrics(ledger_path, ledger, "variant run")
    if args.no_sheet and not metrics["next"]:
        metrics["next"] = "variant sheet"
    metrics["sheets"] = sheets
    issues = extra + set_issues(ledger) + variant_run.timing_issues(metrics["timing"]) + sheet_issues
    return _finish(report.build(issues, metrics))


def _locked(exc):
    """set.lock 이 있어 expand --force · run 을 못 한다 — variant.locked 종료 2."""
    hint = [f"다른 판이 끝났는데 남았으면 {exc.lock_file} 를 지운다"]
    return _finish({"status": "error", "issues": [report.issue("variant.locked", "error", exc.message, hint=hint)], "metrics": {}})


def _sheet_list(made):
    return [{"path": path.as_posix(), "size": list(size)} for path, size in made]


def _finish(built):
    report.emit(built)
    return report.exit_code(built)


def set_issues(ledger):
    """실패 판마다 variant.* issue 에 variant 칸을 붙인다. 판 안 check issue 는 set.json 에만 둔다."""
    found = []
    for entry in ledger["variants"]:
        for item in entry["issues"]:
            if not item["rule"].startswith("variant."):
                continue
            found.append({**item, "variant": entry["name"]})
    return found


def set_metrics(ledger_path, ledger, next_step):
    counts = {"total": len(ledger["variants"])}
    for state in STATES:
        counts[state] = sum(1 for entry in ledger["variants"] if entry["state"] == state)
    variants = []
    for entry in ledger["variants"]:
        variants.append({
            "name": entry["name"], "attr": entry["attr"], "tier": entry["tier"], "seed": entry["seed"],
            "state": entry["state"], "errors": entry["errors"], "warns": entry["warns"],
            "seconds": entry["seconds"], "notes": [item["detail"] for item in entry["notes"]],
        })
    following = None
    if counts["expanded"]:
        following = next_step
    return {"set": ledger_path.as_posix(), "counts": counts, "variants": variants,
            "timing": variant_run.timing(ledger["variants"]), "next": following}
