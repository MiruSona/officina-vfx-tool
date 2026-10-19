"""변형 묶음 펼치기 — 판마다 레시피 · 프로필 사본 · tex/ 를 쓰고 check 를 돌린다(변형묶음설계 4 · 6절).

판 하나 순서 : 이름 · 시드 → 프로필 사본 → 파라미터(기본 < preset < 사전 params < 묶음 params → 세기 → 소재 치환) → 레시피 → run_check.
같은 입력이면 바이트 같은 산출물이 나온다(시간 · 난수를 안 쓴다). 모든 판을 먼저 계산한 뒤 쓰므로 묶음 오류(VfxError)면 아무것도 안 쓴다.
램프 굽기는 variant_ramp, 묶음 읽기 · 장부 · 잠금은 variant_set 에 있다.
"""

import copy
import math
from pathlib import Path

from vfxtool import material_lib, template
from vfxtool.errors import VfxError
from vfxtool.paths import ensure_inside, read_json, write_json
from vfxtool.recipe import colors, schema, values
from vfxtool.recipe.check import run_check
from vfxtool.recipe.profile_view import make_view
from vfxtool.report import issue
from vfxtool.template_values import param_values, type_problem
from vfxtool.variant_dict import BASE, RAMP_PREFIX, load_all as load_dicts, read_small
from vfxtool.variant_ramp import bake_ramp, pair_values, ramp_params
from vfxtool.variant_set import PROFILE_FILE, RECIPE_FILE, SEED_STEP, SET_FILE, TEX_DIR, kept_entries, locked, read_set, require_force

LEDGER_VERSION = 1
MAX_TEXTURE_BYTES = 4 * 1024 * 1024
PROFILE_FIELDS = ("palette", "max_colors", "fx_extra")


def expand_set(set_path, work, variant_dirs=(), template_dirs=(), lib_src=None, input_root=None, force=False):
    """<work>/<name>/ 에 판 폴더 · set.json 을 쓴다. (set.json 경로, 장부 dict)."""
    source = Path(set_path).resolve()
    root = source.parent
    if input_root is not None:
        root = Path(input_root).resolve()
    templates = template.load_all(template_dirs)
    dicts = load_dicts(variant_dirs)
    raw = read_small(source, "변형 묶음")
    spec = read_set(raw, templates, dicts)
    tdata = templates[spec["template"]]["data"]
    profile_raw = _read_profile(spec["profile"], source.parent, root)
    game_files = _game_files(spec["params"], tdata["params"], source.parent, root)
    plans = _plan(spec)
    work_root = Path(work).resolve()
    out = ensure_inside(work_root / spec["name"], work_root)
    context = {
        "spec": spec, "tdata": tdata, "dicts": dicts, "profile_raw": profile_raw, "game_files": game_files,
        "template_dirs": [Path(d).resolve().as_posix() for d in template_dirs], "lib_src": lib_src, "out": out, "ramps": {},
    }
    if not out.exists():
        return _write_set(raw, plans, {}, context)
    require_force(out, force)
    # run 이 같은 묶음을 돌리는 동안 판 폴더 · set.json 을 덮지 않게 run 과 같은 set.lock 을 쥔다.
    with locked(out):
        return _write_set(raw, plans, kept_entries(out, raw, plans), context)


def _write_set(raw, plans, kept, ctx):
    """모든 판을 먼저 계산한다(묶음 오류면 여기서 멈춰 아무것도 안 쓴다). 그 뒤 판 폴더 · set.json 을 쓴다."""
    drafts = {plan["name"]: _draft_or_error(plan, ctx) for plan in plans if plan["name"] not in kept}
    entries = []
    for plan in plans:
        if plan["name"] in kept:
            entries.append(kept[plan["name"]])
            continue
        entries.append(_write_or_error(drafts[plan["name"]], ctx))
    spec = ctx["spec"]
    ledger = {
        "version": LEDGER_VERSION,
        "name": spec["name"],
        "template": spec["template"],
        "attrs": spec["attrs"],
        "tiers": [tier["name"] for tier in spec["tiers"]],
        "seeds": spec["seeds"],
        "settings": {"templates": ctx["template_dirs"]},
        "source": raw,
        "variants": entries,
    }
    out = ctx["out"]
    return write_json(ensure_inside(out / SET_FILE, out), ledger), ledger


