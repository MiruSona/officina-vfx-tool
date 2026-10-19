"""variant run — 가짜 run_pipeline 으로 순차 · 실패 이어감 · seconds · done · 판마다 원자 쓰기 · 잠금 · Unity 안 거절."""

import json

import pytest

from conftest import write_set
from vfxtool import report, variant_run, variant_set
from vfxtool.errors import VfxError
from vfxtool.loop_pipeline import RoundOutcome
from vfxtool.variant_expand import expand_set


def _expand(tmp_path, **fields):
    path = write_set(tmp_path / "in", **fields)
    ledger_path, _ = expand_set(path, tmp_path / "work")
    project = tmp_path / "proj"
    project.mkdir()
    return ledger_path, project


def _ledger(ledger_path):
    return json.loads(ledger_path.read_text(encoding="utf-8"))


class FakePipeline:
    """판 이름 순서 · 그때 디스크의 set.json 을 적어 둔다. fail 에 든 판은 render 실패로 돌려준다."""

    def __init__(self, ledger_path, fail=()):
        self.ledger_path = ledger_path
        self.fail = set(fail)
        self.calls = []
        self.done_on_disk = []
        self.settings = []

    def __call__(self, folder, settings):
        self.calls.append(folder.name)
        self.settings.append(settings)
        on_disk = _ledger(self.ledger_path)
        self.done_on_disk.append(sum(1 for e in on_disk["variants"] if e["state"] in ("done", "failed")))
        (folder / "result.json").write_text(json.dumps({"seconds": {"build": 0.5, "render": 1.0}}), encoding="utf-8")
        if folder.name in self.fail:
            bad = [report.issue("unity.error", "error", "가짜 실패")]
            return RoundOutcome(bad, bad, True)
        warn = [report.issue("frame.palette", "warn", "가짜 warn")]
        return RoundOutcome(warn, warn, False)


@pytest.fixture
def fake(monkeypatch):
    def install(ledger_path, fail=()):
        pipeline = FakePipeline(ledger_path, fail)
        monkeypatch.setattr(variant_run, "run_pipeline", pipeline)
        monkeypatch.setattr(variant_run, "preflight", lambda project, unity: None)
        return pipeline
    return install


def test_runs_in_name_order_and_continues_after_failure(tmp_path, fake):
    ledger_path, project = _expand(tmp_path, attrs=["fire"], tiers=["weak", "mid"], seeds=2)
    pipeline = fake(ledger_path, fail={"hit_fire_mid_s0"})
    _, ledger, issues = variant_run.run_set(ledger_path.parent, project)
    assert pipeline.calls == sorted(pipeline.calls) == ["hit_fire_mid_s0", "hit_fire_mid_s1", "hit_fire_weak_s0", "hit_fire_weak_s1"]
    assert issues == []
    states = {e["name"]: e["state"] for e in ledger["variants"]}
    assert states == {"hit_fire_weak_s0": "done", "hit_fire_weak_s1": "done", "hit_fire_mid_s0": "failed", "hit_fire_mid_s1": "done"}
    failed = next(e for e in ledger["variants"] if e["name"] == "hit_fire_mid_s0")
    assert failed["issues"][0]["rule"] == "variant.run"
    assert "unity.error" in failed["issues"][0]["detail"]
    done = next(e for e in ledger["variants"] if e["name"] == "hit_fire_weak_s0")
    assert (done["errors"], done["warns"]) == (0, 1)
    assert done["seconds"]["unity_build"] == 0.5 and done["seconds"]["unity_render"] == 1.0
    assert done["seconds"]["wall"] >= 0
    assert _ledger(ledger_path) == ledger


def test_settings_point_at_variant_folder(tmp_path, fake):
    ledger_path, project = _expand(tmp_path, attrs=["fire"], tiers=["mid"], seeds=1)
    pipeline = fake(ledger_path)
    variant_run.run_set(ledger_path.parent, project, timeout=12.0, save_root="Assets/Fx")
    settings = pipeline.settings[0]
    folder = (ledger_path.parent / "hit_fire_mid").as_posix()
    assert settings["source_dir"] == settings["input_root"] == folder
    assert settings["profile"] == folder + "/profile.json"
    assert settings["profile_override"] is False
    assert (settings["project"], settings["timeout"], settings["save_root"]) == (project.as_posix(), 12.0, "Assets/Fx")


def test_ledger_saved_after_each_variant(tmp_path, fake):
    ledger_path, project = _expand(tmp_path, attrs=["fire"], tiers=["weak", "mid", "strong"], seeds=1)
    pipeline = fake(ledger_path)
    variant_run.run_set(ledger_path.parent, project)
    assert pipeline.done_on_disk == [0, 1, 2]
    assert not list(ledger_path.parent.glob(".set.json.*.tmp"))
    assert not (ledger_path.parent / variant_set.LOCK_FILE).exists()


