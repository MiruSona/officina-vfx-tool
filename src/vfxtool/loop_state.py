"""고리 장부 loop.json — 바퀴 · 순위 · rollback · 멈춤 까닭(설계 7-1 · 7-4).

순위 : ① error 수 적은 판 ② critic score 높은 판 ③ warn 수 적은 판. 같으면 나중 판이 앞선다.
error · warn 수는 render(unity) · measure(프레임) issue 만 센다. check issue 는 보고에만 싣는다.
"""

from pathlib import Path

from vfxtool.errors import VfxError
from vfxtool.paths import exclusive_lock, read_json, write_json

LEDGER = "loop.json"
LOCK = "loop.lock"
START_RECIPE = "recipe.start.json"
MAX_ROUNDS = 4
CLEAN_SCORE = 0.9
STALL_ROLLBACKS = 2
FAIL_LIMIT = 2


def new_ledger(name, settings, max_rounds=MAX_ROUNDS):
    return {
        "version": 1,
        "name": name,
        "max_rounds": max_rounds,
        "settings": settings,
        "rounds": [],
        "pending": {"round": 1, "base": 0},
        "failures": 0,
        "stopped": False,
        "stop_reason": None,
    }


def find_loop_dir(work):
    """loop.json 이 있는 폴더. work 자체거나, 바로 아래 하나뿐인 <name>/ 폴더."""
    root = Path(work).resolve()
    if (root / LEDGER).is_file():
        return root
    found = []
    if root.is_dir():
        found = [child for child in root.iterdir() if (child / LEDGER).is_file()]
    if len(found) == 1:
        return found[0]
    if not found:
        raise VfxError(f"loop.json 이 없다 — {root} (먼저 loop init)")
    raise VfxError(f"loop.json 이 여럿이다 — {root} 아래 <name> 폴더를 --work 로 준다")


class LoopLocked(VfxError):
    """다른 판이 장부를 쥐고 있다(loop.lock)."""

    def __init__(self, lock_file):
        super().__init__(f"다른 loop 판이 돌고 있다 — {lock_file}")
        self.lock_file = lock_file


def locked(loop_dir):
    """run · next 한 판만 장부를 고치게 loop.lock 을 쥔다."""
    return exclusive_lock(Path(loop_dir) / LOCK, LoopLocked)


def load(loop_dir):
    return read_json(Path(loop_dir) / LEDGER)


def save(loop_dir, ledger):
    write_json(Path(loop_dir) / LEDGER, ledger)


def round_dir(loop_dir, number):
    return Path(loop_dir) / f"round_{number}"


def rank_key(entry):
    """작을수록 앞선 판. 실패한 판은 늘 맨 뒤."""
    score = entry.get("score")
    if score is None:
        score = 0.0
    failed = 0
    if entry.get("failed"):
        failed = 1
    return (failed, entry["errors"], -float(score), entry["warns"], -entry["round"])


def best_round(ledger):
    """최고점 판(실패한 판은 뺀다). 없으면 None."""
    usable = [entry for entry in ledger["rounds"] if not entry.get("failed")]
    if not usable:
        return None
    return min(usable, key=rank_key)


def judge_latest(ledger):
    """마지막 판이 최고점 판이 아니면 rollback(그 patch 는 효과 없음으로 본다). critic 전에는 미정(None)."""
    if not ledger["rounds"]:
        return
    latest = ledger["rounds"][-1]
    if latest.get("failed") or latest.get("score") is None:
        # 실패로 센 판 · critic 전 판은 판정하지 않는다.
        latest["rollback"] = None
        return
    best = best_round(ledger)
    latest["rollback"] = best is None or best["round"] != latest["round"]


def trailing_rollbacks(ledger):
    """끝에서부터 이어진 rollback 수. 실패로 센 판은 건너뛴다(정체 셈에서 뺀다)."""
    count = 0
    for entry in reversed(ledger["rounds"]):
        if entry.get("failed"):
            continue
        if not entry.get("rollback"):
            break
        count += 1
    return count


def is_clean(entry):
    score = entry.get("score")
    if entry.get("failed") or score is None:
        return False
    return entry["errors"] == 0 and entry["warns"] == 0 and float(score) >= CLEAN_SCORE


def stop_reason(ledger):
    """멈출 까닭. 없으면 None. clean · max_rounds · stalled 중 앞선 것."""
    rounds = ledger["rounds"]
    if not rounds:
        return None
    if is_clean(rounds[-1]):
        return "clean"
    if len(rounds) >= ledger["max_rounds"]:
        return "max_rounds"
    if trailing_rollbacks(ledger) >= STALL_ROLLBACKS:
        return "stalled"
    return None


def read_critic(path):
    """critic.json {"score": 0~1, "symptoms": [...], "notes": "..."} 을 읽어 검사한다."""
    critic = read_json(path)
    if not isinstance(critic, dict):
        raise VfxError(f"critic.json 이 JSON 객체가 아니다 — {path}")
    score = critic.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 1:
        raise VfxError(f"critic score 는 0~1 숫자여야 한다 — {score!r}")
    symptoms = critic.get("symptoms", [])
    if not isinstance(symptoms, list):
        raise VfxError("critic symptoms 는 배열이어야 한다")
    return critic


def attach_critic(entry, critic):
    entry["score"] = float(critic["score"])
    entry["symptoms"] = list(critic.get("symptoms", []))


def summary(ledger, loop_dir):
    """보고 metrics 에 싣는 장부 요약."""
    best = best_round(ledger)
    best_info = None
    if best is not None:
        folder = round_dir(loop_dir, best["round"])
        best_info = {"round": best["round"], "dir": str(folder), "sheet": str(folder / "sheet.png"),
                     "errors": best["errors"], "warns": best["warns"], "score": best.get("score")}
    discarded = [entry["patch"] for entry in ledger["rounds"] if entry.get("rollback") and entry.get("patch")]
    return {
        "loop": str(Path(loop_dir) / LEDGER),
        "rounds_used": len(ledger["rounds"]),
        "max_rounds": ledger["max_rounds"],
        "best": best_info,
        "discarded_patches": discarded,
        "stopped": ledger["stopped"],
        "stop_reason": ledger["stop_reason"],
    }
