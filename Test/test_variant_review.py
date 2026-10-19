"""변형 묶음 리뷰 반영 — 긴 이름 판 · 펼치기 도중 오류 · 배수 상한 · --force 같은 묶음 · set.lock · 장부 꼴 · timing · 경계값."""

import json
import os
import subprocess
import sys

import pytest

from conftest import SRC, write_set
from vfxtool import template, variant_expand, variant_run, variant_sheet
from vfxtool.errors import VfxError
from vfxtool.loop_pipeline import RoundOutcome
from vfxtool.variant_dict import MAX_BYTES, load_all
from vfxtool.variant_expand import expand_set
from vfxtool.variant_ramp import lib_src_root
from vfxtool.variant_set import INT32_MAX, INT32_MIN, LOCK_FILE, SetLocked, ledger_entries, read_ledger

LONG = "a" * 24


def _by_name(ledger):
    return {entry["name"]: entry for entry in ledger["variants"]}


def _cli(*args):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC)
    done = subprocess.run([sys.executable, "-m", "vfxtool", "variant", *args], capture_output=True, env=env, timeout=60)
    return done.returncode, json.loads(done.stdout.decode("utf-8"))


def _rewrite(path, **fields):
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(fields)
    path.write_text(json.dumps(data), encoding="utf-8")


def _ok_pipeline(calls):
    def pipeline(folder, settings):
        calls.append(folder.name)
        return RoundOutcome([], [], False)
    return pipeline


# ── 1. 40자 넘는 판 이름 ──

def test_long_name_variant_does_not_block_run_and_sheet(tmp_path, monkeypatch):
    path = write_set(tmp_path / "in", name=LONG, attrs=["lightning"], tiers=["weak", "strong"], seeds=1)
    ledger_path, ledger = expand_set(path, tmp_path / "work")
    long_name = f"{LONG}_lightning_strong"
    assert _by_name(ledger)[long_name]["issues"][0]["rule"] == "variant.name"
    project = tmp_path / "proj"
    project.mkdir()
    calls = []
    monkeypatch.setattr(variant_run, "run_pipeline", _ok_pipeline(calls))
    monkeypatch.setattr(variant_run, "preflight", lambda project, unity: None)
    _, ran, _ = variant_run.run_set(ledger_path.parent, project)
    assert calls == [f"{LONG}_lightning_weak"]
    assert _by_name(ran)[long_name]["state"] == "failed"
    made, _ = variant_sheet.make_sheets(ledger_path.parent)
    assert [p.name for p, _ in made] == ["overview.png", "strips_1.png"]


def test_ledger_name_limit_is_61():
    longest = "a" * 24 + "_" + "b" * 16 + "_" + "c" * 16 + "_s3"
    assert len(longest) == 61
    assert ledger_entries({"variants": [{"name": longest}]})
    with pytest.raises(VfxError, match="1~61"):
        ledger_entries({"variants": [{"name": longest + "x"}]})
    with pytest.raises(VfxError, match="1~61"):
        ledger_entries({"variants": [{"name": "../up"}]})


# ── 2. 펼치기 도중 오류 ──

def test_unexpected_error_fails_only_that_variant(tmp_path, monkeypatch):
    real = variant_expand._recipe

    def broken(plan, spec, params, override):
        if plan["name"] == "hit_fire_mid":
            raise RuntimeError("boom\n두 번째 줄")
        return real(plan, spec, params, override)

    monkeypatch.setattr(variant_expand, "_recipe", broken)
    path = write_set(tmp_path / "in", attrs=["fire"], tiers=["weak", "mid", "strong"], seeds=1)
    ledger_path, ledger = expand_set(path, tmp_path / "work")
    entries = _by_name(ledger)
    assert entries["hit_fire_mid"]["state"] == "failed"
    item = entries["hit_fire_mid"]["issues"][0]
    assert item["rule"] == "variant.error"
    assert "RuntimeError: boom" in item["detail"] and "두 번째" not in item["detail"]
    assert entries["hit_fire_weak"]["state"] == entries["hit_fire_strong"]["state"] == "expanded"
    assert ledger_path.is_file()
    assert not (ledger_path.parent / "hit_fire_mid").exists()


def test_set_error_while_planning_writes_nothing(tmp_path, monkeypatch):
    seen = []

    def short(recipe, view, template_dirs):
        seen.append(recipe["name"])
        if len(seen) == 2:
            raise VfxError("묶음 오류")
        return []

    monkeypatch.setattr(variant_expand, "_palette_short", short)
    path = write_set(tmp_path / "in", attrs=["fire"], tiers=["weak", "mid", "strong"], seeds=1)
    with pytest.raises(VfxError, match="묶음 오류"):
        expand_set(path, tmp_path / "work")
    assert not (tmp_path / "work").exists()


