"""소재 묶음 메타 — 11장 모두 · tiles × cell = PNG 크기 · CC-BY 없음 · cut 소재는 sources.json 에 있음."""

import json

import pytest
from PIL import Image

from vfxtool import lib_cut, material_lib
from vfxtool.errors import VfxError

ALL = ("bolt32", "burst16", "cross", "disc", "dot", "puff16", "puff8", "ring", "shard", "star4", "streak")


def test_eleven_materials():
    assert material_lib.names() == sorted(ALL)


def test_meta_shape_and_png_size():
    for name in ALL:
        meta = material_lib.load(name)
        assert material_lib.meta_problem(meta, name) is None
        with Image.open(material_lib.path(name)) as image:
            assert image.size == (meta["tiles"][0] * meta["cell"], meta["tiles"][1] * meta["cell"])
        assert "BY" not in meta["license"].upper()


def test_cut_materials_listed_in_sources():
    sources = lib_cut.load_sources()
    cut = [name for name in ALL if material_lib.load(name)["made"] == "cut"]
    assert sorted(cut) == ["burst16", "puff16", "puff8"]
    for name in cut:
        entry = lib_cut.entry_for(name, sources)
        assert entry["license"].startswith("CC0")
        assert material_lib.load(name)["source"] == name
        assert len(entry["sha256"]) == 64


def test_lib_prefix_helpers():
    assert material_lib.is_lib("lib:ring") and not material_lib.is_lib("px1")
    assert material_lib.lib_name("lib:ring") == "ring"
    assert material_lib.is_inside(material_lib.path("ring"))
    assert not material_lib.is_inside("C:/elsewhere/ring.png")


def _fake_lib(tmp_path, name="fake", cell=4, png=True):
    """tmp 소재 폴더 — 메타 한 장(+ PNG)."""
    meta = {"name": name, "cell": cell, "tiles": [1, 1], "frames": 1, "rows": 1, "kind": "grain", "variants": [],
            "blend": "alpha", "made": "draw", "source": "", "license": "CC0 1.0"}
    lib = tmp_path / "lib"
    lib.mkdir(exist_ok=True)
    (lib / f"{name}.json").write_text(json.dumps(meta), encoding="utf-8")
    if png:
        Image.new("RGBA", (4, 4)).save(lib / f"{name}.png")
    return lib, meta


def test_path_needs_png(tmp_path):
    lib, _ = _fake_lib(tmp_path, png=False)
    with pytest.raises(VfxError):
        material_lib.path("fake", lib)


@pytest.mark.parametrize("cell", [0, -1, 2.5, "4", True, None])
def test_meta_cell_must_be_positive_int(tmp_path, cell):
    _, meta = _fake_lib(tmp_path)
    meta["cell"] = cell
    assert material_lib.meta_problem(meta, "fake") is not None


def test_tones_only_on_cut(tmp_path):
    _, meta = _fake_lib(tmp_path)
    meta["tones"] = 1
    assert material_lib.meta_problem(meta, "fake") is not None  # made=draw 에 tones
    meta["made"] = "cut"
    assert material_lib.meta_problem(meta, "fake") is None
    meta["tones"] = 3
    assert material_lib.meta_problem(meta, "fake") is not None


def test_is_inside_refuses_dotdot_and_metaless_png(tmp_path):
    lib, _ = _fake_lib(tmp_path)
    good = (lib / "fake.png").resolve()
    assert material_lib.is_inside(good, lib)
    # 글자와 실제 자리가 다른 경로 — lib/../lib/fake.png · lib/../x.png
    assert not material_lib.is_inside(f"{lib.as_posix()}/../lib/fake.png", lib)
    Image.new("RGBA", (4, 4)).save(tmp_path / "x.png")
    assert not material_lib.is_inside(f"{lib.as_posix()}/../x.png", lib)
    # 메타 없는 PNG
    Image.new("RGBA", (4, 4)).save(lib / "stray.png")
    assert not material_lib.is_inside((lib / "stray.png").resolve(), lib)
    # 없는 파일
    assert not material_lib.is_inside((lib / "none.png").resolve(), lib)
