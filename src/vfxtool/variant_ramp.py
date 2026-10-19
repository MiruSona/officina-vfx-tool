"""변형 판의 램프 소재 — ramp:<소재> 파라미터 바꾸기와 판 tex/ 램프 PNG 굽기(변형묶음설계 6-2).

굽기는 속성마다 한 번만 하고 같은 속성의 다음 판은 바이트를 복사한다.
"""

from pathlib import Path

from vfxtool import lib_cut
from vfxtool.errors import VfxError
from vfxtool.paths import ensure_inside, is_junction
from vfxtool.recipe import colors
from vfxtool.report import issue
from vfxtool.template_values import type_problem
from vfxtool.variant_set import TEX_DIR

WHITE = "#FFFFFF"


def _fail(rule, detail):
    return issue(rule, "error", detail)


def pair_values(spec_item, size, tiles, params, table, failures):
    """file 파라미터의 size(· tiles) 짝 값을 채운다. 크기가 범위 밖이면 variant.tier_range."""
    params[spec_item["size"]] = size
    problem = type_problem(table[spec_item["size"]], size)
    if problem is not None:
        failures.append(_fail("variant.tier_range", f"params.{spec_item['size']} {size} — {problem}"))
    if "tiles" in spec_item:
        params[spec_item["tiles"]] = list(tiles)


def ramp_params(name, spec_item, left_meta, material, scale, params, override, ctx, failures):
    """ramp:<소재> — 파라미터를 판 tex/ 의 램프 PNG 로, color 짝을 흰색으로. 굽기 일감을 돌려준다(6-2)."""
    sources = lib_cut.load_sources()
    if material not in sources:
        failures.append(_fail("variant.ramp_source", f"ramp:{material} — sources.json 에 없는 소재다"))
        return []
    entry = lib_cut.entry_for(material, sources)
    tiles = [entry["src_frames"], 1]
    if (left_meta["kind"], left_meta["tiles"]) != ("flipbook", tiles):
        failures.append(_fail("variant.material", f"ramp:{material} 의 {tiles} 플립북이 {left_meta['name']} {left_meta['tiles']} 와 다르다"))
        return []
    params[name] = f"{TEX_DIR}/{lib_cut.ramp_file(material)}"
    pair_values(spec_item, entry["cell"] * scale, tiles, params, ctx["tdata"]["params"], failures)
    if "color" in spec_item:
        params[spec_item["color"]] = WHITE
    if "tiles" not in spec_item:
        # 짝 tiles 가 없는 템플릿(hit_sparks core 등)은 파일 시트 칸 수를 override 로 알린다 — lib 메타가 없으니까.
        for skeleton in ctx["tdata"]["layers"]:
            if skeleton.get("texture") == f"${name}":
                override[skeleton["name"]] = {"textureSheet": {"tiles": tiles}}
    return [{"kind": "ramp", "param": name, "material": material}]


def bake_ramp(material, plan, tex, ctx, palette):
    """속성마다 한 번만 굽고 다음 판은 바이트를 복사한다. 굽기 실패는 그 판 variant.ramp_source."""
    ramp_refs = ctx["dicts"][plan["attr"]]["data"]["ramp"]
    key = (plan["attr"], material)
    target = ensure_inside(tex / lib_cut.ramp_file(material), ctx["out"])
    if key not in ctx["ramps"]:
        ctx["ramps"][key] = _bake(material, ramp_refs, tex, ctx, palette)
    baked = ctx["ramps"][key]
    if isinstance(baked, dict):
        return [baked]
    tex.mkdir(parents=True, exist_ok=True)
    if not target.is_file() or target.read_bytes() != baked:
        target.write_bytes(baked)
    return []


def _bake(material, ramp_refs, tex, ctx, palette):
    """램프 PNG 바이트, 아니면 실패 issue dict."""
    if ctx["lib_src"] is None:
        return _fail("variant.ramp_source", f"ramp:{material} — --lib-src(원본 폴더)를 안 줬다")
    hexes = []
    for ref in ramp_refs:
        index = colors.palette_index(ref)
        if index is None or index >= len(palette):
            return _fail("variant.ramp_source", f"ramp:{material} — 램프 번호 {ref} 가 팔레트({len(palette)}색) 밖이다")
        hexes.append(palette[index][:7])
    try:
        src_root = lib_src_root(ctx["lib_src"])
        entry = lib_cut.entry_for(material, lib_cut.load_sources())
        source = ensure_inside(src_root / entry["file"], src_root)
        _, problem, _, _ = lib_cut.cut_ramp(source, material, tex, hexes)
    except VfxError as exc:
        return _fail("variant.ramp_source", f"ramp:{material} — {exc.message}")
    if problem is not None:
        return _fail("variant.ramp_source", f"ramp:{material} — {problem}")
    return (tex / lib_cut.ramp_file(material)).read_bytes()


def lib_src_root(lib_src):
    """--lib-src 폴더 — 있는 보통 폴더(심볼릭 링크 · junction 거절)."""
    root = Path(lib_src)
    if root.is_symlink() or is_junction(root) or not root.is_dir():
        raise VfxError(f"--lib-src 는 있는 보통 폴더여야 한다 : {lib_src}")
    return root.resolve()
