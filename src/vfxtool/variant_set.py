"""변형 묶음 JSON 읽기 · 검사 · 다듬기(변형묶음설계 2-1 · 3-3 · 4-2 · 4-3)와 set.json 장부 읽기 · set.lock · --force 같은 묶음 검사.

여기서 걸리는 것은 모두 「묶음이 틀렸다」라 VfxError(종료 2) — 판 하나만 틀린 것은 variant_expand 가 판별로 적는다.
"""

import copy
import re
from pathlib import Path

from vfxtool import template
from vfxtool.errors import VfxError
from vfxtool.paths import exclusive_lock, read_json
from vfxtool.recipe import values
from vfxtool.template_values import param_values
from vfxtool.variant_dict import BASE, NAME_RE

SET_KEYS = ("version", "name", "template", "profile", "duration", "fixedTimeStep", "seed", "params", "preset", "attrs", "tiers", "seeds")
SET_NAME_RE = re.compile(r"[a-z0-9_]{1,24}")
INLINE_TIER_KEYS = {"name", "mul", "scale"}
MAX_VARIANTS = 48
MAX_SEEDS = 4
SEED_STEP = 16  # C# 이 층마다 seed + 층 번호를 쓴다(층 상한 6) — 이웃 판 층끼리 난수가 겹치지 않게
INT32_MIN = -(2 ** 31)
INT32_MAX = 2 ** 31 - 1
DEFAULT_DURATION = 1.0
SET_FILE = "set.json"
LOCK_FILE = "set.lock"
RECIPE_FILE = "recipe.json"
PROFILE_FILE = "profile.json"
TEX_DIR = "tex"
STATES = ("expanded", "failed", "done")
# 판 이름 = 묶음 name(24) _ 속성(16) _ 세기(16) _s3 → 61자. 40자 넘는 판은 variant.name 실패로 장부에 남는다.
VARIANT_NAME_RE = re.compile(r"[a-z0-9_]{1,61}")
# --force 때 옛 set.json source 와 같아야 하는 칸(안 적었을 때 값). 다르면 done 판이 옛 값으로 남는다.
SAME_SOURCE = {"template": None, "profile": None, "duration": None, "fixedTimeStep": True, "seed": 1, "params": {}, "preset": None}


class SetLocked(VfxError):
    """다른 variant run · expand --force 가 같은 묶음을 쥐고 있다(set.lock)."""

    def __init__(self, lock_file):
        super().__init__(f"다른 variant run · expand 가 돌고 있다 — {lock_file} (끝났는데 남았으면 지운다)")
        self.lock_file = lock_file


def locked(set_dir):
    """set.lock 을 쥔다(loop_state.locked 와 같은 paths.exclusive_lock)."""
    return exclusive_lock(Path(set_dir) / LOCK_FILE, SetLocked)


def read_ledger(set_dir):
    """<묶음 폴더>/set.json 을 읽어 꼴을 본다. 객체가 아니거나 판 이름이 틀리면 VfxError."""
    ledger = read_json(Path(set_dir) / SET_FILE)
    if not isinstance(ledger, dict):
        raise VfxError(f"{SET_FILE} 은 JSON 객체여야 한다 : {set_dir}")
    ledger_entries(ledger)
    return ledger


def ledger_entries(ledger):
    """set.json 판 칸 목록. 판 이름은 폴더 이름으로 쓰므로 글자 꼴을 다시 본다(손으로 고친 장부 막기)."""
    entries = ledger.get("variants") if isinstance(ledger, dict) else None
    if not isinstance(entries, list) or not entries:
        raise VfxError(f"{SET_FILE} 에 판 목록(variants)이 없다")
    for entry in entries:
        name = entry.get("name") if isinstance(entry, dict) else None
        if not isinstance(name, str) or VARIANT_NAME_RE.fullmatch(name) is None:
            raise VfxError(f"{SET_FILE} 판 이름 {name!r} 는 [a-z0-9_] 1~61자여야 한다")
        if entry.get("state") not in STATES:
            raise VfxError(f"{SET_FILE} 판 {name} 의 state {entry.get('state')!r} 는 {list(STATES)} 중 하나여야 한다")
        for key in ("issues", "notes"):
            if not isinstance(entry.get(key), list):
                raise VfxError(f"{SET_FILE} 판 {name} 의 {key} 는 목록이어야 한다")
    return entries