def test_second_run_skips_done_and_only_filters(tmp_path, fake):
    ledger_path, project = _expand(tmp_path, attrs=["fire"], tiers=["weak", "mid"], seeds=1)
    first = fake(ledger_path)
    variant_run.run_set(ledger_path.parent, project, only=["hit_fire_mid"])
    assert first.calls == ["hit_fire_mid"]
    second = fake(ledger_path)
    _, _, issues = variant_run.run_set(ledger_path.parent, project, only=["hit_fire_mid,hit_fire_weak"])
    assert second.calls == ["hit_fire_weak"]
    assert [i["rule"] for i in issues] == ["variant.skipped"]
    third = fake(ledger_path)
    variant_run.run_set(ledger_path.parent, project)
    assert third.calls == []


def test_unknown_only_name_is_refused(tmp_path, fake):
    ledger_path, project = _expand(tmp_path, attrs=["fire"], tiers=["mid"], seeds=1)
    pipeline = fake(ledger_path)
    with pytest.raises(VfxError, match="모르는 판"):
        variant_run.run_set(ledger_path.parent, project, only=["hit_ice_mid"])
    assert pipeline.calls == []
    assert not (ledger_path.parent / variant_set.LOCK_FILE).exists()


def test_work_inside_unity_project_is_refused(tmp_path, fake):
    path = write_set(tmp_path / "in", attrs=["fire"], tiers=["mid"], seeds=1)
    project = tmp_path / "proj"
    ledger_path, _ = expand_set(path, project / "fx")
    pipeline = fake(ledger_path)
    with pytest.raises(VfxError, match="Unity 프로젝트 밖"):
        variant_run.run_set(ledger_path.parent, project)
    assert pipeline.calls == []


def test_lock_file_blocks_second_run(tmp_path, fake):
    ledger_path, project = _expand(tmp_path, attrs=["fire"], tiers=["mid"], seeds=1)
    pipeline = fake(ledger_path)
    (ledger_path.parent / variant_set.LOCK_FILE).write_text("", encoding="utf-8")
    with pytest.raises(variant_set.SetLocked):
        variant_run.run_set(ledger_path.parent, project)
    assert pipeline.calls == []


def test_preflight_only_when_something_to_run(tmp_path, fake, monkeypatch):
    ledger_path, project = _expand(tmp_path, attrs=["fire"], tiers=["mid"], seeds=1)
    fake(ledger_path)
    seen = []
    monkeypatch.setattr(variant_run, "preflight", lambda p, u: seen.append(p))
    variant_run.run_set(ledger_path.parent, project)
    variant_run.run_set(ledger_path.parent, project)
    assert seen == [project.resolve()]


def test_failed_expand_variant_is_not_run(tmp_path, fake):
    ledger_path, project = _expand(tmp_path, attrs=["fire"], tiers=["mid", {"name": "huge", "mul": {"life": 1.5}}], seeds=1)
    pipeline = fake(ledger_path)
    variant_run.run_set(ledger_path.parent, project)
    assert pipeline.calls == ["hit_fire_mid"]


def test_missing_set_json_and_bad_save_root(tmp_path, fake):
    ledger_path, project = _expand(tmp_path, attrs=["fire"], tiers=["mid"], seeds=1)
    with pytest.raises(VfxError, match="set.json"):
        variant_run.run_set(tmp_path, project)
    with pytest.raises(VfxError, match="save-root"):
        variant_run.run_set(ledger_path.parent, project, save_root="C:/x")


def test_timing_sums_done_variants():
    entries = [
        {"state": "done", "seconds": {"wall": 20.0, "unity_build": 1.0, "unity_render": 3.0}},
        {"state": "done", "seconds": {"wall": 10.0, "unity_build": 0.5, "unity_render": 0.5}},
        {"state": "failed", "seconds": {"wall": 99.0, "unity_build": None, "unity_render": None}},
        {"state": "expanded", "seconds": None},
    ]
    summary = variant_run.timing(entries)
    assert summary == {"wall_total": 30.0, "unity_inside": 5.0, "per_variant_mean": 15.0,
                       "startup_ratio": round(1 - 5.0 / 30.0, 3), "measured": 2}
    assert [i["rule"] for i in variant_run.timing_issues(summary)] == ["variant.startup_heavy"]
    assert variant_run.timing([{"state": "expanded", "seconds": None}]) is None
    light = dict(summary, startup_ratio=0.4)
    assert variant_run.timing_issues(light) == []


def test_unexpected_error_fails_only_that_variant(tmp_path, fake, monkeypatch):
    """반쯤 쓴 PNG 같은 VfxError 밖 오류도 그 판만 failed, 다음 판은 돈다."""
    ledger_path, project = _expand(tmp_path, attrs=["fire"], tiers=["weak", "mid"], seeds=1)
    pipeline = fake(ledger_path)

    def flaky(folder, settings):
        if folder.name == "hit_fire_mid":
            raise OSError("반쯤 쓴 파일")
        return pipeline(folder, settings)

    monkeypatch.setattr(variant_run, "run_pipeline", flaky)
    _, ledger, _ = variant_run.run_set(ledger_path.parent, project)
    states = {e["name"]: e["state"] for e in ledger["variants"]}
    assert states == {"hit_fire_mid": "failed", "hit_fire_weak": "done"}
    failed = next(e for e in ledger["variants"] if e["name"] == "hit_fire_mid")
    assert failed["issues"][0]["detail"] == "OSError: 반쯤 쓴 파일"
    assert _ledger(ledger_path) == ledger