def _read_profile(relative, set_dir, root):
    path = ensure_inside(set_dir / relative, root)
    data = read_json(path)
    if not isinstance(data, dict):
        raise VfxError(f"바탕 프로필은 JSON 객체여야 한다 : {path}")
    make_view(data, str(path))
    return data


def _game_files(params, table, set_dir, root):
    """묶음 params 의 게임 쪽 파일 텍스처 → {파라미터: 원본 경로}. PNG · 4MB · 감옥 안이어야 한다(6-3)."""
    found = {}
    for name, value in params.items():
        if table[name]["type"] != "file" or material_lib.is_lib(value):
            continue
        path = ensure_inside(set_dir / value, root)
        if path.suffix.lower() != ".png" or not path.is_file():
            raise VfxError(f"params.{name} 는 있는 PNG 파일이어야 한다 : {value}")
        if path.stat().st_size > MAX_TEXTURE_BYTES:
            raise VfxError(f"params.{name} 텍스처가 {MAX_TEXTURE_BYTES // (1024 * 1024)}MB 를 넘는다 : {value}")
        found[name] = path
    return found


def _plan(spec):
    """판 목록(속성 → 세기 → 시드 순). 이름이 겹치면 VfxError."""
    plans = []
    for attr in spec["attrs"]:
        for tier in spec["tiers"]:
            for k in range(spec["seeds"]):
                name = f"{spec['name']}_{attr}_{tier['name']}"
                if spec["seeds"] > 1:
                    name += f"_s{k}"
                plans.append({"name": name, "attr": attr, "tier": tier, "k": k, "seed": spec["seed"] + k * SEED_STEP})
    names = [plan["name"] for plan in plans]
    if len(set(names)) != len(names):
        raise VfxError(f"판 이름이 겹친다 — 속성 · 세기 이름을 바꾼다 : {sorted(n for n in set(names) if names.count(n) > 1)}")
    return plans


def _draft_or_error(plan, ctx):
    try:
        return _draft(plan, ctx)
    except VfxError:
        raise
    except Exception as exc:  # 판 하나의 뜻밖의 오류는 그 판만 failed — 다른 판 · set.json 은 그대로 간다
        return {"plan": plan, "entry": _error_entry(plan, exc)}


def _write_or_error(draft, ctx):
    if "recipe" not in draft:
        return draft["entry"]
    try:
        return _write_one(draft, ctx)
    except Exception as exc:  # 쓰기 도중 오류도 그 판만 failed — set.json 은 끝까지 쓴다
        return _error_entry(draft["plan"], exc)


def _error_entry(plan, exc):
    """뜻밖의 오류 판 — variant.error 에 오류 글 첫 줄만 적는다."""
    text = str(exc)
    if isinstance(exc, VfxError):
        text = exc.message
    lines = text.strip().splitlines() or [""]
    entry = _entry(plan, [])
    entry["state"] = "failed"
    entry["errors"] = 1
    entry["issues"] = [_fail("variant.error", f"뜻밖의 오류로 이 판을 못 펼쳤다 — {type(exc).__name__}: {lines[0]}")]
    return entry


def _entry(plan, notes):
    return {
        "name": plan["name"], "attr": plan["attr"], "tier": plan["tier"]["name"], "k": plan["k"], "seed": plan["seed"],
        "state": "expanded", "errors": 0, "warns": 0, "issues": [], "notes": notes, "seconds": None,
    }


def _draft(plan, ctx):
    """판 하나를 디스크에 안 쓰고 계산한다. 앞선 실패(이름 · 범위 · 소재 · 팔레트)는 failures 에 모은다."""
    spec = ctx["spec"]
    failures = []
    if len(plan["name"]) > schema.LAYER_NAME_MAX:
        failures.append(_fail("variant.name", f"판 이름 {plan['name']!r} 가 {schema.LAYER_NAME_MAX}자를 넘는다 — 묶음 name 을 짧게 준다"))
    attr_dict = None
    if plan["attr"] != BASE:
        attr_dict = ctx["dicts"][plan["attr"]]["data"]
    profile_data = profile_copy(ctx["profile_raw"], attr_dict)
    view = make_view(profile_data, f"{plan['name']}/{PROFILE_FILE}")
    params, override, jobs, notes = _variant_params(plan, ctx, attr_dict, view["palette"], failures)
    recipe = _recipe(plan, spec, params, override)
    if not failures:
        failures.extend(_palette_short(recipe, view, ctx["template_dirs"]))
    return {"plan": plan, "entry": _entry(plan, notes), "failures": failures, "recipe": recipe,
            "profile": profile_data, "jobs": jobs, "palette": view["palette"]}