def test_error_while_writing_keeps_set_json_and_force_recovers(tmp_path, monkeypatch):
    real = variant_expand.run_check

    def broken(recipe, *args):
        if recipe["name"] == "hit_fire_weak":
            raise OSError("디스크 오류")
        return real(recipe, *args)

    monkeypatch.setattr(variant_expand, "run_check", broken)
    path = write_set(tmp_path / "in", attrs=["fire"], tiers=["weak", "mid"], seeds=1)
    _, ledger = expand_set(path, tmp_path / "work")
    assert _by_name(ledger)["hit_fire_weak"]["issues"][0]["rule"] == "variant.error"
    assert _by_name(ledger)["hit_fire_mid"]["state"] == "expanded"
    monkeypatch.setattr(variant_expand, "run_check", real)
    _, again = expand_set(path, tmp_path / "work", force=True)
    assert {entry["state"] for entry in again["variants"]} == {"expanded"}


# ── 3 · 7. 세기 배수 ──

@pytest.mark.parametrize("mul, words", [({"count": 101}, "100"), ({"count": 1e300}, "100"), ({"sparks_size": 2}, "scale")])
def test_inline_tier_mul_refused(tmp_path, mul, words):
    path = write_set(tmp_path / "in", tiers=[{"name": "huge", "mul": mul}], seeds=1)
    with pytest.raises(VfxError, match=words):
        expand_set(path, tmp_path / "work")
    assert not (tmp_path / "work").exists()


def test_tier_mul_100_is_allowed_but_range_fails(tmp_path):
    path = write_set(tmp_path / "in", attrs=["fire"], tiers=[{"name": "huge", "mul": {"count": 100}}], seeds=1)
    _, ledger = expand_set(path, tmp_path / "work")
    assert ledger["variants"][0]["issues"][0]["rule"] == "variant.tier_range"


def test_template_tier_on_size_pair_refused():
    params = {"tex": {"type": "file", "size": "tex_size"}, "tex_size": {"type": "int"}, "count": {"type": "int"}}
    assert "scale" in template.tier_problem({"mul": {"tex_size": 2}}, params)
    assert template.tier_problem({"mul": {"count": 2}}, params) is None


def test_scaled_overflow_is_none():
    assert variant_expand._scaled(1e308, 10, "float") is None
    assert variant_expand._scaled(1e308, 10, "int") is None
    assert variant_expand._scaled(7, 1.5, "int") == 11


# ── 4. --force 는 같은 묶음으로만 ──

@pytest.mark.parametrize("fields", [{"seed": 2000}, {"params": {"ring": False}}, {"duration": 0.5},
                                    {"tiers": ["weak", {"name": "mid", "mul": {"count": 2}}]}])
def test_force_with_changed_source_exits(tmp_path, fields):
    path = write_set(tmp_path / "in", attrs=["fire"], tiers=["weak", "mid"], seeds=1)
    expand_set(path, tmp_path / "work")
    _rewrite(path, **fields)
    with pytest.raises(VfxError, match="새 name"):
        expand_set(path, tmp_path / "work", force=True)


def test_force_allows_reordered_and_added_attrs_tiers(tmp_path):
    path = write_set(tmp_path / "in", attrs=["fire"], tiers=["weak", "mid"], seeds=1)
    expand_set(path, tmp_path / "work")
    _rewrite(path, attrs=["ice", "fire"], tiers=["mid", "weak", "strong"])
    _, ledger = expand_set(path, tmp_path / "work", force=True)
    assert len(ledger["variants"]) == 6
    assert ledger["source"]["attrs"] == ["ice", "fire"]


# ── 5. expand --force 도 set.lock 을 쥔다 ──

def test_force_respects_set_lock(tmp_path):
    path = write_set(tmp_path / "in", attrs=["fire"], tiers=["mid"], seeds=1)
    ledger_path, _ = expand_set(path, tmp_path / "work")
    lock = ledger_path.parent / LOCK_FILE
    lock.write_text("", encoding="utf-8")
    with pytest.raises(SetLocked):
        expand_set(path, tmp_path / "work", force=True)
    assert lock.exists()
    code, report = _cli("expand", str(path), "--work", str(tmp_path / "work"), "--force")
    assert code == 2
    assert report["issues"][0]["rule"] == "variant.locked"
    lock.unlink()
    expand_set(path, tmp_path / "work", force=True)
    assert not lock.exists()


