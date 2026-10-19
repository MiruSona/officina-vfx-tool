"""`vfxtool gif` — 사람이 움직임을 보는 preview.gif (설계 6-1).

프레임 순서 · fps 는 result.json 프레임 t 간격 · 검정 배경 합성 · nearest k 배 · 끝 프레임 0.5초 더 멈춤 · 무한 반복.
"""

from pathlib import Path

from PIL import Image

from vfxtool import frames as frames_mod
from vfxtool import report as report_mod
from vfxtool.errors import VfxError
from vfxtool.sheet import composite

DEFAULT_SCALE = 4
HOLD_LAST_MS = 500


def build_gif_frames(info, frames, k):
    images = []
    for frame in frames:
        tex = frames_mod.to_texels(frame.rgba, info.scale, info.texels)
        img = Image.fromarray(composite(tex, (0, 0, 0)), "RGB")
        images.append(img.resize((img.width * k, img.height * k), Image.NEAREST))
    return images


def durations_ms(frames):
    step = int(round(frames_mod.frame_interval(frames) * 1000.0))
    step = max(step, 10)
    durations = [step] * len(frames)
    durations[-1] = step + HOLD_LAST_MS
    return durations


def make_gif(round_dir, k=DEFAULT_SCALE, out=None):
    if k < 1:
        raise VfxError(f"--scale 는 1 이상이어야 한다 — {k}")
    result = frames_mod.load_result(round_dir)
    info = frames_mod.load_round(round_dir, result, frames_mod.load_resolved(round_dir))
    frames = frames_mod.load_frames(round_dir, result, expected=frames_mod.expected_size(info))
    images = build_gif_frames(info, frames, k)
    durations = durations_ms(frames)
    target = Path(out) if out else Path(round_dir) / "preview.gif"
    # 같은 그림이 이어지면 PIL 이 한 장으로 합친다(시간은 더해짐). 프레임 수가 줄 수 있다.
    images[0].save(target, format="GIF", save_all=True, append_images=images[1:],
                   duration=durations, loop=0, disposal=1)
    return target, len(images), durations


def add_parser(sub):
    parser = sub.add_parser("gif", help="바퀴 폴더 프레임으로 preview.gif 를 만든다(사람 확인용)")
    parser.add_argument("round_dir", help="round_N 폴더(result.json · frames/)")
    parser.add_argument("--scale", type=int, default=DEFAULT_SCALE, help="텍셀당 픽셀 배율 k (기본 4)")
    parser.add_argument("--out", help="preview.gif 자리 (기본 <round_dir>/preview.gif)")
    return parser


def run(args):
    try:
        target, count, durations = make_gif(args.round_dir, args.scale, args.out)
    except VfxError as exc:
        report_mod.emit(report_mod.error_report(str(exc)))
        return 2
    metrics = {"gif": str(target), "frames": count, "duration_ms": durations}
    report_mod.emit(report_mod.build([], metrics))
    report_mod.say(f"gif {count} 장 — {target}")
    return 0
