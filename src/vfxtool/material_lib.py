"""소재 묶음(lib) — 메타 읽기 · `lib:<이름>` → PNG 절대 경로(소재묶음설계 2 · 4절). 레시피 층 검사는 check_rules 몫.

소재는 `vfxtool/lib/<이름>.png` + `<이름>.json`(메타) 한 쌍이다. lib/ 는 데이터 폴더라 py 를 두지 않는다.
Python 이 `lib:` 를 다 풀어 resolved.json 에는 절대 경로 · tiles 만 넘긴다 — C# 은 lib 를 모른다.
"""

from pathlib import Path

from vfxtool.errors import VfxError
from vfxtool.paths import read_json

LIB_DIR = Path(__file__).resolve().parent / "lib"
PREFIX = "lib:"
SOURCES_FILE = "sources.json"
RULE = "recipe.lib"
META_KEYS = ("name", "cell", "tiles", "frames", "rows", "kind", "variants", "blend", "made", "source", "license")
TONES_KEY = "tones"  # 자른 소재(made=cut)만 끝에 붙인다 — 몇 단으로 잘랐나(재현용)
KINDS = ("grain", "flipbook")


def is_lib(texture):
    return isinstance(texture, str) and texture.startswith(PREFIX)


def lib_name(texture):
    """`lib:ring` → `ring`."""
    return texture[len(PREFIX):]


def names(lib_dir=LIB_DIR):
    """소재 이름 목록(메타 JSON 이 있는 것). sources.json 은 소재가 아니다."""
    return sorted(p.stem for p in Path(lib_dir).glob("*.json") if p.name != SOURCES_FILE)


def load(name, lib_dir=LIB_DIR):
    """메타 dict. 모르는 이름 · 꼴이 틀린 메타는 VfxError."""
    if name not in names(lib_dir):
        raise VfxError(f"모르는 소재 {name!r} (있는 것 : {names(lib_dir)})")
    meta = read_json(Path(lib_dir) / f"{name}.json")
    problem = meta_problem(meta, name)
    if problem is not None:
        raise VfxError(f"소재 메타가 틀렸다 ({name}.json) : {problem}")
    return meta


def meta_problem(meta, name):
    """메타 꼴이 맞으면 None, 아니면 사람 말. 시험과 load 가 같이 쓴다."""
    if not isinstance(meta, dict) or list(meta) not in (list(META_KEYS), [*META_KEYS, TONES_KEY]):
        return f"칸이 {list(META_KEYS)} 순서여야 한다(자른 소재는 끝에 {TONES_KEY!r})"
    if TONES_KEY in meta and (meta["made"] != "cut" or meta[TONES_KEY] not in (1, 2)):
        return f"{TONES_KEY} 는 자른 소재(made=cut)에만 1 · 2 로 적는다"
    if meta["name"] != name:
        return f"name {meta['name']!r} 이 파일 이름과 다르다"
    cell = meta["cell"]
    if not (isinstance(cell, int) and not isinstance(cell, bool) and cell >= 1):
        return f"cell {cell!r} 은 1 이상 정수여야 한다"
    tiles = meta["tiles"]
    if not (isinstance(tiles, list) and len(tiles) == 2 and tiles == [meta["frames"], meta["rows"]]):
        return "tiles 는 [frames, rows] 여야 한다"
    if meta["kind"] not in KINDS:
        return f"kind 는 {list(KINDS)} 중 하나"
    if meta["variants"] and len(meta["variants"]) != meta["rows"]:
        return "variants 는 비었거나 줄 수만큼 있어야 한다"
    return None


def path(name, lib_dir=LIB_DIR):
    """소재 PNG 절대 경로(슬래시 꼴은 resolve 가 붙인다). 메타만 있고 PNG 가 없으면 VfxError."""
    load(name, lib_dir)
    png = (Path(lib_dir) / f"{name}.png").resolve()
    if not png.is_file():
        raise VfxError(f"소재 {name!r} 의 PNG 가 없다 : {png.as_posix()} — `vfxtool lib build` 로 다시 만든다")
    return png


def is_inside(texture_path, lib_dir=LIB_DIR):
    """절대 경로가 소재 폴더 바로 아래의 메타 있는 PNG 인가 — render 가 resolved.json 을 다시 검사할 때 감옥 예외로 쓴다.

    resolve 한 실제 경로가 적힌 글자와 똑같아야 한다 — `lib/../x.png` · 중간 폴더 symlink 처럼
    글자와 실제 자리가 다른 경로는 다 거절한다(검사와 사용 사이 바꿔치기 틈을 좁힌다).
    """
    candidate = Path(texture_path)
    if not candidate.is_absolute() or candidate.suffix != ".png":
        return False
    try:
        real = candidate.resolve(strict=True)
        lib_real = Path(lib_dir).resolve(strict=True)
    except OSError:
        return False
    if str(real) != str(candidate) or real.parent != lib_real:
        return False
    return real.stem in names(lib_real)


def frames_of(meta, sheet):
    """한 생에 넘기는 장 수. row 를 고르면 한 줄(frames), 아니면 시트 전체."""
    if sheet is not None and "row" in sheet:
        return meta["frames"]
    return meta["frames"] * meta["rows"]

