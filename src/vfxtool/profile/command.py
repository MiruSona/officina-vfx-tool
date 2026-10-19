"""`vfxtool profile` 명령. 보고 JSON 은 stdout 한 덩어리(설계 6-1)."""
from pathlib import Path

from vfxtool import report as reports
from vfxtool.errors import VfxError
from vfxtool.paths import read_json, write_json
from vfxtool.profile.common import make_issue
from vfxtool.profile.extract import extract
from vfxtool.profile.merge import merge
from vfxtool.profile.style import map_style



def add_parser(sub):
    parser = sub.add_parser("profile", help="기준 PNG · 화풍 조각 · 손 덮기로 VFX 프로필을 만든다")
    parser.add_argument("--from", dest="from_png", action="append", required=True, metavar="PNG",
                        help="기준 PNG(1:1 원본). 여러 번 줄 수 있다")
    parser.add_argument("--style", help="화풍 조각 JSON (아는 키만 읽는다)")
    parser.add_argument("--override", help="손 덮기 JSON (가장 세다)")
    parser.add_argument("--out", required=True, help="쓸 profile.json")
    return parser


def _read_object(path: str, what: str) -> dict:
    data = read_json(path)
    if not isinstance(data, dict):
        raise VfxError(f"{what} 는 JSON 객체여야 한다 : {path}")
    return data


def build_report(args) -> dict:
    extracted = extract(args.from_png)
    issues = list(extracted["issues"])
    metrics = dict(extracted["metrics"])

    style_fields = {}
    if args.style:
        mapped = map_style(_read_object(args.style, "화풍 조각"))
        style_fields = mapped["fields"]
        issues.extend(mapped["issues"])
        metrics["style_ignored"] = mapped["ignored"]

    override = None
    if args.override:
        override = _read_object(args.override, "손 덮기")

    merged = merge(extracted["fields"], style_fields, override)
    issues.extend(merged["issues"])
    profile = merged["profile"]
    metrics["palette"] = len(profile["palette"])

    if not profile["palette"]:
        issues.append(make_issue("profile.palette_empty", "error", "팔레트가 비었다 — 프로필을 쓰지 않았다",
                                 ["--from", "--style", "--override"]))
        return reports.build(issues, metrics)

    out = Path(args.out)
    write_json(out, profile)
    metrics["out"] = str(out)
    return reports.build(issues, metrics)


def run(args) -> int:
    try:
        report = build_report(args)
    except VfxError as error:
        report = {"status": "error", "issues": [make_issue("profile.error", "error", error.message)], "metrics": {}}
    reports.emit(report)
    return reports.exit_code(report)