def _write_one(draft, ctx):
    """계산해 둔 판을 쓰고 check 를 돌려 장부 칸을 돌려준다. 실패해도 폴더 · recipe.json 은 만든다(4-5)."""
    plan, entry, failures = draft["plan"], draft["entry"], draft["failures"]
    folder = ensure_inside(ctx["out"] / plan["name"], ctx["out"])
    write_json(ensure_inside(folder / RECIPE_FILE, ctx["out"]), draft["recipe"])
    write_json(ensure_inside(folder / PROFILE_FILE, ctx["out"]), draft["profile"])
    for job in draft["jobs"]:
        failures.extend(_run_job(job, plan, folder, ctx, draft["palette"]))
    entry["issues"] = failures
    if failures:
        entry["state"] = "failed"
        entry["errors"] = len(failures)
        return entry
    result = run_check(draft["recipe"], folder / RECIPE_FILE, None, folder, ctx["template_dirs"])
    errors = [item for item in result.issues if item["severity"] == "error"]
    entry["warns"] = sum(1 for item in result.issues if item["severity"] == "warn")
    if errors:
        rules = sorted({item["rule"] for item in errors})
        entry["issues"] = [_fail("variant.check", f"check error {len(errors)}건 : {', '.join(rules)}")] + result.issues
        entry["state"] = "failed"
        entry["errors"] = len(errors)
    return entry


def _fail(rule, detail):
    return issue(rule, "error", detail)


def profile_copy(raw, attr_dict):
    """바탕 프로필 원본 dict 에서 palette(· max_colors · fx_extra)만 바꾼 사본. 다른 칸 · 칸 꼴은 그대로."""
    data = copy.deepcopy(raw)
    if attr_dict is None:
        return data
    for field in PROFILE_FIELDS:
        if field not in attr_dict:
            continue
        value = copy.deepcopy(attr_dict[field])
        if isinstance(data.get(field), dict) and "value" in data[field]:
            data[field]["value"] = value
            if "source" in data[field]:
                data[field]["source"] = f"variant:{attr_dict['name']}"
        else:
            data[field] = value
    return data


def _variant_params(plan, ctx, attr_dict, palette, failures):
    """(레시피 params, override, tex 일감, notes). 범위 밖 · 소재 오류는 failures 에 더한다."""
    spec = ctx["spec"]
    table = ctx["tdata"]["params"]
    params, notes = _dict_params(attr_dict, table, failures)
    # 묶음 params 가 사전 params 를 이긴다 — 묶음은 이 판을 위한 손 덧칠이다.
    params.update(copy.deepcopy(spec["params"]))
    call = {"name": spec["name"], "preset": spec["preset"], "params": params}
    merged, _ = param_values(ctx["tdata"], call, palette)
    tier = plan["tier"]
    for name, factor in tier["mul"].items():
        scaled = _scaled(merged[name], factor, table[name]["type"])
        if scaled is None:
            failures.append(_fail("variant.tier_range", f"params.{name} {merged[name]} × {factor} 가 유한한 수가 아니다"))
            continue
        params[name] = scaled
        _range_check(name, params[name], table[name], failures)
    materials = {}
    if attr_dict is not None:
        materials = attr_dict.get("materials", {})
    used = set()
    override = {}
    jobs = []
    for name, spec_item in table.items():
        if spec_item.get("type") != "file":
            continue
        current = merged[name]
        right = materials.get(current)
        if right is not None and "size" in spec_item:
            used.add(current)
            jobs.extend(_substitute(name, spec_item, current, right, tier["scale"], params, override, ctx, failures))
            continue
        if name in ctx["game_files"]:
            params[name] = f"{TEX_DIR}/{name}.png"
            jobs.append({"kind": "copy", "param": name, "source": ctx["game_files"][name]})
        if "size" in spec_item and tier["scale"] != 1:
            size_name = spec_item["size"]
            params[size_name] = merged[size_name] * tier["scale"]
            _range_check(size_name, params[size_name], table[size_name], failures)
    notes += [issue("variant.unused_material", "info", f"안 쓴 치환 {left}") for left in sorted(set(materials) - used)]
    return params, override, jobs, notes