def read_set(data, templates, dicts):
    """원본 묶음 dict → 다듬은 spec. tiers 는 [{name, mul, scale}] 로 푼다."""
    if not isinstance(data, dict):
        raise VfxError("변형 묶음은 JSON 객체여야 한다")
    extra = sorted(set(data) - set(SET_KEYS))
    if extra:
        raise VfxError(f"변형 묶음에 모르는 칸 {extra} (쓸 수 있는 칸 {list(SET_KEYS)})")
    if data.get("version") != 1:
        raise VfxError("변형 묶음 version 은 1 이어야 한다")
    for key in ("template", "profile", "attrs", "tiers"):
        if key not in data:
            raise VfxError(f"변형 묶음에 {key} 가 없다")
    template_name = data["template"]
    if not isinstance(template_name, str) or template_name not in templates:
        raise VfxError(f"모르는 템플릿 {template_name!r} (있는 것 : {sorted(templates)})")
    tdata = templates[template_name]["data"]
    spec = {
        "name": _set_name(data.get("name", template_name)),
        "template": template_name,
        "profile": _text(data["profile"], "profile"),
        "duration": _duration(data.get("duration"), tdata),
        "fixedTimeStep": _flag(data.get("fixedTimeStep", True), "fixedTimeStep"),
        "seed": _int(data.get("seed", 1), "seed"),
        "params": copy.deepcopy(data.get("params", {})),
        "preset": data.get("preset"),
        "attrs": _attrs(data["attrs"], dicts),
        "tiers": _tiers(data["tiers"], tdata),
        "seeds": _int(data.get("seeds", 1), "seeds"),
        "loop": _loop(tdata),
    }
    _check_params(spec, tdata)
    if not 1 <= spec["seeds"] <= MAX_SEEDS:
        raise VfxError(f"seeds 는 1 ~ {MAX_SEEDS} 이어야 한다 (지금 {spec['seeds']})")
    last_seed = spec["seed"] + (spec["seeds"] - 1) * SEED_STEP
    if spec["seed"] < INT32_MIN or last_seed > INT32_MAX:
        raise VfxError(f"seed {spec['seed']} + (seeds−1)×{SEED_STEP} 가 int 범위({INT32_MIN} ~ {INT32_MAX}) 밖이다")
    total = len(spec["attrs"]) * len(spec["tiers"]) * spec["seeds"]
    if total > MAX_VARIANTS:
        raise VfxError(f"판 수 {total} (attrs × tiers × seeds) 가 상한 {MAX_VARIANTS} 를 넘는다")
    return spec


def _set_name(name):
    if not isinstance(name, str) or SET_NAME_RE.fullmatch(name) is None:
        raise VfxError(f"묶음 name {name!r} 는 [a-z0-9_] 1~24자여야 한다 — 판 이름 앞머리 · 폴더 이름으로 쓴다")
    return name


def _text(value, key):
    if not isinstance(value, str) or not value:
        raise VfxError(f"변형 묶음 {key} 는 빈칸 아닌 글이어야 한다")
    return value


def _flag(value, key):
    if not isinstance(value, bool):
        raise VfxError(f"변형 묶음 {key} 는 true/false 여야 한다")
    return value


def _int(value, key):
    if isinstance(value, bool) or not isinstance(value, int):
        raise VfxError(f"변형 묶음 {key} 는 정수여야 한다 (지금 {value!r})")
    return value


def _duration(value, tdata):
    """안 적으면 템플릿 max_duration 상한, 그것도 없으면 DEFAULT_DURATION."""
    if value is None:
        for rule in tdata.get("check", []):
            if rule["rule"] == "max_duration":
                return rule["args"]["max"]
        return DEFAULT_DURATION
    if not values.is_number(value) or value <= 0:
        raise VfxError(f"변형 묶음 duration 은 0 보다 큰 숫자여야 한다 (지금 {value!r})")
    return value


def _loop(tdata):
    """템플릿 loop 규칙이 있으면 그 값을 레시피 loop 칸에 넣는다(없으면 None — 칸을 안 적는다)."""
    for rule in tdata.get("check", []):
        if rule["rule"] == "loop":
            return rule.get("args", {}).get("value", True)
    return None


def _attrs(attrs, dicts):
    if not isinstance(attrs, list) or not attrs:
        raise VfxError("변형 묶음 attrs 는 속성 이름 목록이어야 한다")
    for name in attrs:
        if not isinstance(name, str) or NAME_RE.fullmatch(name) is None:
            raise VfxError(f"속성 이름 {name!r} 는 [a-z0-9_] 1~16자여야 한다")
        if name != BASE and name not in dicts:
            raise VfxError(f"모르는 속성 {name!r} (있는 것 : {[BASE] + sorted(dicts)})")
    if len(set(attrs)) != len(attrs):
        raise VfxError(f"attrs 에 같은 속성이 두 번 있다 : {attrs}")
    return list(attrs)


