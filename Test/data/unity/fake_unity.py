"""시험용 가짜 Unity. Unity 인자(-logFile · -vfxJob)를 받아 result.json 을 쓰고 정한 코드로 끝난다.

가짜 쪽 손잡이(-- 로 시작) : --exit N · --status ok|issues|error · --sleep 초 · --no-result
· --log-line 글 (여러 번) · --child-pid-file 경로(자식 하나를 띄워 pid 를 적는다) · --args-file 경로
· --frame-png 경로(프레임마다 이 PNG 를 복사) · --blank-png 경로(끝 프레임만 이것으로).
"""

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path


def parse(argv):
    fake = {"exit": 0, "status": "ok", "sleep": 0.0, "no_result": False, "log_lines": [],
            "child_pid_file": None, "args_file": None, "frame_png": None, "blank_png": None}
    unity = {}
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--no-result":
            fake["no_result"] = True
        elif arg == "--log-line":
            fake["log_lines"].append(argv[i + 1])
            i += 1
        elif arg in ("--exit", "--status", "--sleep", "--child-pid-file", "--args-file",
                     "--frame-png", "--blank-png"):
            fake[arg[2:].replace("-", "_")] = argv[i + 1]
            i += 1
        elif arg in ("-projectPath", "-logFile", "-executeMethod", "-vfxJob"):
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

    time.sleep(float(fake["sleep"]))

    job = json.loads(Path(unity["-vfxJob"]).read_text(encoding="utf-8"))
    if not fake["no_result"]:
        out_dir = Path(job["outDir"])
        out_dir.mkdir(parents=True, exist_ok=True)
        frames = [{"i": f["i"], "t": f["t"], "png": f"f{f['i']:03d}.png", "particles": 1}
                  for f in job["frames"]]
        _copy_frames(fake, out_dir, frames)
        issues = []
        if fake["status"] == "issues":
            issues = [{"rule": "build.unknown_field", "layer": "sparks", "detail": "main.foo"}]
        result = {"status": fake["status"], "unity": "fake", "prefab": "Assets/x.prefab",
                  "renderApi": "SingleCameraRequest", "frames": frames, "issues": issues,
                  "seconds": {"build": 0.1, "render": 0.1}}
        (out_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")

    sys.exit(int(fake["exit"]))


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