def _dict_params(attr_dict, table, failures):
    """사전 params 중 템플릿에 있는 것 {이름: 값} 과 안 쓴 이름 notes. 꼴 · 범위가 틀리면 variant.param."""
    found = {}
    notes = []
    if attr_dict is None:
        return found, notes
    for name, value in sorted(attr_dict.get("params", {}).items()):
        if name not in table:
            notes.append(issue("variant.unused_param", "info", f"안 쓴 파라미터 {name}"))
            continue
        problem = type_problem(table[name], value)
        if problem is not None:
            failures.append(_fail("variant.param", f"사전 {attr_dict['name']} params.{name} {value!r} — {problem}"))
            continue
        found[name] = copy.deepcopy(value)
    return found, notes


def _scaled(value, factor, kind):
    """배수 곱 — int 는 반올림(0.5 는 올림), float 은 values.DIGITS 자리. 곱이 inf · NaN 이면 None."""
    product = value * factor
    if not math.isfinite(product):
        return None
    product = round(product, values.DIGITS)
    if kind == "int":
        return int(math.floor(product + 0.5))
    return product


def _range_check(name, value, spec, failures):
    problem = type_problem(spec, value)
    if problem is not None:
        failures.append(_fail("variant.tier_range", f"params.{name} {value} — {problem}"))


def _substitute(name, spec_item, current, right, scale, params, override, ctx, failures):
    """소재 치환 한 칸(4-4). 램프면 굽기 일감 하나를 돌려준다."""
    table = ctx["tdata"]["params"]
    if not material_lib.is_lib(current):
        failures.append(_fail("variant.material", f"params.{name} {current!r} 는 lib 소재가 아니라 치환을 못 맞춘다"))
        return []
    left_meta = _meta(current, failures)
    if left_meta is None:
        return []
    if right.startswith(RAMP_PREFIX):
        return ramp_params(name, spec_item, left_meta, right[len(RAMP_PREFIX):], scale, params, override, ctx, failures)
    meta = _meta(right, failures)
    if meta is None:
        return []
    if (meta["kind"], meta["tiles"]) != (left_meta["kind"], left_meta["tiles"]):
        detail = f"{current} → {right} : kind · tiles 가 다르다 ({left_meta['kind']} {left_meta['tiles']} ≠ {meta['kind']} {meta['tiles']})"
        failures.append(_fail("variant.material", detail))
        return []
    params[name] = right
    pair_values(spec_item, meta["cell"] * scale, meta["tiles"], params, table, failures)
    return []


def _meta(texture, failures):
    try:
        return material_lib.load(material_lib.lib_name(texture))
    except VfxError as exc:
        failures.append(_fail("variant.material", f"{texture} : {exc.message}"))
        return None


def _recipe(plan, spec, params, override):
    call = {"name": spec["name"], "template": spec["template"]}
    if spec["preset"] is not None:
        call["preset"] = spec["preset"]
    call["params"] = params
    if override:
        call["override"] = override
    recipe = {
        "version": 1, "name": plan["name"], "profile": PROFILE_FILE, "seed": plan["seed"],
        "fixedTimeStep": spec["fixedTimeStep"], "duration": spec["duration"],
    }
    if spec["loop"] is not None:
        recipe["loop"] = spec["loop"]
    recipe["layers"] = [call]
    return recipe


def _palette_short(recipe, view, template_dirs):
    """레시피가 쓰는 가장 큰 p<n> 이 사본 팔레트 밖이면 variant.palette_short(fallback 적용 뒤 값으로 본다)."""
    expanded, found = template.expand(recipe, view, template_dirs)
    if found:
        return []
    top = max(_palette_refs(expanded["layers"]), default=-1)
    if top < len(view["palette"]):
        return []
    return [_fail("variant.palette_short", f"레시피가 p{top} 를 쓰는데 속성 팔레트는 {len(view['palette'])}색이다")]


def _palette_refs(node):
    if isinstance(node, list):
        for item in node:
            yield from _palette_refs(item)
    elif isinstance(node, dict):
        for item in node.values():
            yield from _palette_refs(item)
    elif isinstance(node, str):
        index = colors.palette_index(node)
        if index is not None:
            yield index


def _run_job(job, plan, folder, ctx, palette):
    """tex/ 일감 하나 — 게임 파일 복사 또는 램프 굽기. 실패는 issue 목록으로."""
    tex = ensure_inside(folder / TEX_DIR, ctx["out"])
    if job["kind"] == "copy":
        target = ensure_inside(tex / f"{job['param']}.png", ctx["out"])
        tex.mkdir(parents=True, exist_ok=True)
        target.write_bytes(job["source"].read_bytes())
        return []
    return bake_ramp(job["material"], plan, tex, ctx, palette)