def _tiers(tiers, tdata):
    """[이름 | {name, mul, scale}] → [{name, mul, scale}]. 이름은 템플릿 tiers 에서 찾는다."""
    if not isinstance(tiers, list) or not tiers:
        raise VfxError("변형 묶음 tiers 는 세기 이름(또는 즉석 세기 객체) 목록이어야 한다")
    table = tdata.get("tiers", {})
    found = []
    for item in tiers:
        if isinstance(item, str):
            if item not in table:
                raise VfxError(f"템플릿 {tdata['name']} 에 세기 {item!r} 가 없다 (있는 것 : {sorted(table)})")
            body = table[item]
            name = item
        elif isinstance(item, dict):
            if set(item) - INLINE_TIER_KEYS or "name" not in item:
                raise VfxError(f"즉석 세기는 {sorted(INLINE_TIER_KEYS)} 칸 객체(name 필수)여야 한다 : {item!r}")
            name = item["name"]
            body = {key: item[key] for key in ("mul", "scale") if key in item}
            problem = template.tier_problem(body, tdata["params"])
            if problem is not None:
                raise VfxError(f"즉석 세기 {name!r} : {problem}")
        else:
            raise VfxError(f"tiers 항목은 세기 이름이나 객체여야 한다 : {item!r}")
        if not isinstance(name, str) or NAME_RE.fullmatch(name) is None:
            raise VfxError(f"세기 이름 {name!r} 는 [a-z0-9_] 1~16자여야 한다")
        found.append({"name": name, "mul": dict(body.get("mul", {})), "scale": body.get("scale", 1)})
    names = [tier["name"] for tier in found]
    if len(set(names)) != len(names):
        raise VfxError(f"세기 이름이 겹친다 : {names}")
    return found


def _check_params(spec, tdata):
    """묶음 params · preset 이 템플릿에 맞나 — 모든 판에 깔리는 값이라 틀리면 묶음 오류."""
    if not isinstance(spec["params"], dict):
        raise VfxError("변형 묶음 params 는 객체여야 한다")
    if spec["preset"] is not None and not isinstance(spec["preset"], str):
        raise VfxError("변형 묶음 preset 은 이름 글이거나 null 이어야 한다")
    call = {"name": spec["name"], "preset": spec["preset"], "params": spec["params"]}
    _, issues = param_values(tdata, call)
    if issues:
        raise VfxError("변형 묶음 params · preset : " + " / ".join(item["detail"] for item in issues))


def require_force(out, force):
    """이미 있는 묶음 폴더는 --force 이고 set.json 이 있을 때만 다시 쓴다."""
    if not force:
        raise VfxError(f"묶음 폴더가 이미 있다 — {out} (실패 · 남은 판만 다시 쓰려면 --force)")
    if not (out / SET_FILE).is_file():
        raise VfxError(f"--force 인데 {SET_FILE} 이 없다 — 묶음 폴더가 아니다 : {out}")


def kept_entries(out, raw, plans):
    """--force 때 그대로 둘 판(done) {이름: 옛 장부 칸}. 같은 묶음이 아니면 VfxError."""
    old_ledger = read_ledger(out)
    _check_same_source(old_ledger.get("source"), raw)
    old = {entry["name"]: entry for entry in old_ledger["variants"]}
    names = {plan["name"] for plan in plans}
    lost = sorted(name for name, entry in old.items() if entry.get("state") == "done" and name not in names)
    if lost:
        raise VfxError(f"--force 는 같은 묶음으로만 — done 인 판이 새 판 목록에 없다 : {lost}")
    strangers = sorted(name for name in names if name not in old and (out / name).exists())
    if strangers:
        raise VfxError(f"{SET_FILE} 에 없는 판 폴더가 이미 있다 — 덮어쓰지 않는다 : {strangers}")
    return {name: entry for name, entry in old.items() if entry.get("state") == "done" and name in names}


def _check_same_source(old, new):
    """판 값을 바꾸는 칸 · 같은 이름 세기의 몸이 옛 묶음과 같아야 한다. attrs · tiers · seeds 가 늘거나 순서가 바뀐 것은 된다."""
    if not isinstance(old, dict):
        raise VfxError(f"옛 {SET_FILE} 의 source 가 객체가 아니다 — 새 name 으로 펼친다")
    changed = [key for key, default in SAME_SOURCE.items() if old.get(key, default) != new.get(key, default)]
    old_tiers, new_tiers = _tier_items(old.get("tiers")), _tier_items(new.get("tiers"))
    changed += [f"tiers.{name}" for name in sorted(set(old_tiers) & set(new_tiers)) if old_tiers[name] != new_tiers[name]]
    if changed:
        raise VfxError(f"--force 는 같은 묶음으로만 — {changed} 가 옛 {SET_FILE} 과 다르다. 바꾼 묶음은 새 name 으로 펼친다")


def _tier_items(tiers):
    """원본 tiers 목록 → {세기 이름: 항목(이름 글 또는 즉석 객체)}."""
    found = {}
    if not isinstance(tiers, list):
        return found
    for item in tiers:
        if isinstance(item, dict):
            found[str(item.get("name"))] = item
        else:
            found[str(item)] = item
    return found