def test_run_releases_lock_on_unexpected_error(tmp_path, monkeypatch):
    path = write_set(tmp_path / "in", attrs=["fire"], tiers=["mid"], seeds=1)
    ledger_path, _ = expand_set(path, tmp_path / "work")
    project = tmp_path / "proj"
    project.mkdir()

    def explode(folder, settings):
        raise RuntimeError("Unity 가 이상하다")

    monkeypatch.setattr(variant_run, "run_pipeline", explode)
    monkeypatch.setattr(variant_run, "preflight", lambda project, unity: None)
    with pytest.raises(RuntimeError):
        variant_run.run_set(ledger_path.parent, project)
    assert not (ledger_path.parent / LOCK_FILE).exists()


# ── 12. 장부 · measure 꼴 ──

def test_ledger_not_object_exits(tmp_path):
    out = tmp_path / "hit"
    out.mkdir()
    (out / "set.json").write_text("[]", encoding="utf-8")
    with pytest.raises(VfxError, match="객체"):
        read_ledger(out)
    with pytest.raises(VfxError, match="객체"):
        variant_sheet.make_sheets(out)


def test_measure_not_object_is_blank_cell(tmp_path):
    out = tmp_path / "hit"
    (out / "hit_fire_mid").mkdir(parents=True)
    (out / "hit_fire_mid" / "measure.json").write_text("[1]", encoding="utf-8")
    entry = {"name": "hit_fire_mid", "attr": "fire", "tier": "mid", "k": 0, "seed": 1, "state": "done",
             "errors": 0, "warns": 0, "issues": [], "notes": [], "seconds": None}
    (out / "set.json").write_text(json.dumps({"name": "hit", "variants": [entry]}), encoding="utf-8")
    made, issues = variant_sheet.make_sheets(out)
    assert [item["rule"] for item in issues] == ["variant.sheet"]
    assert made


# ── 13. timing ──

def test_timing_skips_variants_without_unity_time():
    entries = [
        {"state": "done", "seconds": {"wall": 20.0, "unity_build": 1.0, "unity_render": None}},
        {"state": "done", "seconds": {"wall": 50.0, "unity_build": None, "unity_render": None}},
    ]
    summary = variant_run.timing(entries)
    assert (summary["measured"], summary["wall_total"]) == (1, 20.0)
    assert variant_run.timing(entries[1:]) is None
    assert variant_run.timing_issues(None) == []


# ── 17. 경계값 ──

@pytest.mark.parametrize("seed, seeds, ok", [(INT32_MAX - 16, 2, True), (INT32_MAX - 15, 2, False),
                                             (INT32_MIN, 1, True), (INT32_MIN - 1, 1, False)])
def test_seed_int32_boundary(tmp_path, seed, seeds, ok):
    path = write_set(tmp_path / "in", attrs=["fire"], tiers=["mid"], seed=seed, seeds=seeds)
    if ok:
        _, ledger = expand_set(path, tmp_path / "work")
        assert ledger["variants"][-1]["seed"] == seed + (seeds - 1) * 16
        return
    with pytest.raises(VfxError, match="int 범위"):
        expand_set(path, tmp_path / "work")


def test_set_file_size_limit(tmp_path):
    path = write_set(tmp_path / "in", attrs=["fire"], tiers=["mid"], seeds=1)
    data = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(data) + " " * MAX_BYTES, encoding="utf-8")
    with pytest.raises(VfxError, match="KB"):
        expand_set(path, tmp_path / "work")
    assert not (tmp_path / "work").exists()


def _junction(tmp_path):
    target = tmp_path / "real"
    target.mkdir()
    link = tmp_path / "link"
    if sys.platform != "win32":
        pytest.skip("junction 은 윈도에만 있다")
    done = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
    if done.returncode != 0 or not link.exists():
        pytest.skip("junction 을 못 만들었다")
    return target, link


def test_junction_variant_folder_refused(tmp_path):
    target, link = _junction(tmp_path)
    (target / "fire.json").write_text(json.dumps({"version": 1, "name": "fire", "palette": ["#FF0000"]}), encoding="utf-8")
    with pytest.raises(VfxError, match="링크"):
        load_all([link])
    assert "fire" in load_all([target])


def test_junction_lib_src_refused(tmp_path):
    target, link = _junction(tmp_path)
    with pytest.raises(VfxError, match="--lib-src"):
        lib_src_root(link)
    assert lib_src_root(target) == target.resolve()
