"""모든 명령이 쓰는 보고 JSON — 만들기 · stdout 출력 · 종료 코드(설계 6-1).

꼴 : {"status": "ok|warn|fail|error", "issues": [...], "metrics": {...}}. 사람용 글은 stderr 로.
"""

import json
import sys

SEVERITIES = ("error", "warn", "info")
EXIT_CODES = {"ok": 0, "warn": 0, "fail": 1, "error": 2}


def issue(rule, severity, detail, layer=None, frame=None, hint=None):
    """issue 한 칸. 칸 순서를 고정해 출력이 늘 같게 한다."""
    if severity not in SEVERITIES:
        raise ValueError(f"모르는 심각도 : {severity}")
    hints = []
    if isinstance(hint, str):
        hints = [hint]
    elif hint is not None:
        hints = list(hint)
    return {
        "rule": rule,
        "layer": layer,
        "frame": frame,
        "severity": severity,
        "detail": detail,
        "hint": hints,
    }


def status_of(issues):
    """error 가 하나라도 있으면 fail, warn 이 있으면 warn, 아니면 ok."""
    severities = {item["severity"] for item in issues}
    if "error" in severities:
        return "fail"
    if "warn" in severities:
        return "warn"
    return "ok"


def build(issues, metrics=None):
    if metrics is None:
        metrics = {}
    return {"status": status_of(issues), "issues": list(issues), "metrics": metrics}


def error_report(message):
    """종료 2 용 보고. 규칙이 아니라 인자 · 파일 · 환경 문제다."""
    return {
        "status": "error",
        "issues": [issue("vfxtool.error", "error", message)],
        "metrics": {},
    }


def has_errors(issues):
    return any(item["severity"] == "error" for item in issues)


def emit(report):
    """보고를 stdout 에 UTF-8 JSON 한 덩어리로 쓴다(윈도 콘솔 코드 페이지와 상관없이)."""
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is None:
        sys.stdout.write(text)
        return
    sys.stdout.flush()
    buffer.write(text.encode("utf-8"))
    buffer.flush()


def exit_code(report):
    return EXIT_CODES[report["status"]]


def say(message):
    """사람용 한 줄은 stderr 로."""
    print(message, file=sys.stderr)
