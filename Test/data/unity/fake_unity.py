"""시험용 가짜 Unity. Unity 인자(-logFile · -vfxJob)를 받아 result.json 을 쓰고 정한 코드로 끝난다.

가짜 쪽 손잡이(-- 로 시작) : --exit N · --status ok|issues|error · --sleep 초 · --no-result
· --log-line 글 (여러 번) · --child-pid-file 경로(자식 하나를 띄워 pid 를 적는다) · --args-file 경로
· --frame-png 경로(프레임마다 이 PNG 를 복사) · --blank-png 경로(끝 프레임만 이것으로).

묶어 굽기(-vfxJobs 목록) 손잡이 : --die-at k(목록 안 k번째 판 시작 때 result 없이 종료 3)
· --die-once 표시파일(없으면 만들고 --die-at 대로 죽고, 있으면 안 죽는다) · --fail-at k(k번째 판만 status=error)
· --die-job 판이름(판 폴더 이름이 이것인 판 차례마다 늘 result 없이 종료 3)
· --list-error(jobs error= 줄만 남기고 종료 2). 목록이면 result.json 은 각 job.json 옆에, --sleep 은 판마다.
로그 줄은 C# VfxEntry 와 같은 꼴(묶어굽기설계 2-5).
"""

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path


def parse(argv):
    fake = {"exit": 0, "status": "ok", "sleep": 0.0, "no_result": False, "log_lines": [],
            "child_pid_file": None, "args_file": None, "frame_png": None, "blank_png": None,
            "die_at": 0, "die_once": None, "fail_at": 0, "die_job": None, "list_error": False}
    unity = {}
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--no-result":
            fake["no_result"] = True
        elif arg == "--list-error":
            fake["list_error"] = True
        elif arg == "--log-line":
            fake["log_lines"].append(argv[i + 1])
            i += 1
        elif arg in ("--exit", "--status", "--sleep", "--child-pid-file", "--args-file",
                     "--frame-png", "--blank-png", "--die-at", "--die-once", "--fail-at", "--die-job"):
            fake[arg[2:].replace("-", "_")] = argv[i + 1]
            i += 1
        elif arg in ("-projectPath", "-logFile", "-executeMethod", "-vfxJob", "-vfxJobs"):
            unity[arg] = argv[i + 1]
            i += 1
        i += 1
    return fake, unity


def main():
    fake, unity = parse(sys.argv[1:])
    if fake["args_file"]:
        Path(fake["args_file"]).write_text(json.dumps(sys.argv[1:]), encoding="utf-8")

    if fake["child_pid_file"]:
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        Path(fake["child_pid_file"]).write_text(str(child.pid), encoding="utf-8")

    log_file = unity.get("-logFile")
    if log_file:
        lines = ["fake unity start"] + fake["log_lines"]
        Path(log_file).write_text("\n".join(lines) + "\n", encoding="utf-8")

    if "-vfxJobs" in unity:
        sys.exit(_run_list(fake, unity["-vfxJobs"], log_file))

    time.sleep(float(fake["sleep"]))

    job = json.loads(Path(unity["-vfxJob"]).read_text(encoding="utf-8"))
    if not fake["no_result"]:
        out_dir = Path(job["outDir"])
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "result.json").write_text(json.dumps(_result(fake, job, out_dir, fake["status"])), encoding="utf-8")

    sys.exit(int(fake["exit"]))


_EXIT = {"ok": 0, "issues": 1, "error": 2}


def _result(fake, job, out_dir, status):
    frames = [{"i": f["i"], "t": f["t"], "png": f"f{f['i']:03d}.png", "particles": 1}
              for f in job["frames"]]
    _copy_frames(fake, out_dir, frames)
    issues = []
    if status == "issues":
        issues = [{"rule": "build.unknown_field", "layer": "sparks", "detail": "main.foo"}]
    return {"status": status, "unity": "fake", "prefab": "Assets/x.prefab",
            "renderApi": "SingleCameraRequest", "frames": frames, "issues": issues,
            "seconds": {"build": 0.1, "render": 0.1}}


def _log(log_file, line):
    """한 줄씩 덧붙인다 — 도중에 죽거나 끊겨도 앞 줄은 남는다(진짜 Unity 로그처럼)."""
    if log_file:
        with open(log_file, "a", encoding="utf-8") as out:
            out.write("[VFXTOOL] " + line + "\n")


def _run_list(fake, list_path, log_file):
    if fake["list_error"]:
        _log(log_file, "jobs error=가짜 목록 오류")
        return 2
    paths = json.loads(Path(list_path).read_text(encoding="utf-8"))["jobs"]
    _log(log_file, f"jobs n={len(paths)} list={list_path}")
    worst = 0
    for index, job_path in enumerate(paths, start=1):
        job = json.loads(Path(job_path).read_text(encoding="utf-8"))
        _log(log_file, f"job={job_path} mode={job['mode']} recipe=fake layers=1")
        if index == int(fake["die_at"]) and _should_die(fake["die_once"]):
            return 3
        if Path(job_path).parent.name == fake["die_job"]:
            return 3
        time.sleep(float(fake["sleep"]))
        status = "error" if index == int(fake["fail_at"]) else fake["status"]
        out_dir = Path(job["outDir"])
        out_dir.mkdir(parents=True, exist_ok=True)
        result = _result(fake, job, out_dir, status)
        result_path = Path(job_path).parent / "result.json"
        result_path.write_text(json.dumps(result), encoding="utf-8")
        code = _EXIT[status]
        worst = max(worst, code)
        _log(log_file, f"item {index}/{len(paths)} status={status} issues={len(result['issues'])} "
                       f"frames={len(result['frames'])} exit={code} result={result_path}")
    _log(log_file, f"jobs done n={len(paths)} exit={worst}")
    return worst


def _should_die(marker):
    if marker is None:
        return True
    marker = Path(marker)
    if marker.exists():
        return False
    marker.write_text("죽었음", encoding="utf-8")
    return True


def _copy_frames(fake, out_dir, frames):
    if not fake["frame_png"]:
        return
    for index, frame in enumerate(frames):
        source = fake["frame_png"]
        if fake["blank_png"] and index == len(frames) - 1:
            source = fake["blank_png"]
        shutil.copyfile(source, out_dir / frame["png"])


if __name__ == "__main__":
    main()
