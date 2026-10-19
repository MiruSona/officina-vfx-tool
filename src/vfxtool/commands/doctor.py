"""`vfxtool doctor` — Python 의존성 · Unity 판을 본다(설계 6-1).

--project 를 주면 Unity.exe · 잠금 · manifest 의 com.officina.vfx · Newtonsoft 줄도 본다(잠금 · manifest 는 info).
"""

import platform
from importlib import metadata
from pathlib import Path

from vfxtool import report
from vfxtool.errors import VfxError
from vfxtool.unity.locate import locate_unity, read_editor_version
from vfxtool.unity.lock import check_lock

NAME = "doctor"
PACKAGES = ("pillow", "numpy")
PACKAGE_NAME = "com.officina.vfx"
NEWTONSOFT_NAME = "com.unity.nuget.newtonsoft-json"


def add_parser(sub):
    parser = sub.add_parser(NAME, help="Python 의존성 · Unity 판을 확인한다")
    parser.add_argument("--project", help="Unity 프로젝트 폴더")
    return parser


def run(args):
    issues = []
    metrics = {"python": platform.python_version(), "packages": {}}
    for name in PACKAGES:
        try:
            metrics["packages"][name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            metrics["packages"][name] = None
            issues.append(report.issue("doctor.package", "error", f"Python 패키지 {name} 가 없다 — setup.ps1 을 다시 돌린다"))
    if args.project:
        metrics["unity_version"] = read_editor_version(Path(args.project))
        metrics["unity_exe"] = _locate(Path(args.project), issues)
        metrics["lock"] = _lock(Path(args.project), issues)
        metrics["vfx_package"] = _manifest_has_package(Path(args.project), issues)
    built = report.build(issues, metrics)
    report.emit(built)
    return report.exit_code(built)


def _locate(project, issues):
    """Unity.exe 명령 줄. 못 찾으면 error 로 알리고 None."""
    try:
        return " ".join(locate_unity(project))
    except VfxError as exc:
        issues.append(report.issue("doctor.unity_exe", "error", exc.message))
        return None


def _lock(project, issues):
    """같은 프로젝트를 연 Unity 가 있나. 막혀도 doctor 는 info 로만 알린다."""
    try:
        state = check_lock(project)
    except VfxError as exc:
        issues.append(report.issue("doctor.lock", "info", exc.message))
        return "blocked"
    issues.append(report.issue("doctor.lock", "info", f"잠금 상태 {state}"))
    return state


def _manifest_has_package(project, issues):
    manifest = project / "Packages" / "manifest.json"
    if not manifest.is_file():
        issues.append(report.issue("doctor.manifest", "info", f"Packages/manifest.json 이 없다 : {manifest}"))
        return False
    text = manifest.read_text(encoding="utf-8", errors="replace")
    found = f'"{PACKAGE_NAME}"' in text
    if found:
        issues.append(report.issue("doctor.manifest", "info", f"manifest 에 {PACKAGE_NAME} 줄이 있다"))
    else:
        issues.append(report.issue("doctor.manifest", "info", f"manifest 에 {PACKAGE_NAME} 줄이 없다 — 패키지를 넣어야 build · render 가 돈다"))
    _newtonsoft_issue(text, issues)
    return found


def _newtonsoft_issue(text, issues):
    """C# 패키지는 Newtonsoft 로 resolved 를 읽는다. manifest 에 직접 적혔는지만 info 로 알린다."""
    if f'"{NEWTONSOFT_NAME}"' in text:
        issues.append(report.issue("doctor.newtonsoft", "info", f"manifest 에 {NEWTONSOFT_NAME} 줄이 있다"))
        return
    issues.append(report.issue("doctor.newtonsoft", "info",
                               f"manifest 에 {NEWTONSOFT_NAME} 줄이 없다 — 패키지 의존성으로 들어오는지 Unity 에서 본다"))
