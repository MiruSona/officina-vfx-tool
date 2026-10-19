"""변형 사전 — 기본 넷 · 파일 이름 = name · 모르는 칸 · 덮기 · 심볼릭 링크 · 이름 글자 · 램프 번호 · 크기 상한."""

import json

import pytest

from conftest import write_set
from vfxtool import template
from vfxtool.errors import VfxError
from vfxtool.variant_dict import MAX_BYTES, load_all
from vfxtool.variant_set import read_set

FIRE = {"version": 1, "name": "fire", "title": "불", "palette": ["#FF0000", "#880000"], "materials": {}, "ramp": ["p0", "p1"]}


def _write(folder, name, data):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_builtin_four():
    dicts = load_all()
    assert sorted(dicts) == ["fire", "ice", "lightning", "poison"]
    for entry in dicts.values():
        assert entry["source"] == "builtin"
        assert len(entry["data"]["palette"]) == 5
        assert entry["data"]["ramp"] == ["p0", "p1", "p2", "p3"]
        assert not any(right.startswith("ramp:") for right in entry["data"]["materials"].values())
        assert entry["data"]["params"] == {"color": "p2"}


def test_file_name_must_match(tmp_path):
    _write(tmp_path, "flame", FIRE)
    with pytest.raises(VfxError, match="파일 이름"):
        load_all([tmp_path])


def test_unknown_key_rejected(tmp_path):
    _write(tmp_path, "fire", {**FIRE, "colour": "red"})
    with pytest.raises(VfxError, match="모르는 칸"):
        load_all([tmp_path])


def test_game_folder_wins_whole_file(tmp_path):
    _write(tmp_path, "fire", FIRE)
    entry = load_all([tmp_path])["fire"]
    assert entry["source"] == str(tmp_path)
    assert entry["data"]["palette"] == ["#FF0000", "#880000"]
    assert entry["data"]["materials"] == {}


def test_symlink_file_rejected(tmp_path):
    target = _write(tmp_path / "real", "fire", FIRE)
    link_dir = tmp_path / "game"
    link_dir.mkdir()
    try:
        (link_dir / "fire.json").symlink_to(target)
    except OSError:
        pytest.skip("이 자리에서는 심볼릭 링크를 못 만든다")
    with pytest.raises(VfxError, match="심볼릭 링크"):
        load_all([link_dir])


@pytest.mark.parametrize("attr", ["../fire", "Fire", "fire/x", "c:fire", "a" * 17])
def test_attr_name_with_path_chars_rejected(tmp_path, attr):
    data = json.loads(write_set(tmp_path, attrs=[attr]).read_text(encoding="utf-8"))
    with pytest.raises(VfxError, match="속성 이름"):
        read_set(data, template.load_all(), load_all())


def test_unknown_attr_rejected(tmp_path):
    data = json.loads(write_set(tmp_path, attrs=["wind"]).read_text(encoding="utf-8"))
    with pytest.raises(VfxError, match="모르는 속성"):
        read_set(data, template.load_all(), load_all())


def test_ramp_index_outside_palette(tmp_path):
    _write(tmp_path, "fire", {**FIRE, "ramp": ["p0", "p2"]})
    with pytest.raises(VfxError, match="ramp"):
        load_all([tmp_path])


def test_ramp_material_needs_ramp_key(tmp_path):
    data = {key: value for key, value in FIRE.items() if key != "ramp"}
    data["materials"] = {"lib:burst16": "ramp:burst16"}
    _write(tmp_path, "fire", data)
    with pytest.raises(VfxError, match="ramp 칸"):
        load_all([tmp_path])


@pytest.mark.parametrize("right", ["burst16", "lib:../x", "file:a.png"])
def test_material_right_shape(tmp_path, right):
    _write(tmp_path, "fire", {**FIRE, "materials": {"lib:shard": right}})
    with pytest.raises(VfxError, match="materials"):
        load_all([tmp_path])


def test_bad_palette_rejected(tmp_path):
    _write(tmp_path, "fire", {**FIRE, "palette": ["red"]})
    with pytest.raises(VfxError, match="palette"):
        load_all([tmp_path])


def test_size_limit(tmp_path):
    _write(tmp_path, "fire", {**FIRE, "title": "x" * MAX_BYTES})
    with pytest.raises(VfxError, match="KB"):
        load_all([tmp_path])


def test_missing_folder(tmp_path):
    with pytest.raises(VfxError, match="없다"):
        load_all([tmp_path / "nope"])


def test_params_scalar_values_accepted(tmp_path):
    _write(tmp_path, "fire", {**FIRE, "params": {"color": "p1", "count": 3, "speed": 1.5, "ring": False, "_x": "a"}})
    assert load_all([tmp_path])["fire"]["data"]["params"]["count"] == 3


@pytest.mark.parametrize("params", [["color"], {"Color": "p1"}, {"9x": 1}, {"a-b": 1}, {"color": None}, {"color": [1, 2]}, {"color": {"v": 1}}])
def test_params_shape_rejected(tmp_path, params):
    _write(tmp_path, "fire", {**FIRE, "params": params})
    with pytest.raises(VfxError, match="params"):
        load_all([tmp_path])
