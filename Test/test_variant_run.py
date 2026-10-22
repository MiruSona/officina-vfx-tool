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
    _, ledger, issues = variant_run.run_set(ledger_path.parent, project, each=True)
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
    variant_run.run_set(ledger_path.parent, project, timeout=12.0, save_root="Assets/Fx", each=True)
    settings = pipeline.settings[0]
    folder = (ledger_path.parent / "hit_fire_mid").as_posix()
    assert settings["source_dir"] == settings["input_root"] == folder
    assert settings["profile"] == folder + "/profile.json"
    assert settings["profile_override"] is False
    assert (settings["project"], settings["timeout"], settings["save_root"]) == (project.as_posix(), 12.0, "Assets/Fx")


def test_ledger_saved_after_each_variant(tmp_path, fake):
    ledger_path, project = _expand(tmp_path, attrs=["fire"], tiers=["weak", "mid", "strong"], seeds=1)
    pipeline = fake(ledger_path)
    variant_run.run_set(ledger_path.parent, project, each=True)
    assert pipeline.done_on_disk == [0, 1, 2]
    assert not list(ledger_path.parent.glob(".set.json.*.tmp"))
    assert not (ledger_path.parent / variant_set.LOCK_FILE).exists()


def test_second_run_skips_done_and_only_filters(tmp_path, fake):
    ledger_path, project = _expand(tmp_path, attrs=["fire"], tiers=["weak", "mid"], seeds=1)
    first = fake(ledger_path)
    variant_run.run_set(ledger_path.parent, project, only=["hit_fire_mid"], each=True)
    assert first.calls == ["hit_fire_mid"]
    second = fake(ledger_path)
    _, _, issues = variant_run.run_set(ledger_path.parent, project, only=["hit_fire_mid,hit_fire_weak"], each=True)
    assert second.calls == ["hit_fire_weak"]
    assert [i["rule"] for i in issues] == ["variant.skipped"]
    third = fake(ledger_path)
    variant_run.run_set(ledger_path.parent, project, each=True)
    assert third.calls == []


def test_unknown_only_name_is_refused(tmp_path, fake):
    ledger_path, project = _expand(tmp_path, attrs=["fire"], tiers=["mid"], seeds=1)
    pipeline = fake(ledger_path)
    with pytest.raises(VfxError, match="모르는 판"):
        variant_run.run_set(ledger_path.parent, project, only=["hit_ice_mid"], each=True)
    assert pipeline.calls == []
    assert not (ledger_path.parent / variant_set.LOCK_FILE).exists()


def test_work_inside_unity_project_is_refused(tmp_path, fake):
    path = write_set(tmp_path / "in", attrs=["fire"], tiers=["mid"], seeds=1)
    project = tmp_path / "proj"
    ledger_path, _ = expand_set(path, project / "fx")
    pipeline = fake(ledger_path)
    with pytest.raises(VfxError, match="Unity 프로젝트 밖"):
        variant_run.run_set(ledger_path.parent, project, each=True)
    assert pipeline.calls == []


def test_lock_file_blocks_second_run(tmp_path, fake):
    ledger_path, project = _expand(tmp_path, attrs=["fire"], tiers=["mid"], seeds=1)
    pipeline = fake(ledger_path)
    (ledger_path.parent / variant_set.LOCK_FILE).write_text("", encoding="utf-8")
    with pytest.raises(variant_set.SetLocked):
        variant_run.run_set(ledger_path.parent, project, each=True)
    assert pipeline.calls == []


def test_preflight_only_when_something_to_run(tmp_path, fake, monkeypatch):
    ledger_path, project = _expand(tmp_path, attrs=["fire"], tiers=["mid"], seeds=1)
    fake(ledger_path)
    seen = []
    monkeypatch.setattr(variant_run, "preflight", lambda p, u: seen.append(p))
    variant_run.run_set(ledger_path.parent, project, each=True)
    variant_run.run_set(ledger_path.parent, project, each=True)
    assert seen == [project.resolve()]


def test_failed_expand_variant_is_not_run(tmp_path, fake):
    ledger_path, project = _expand(tmp_path, attrs=["fire"], tiers=["mid", {"name": "huge", "mul": {"life": 1.5}}], seeds=1)
    pipeline = fake(ledger_path)
    variant_run.run_set(ledger_path.parent, project, each=True)
    assert pipeline.calls == ["hit_fire_mid"]


def test_missing_set_json_and_bad_save_root(tmp_path, fake):
    ledger_path, project = _expand(tmp_path, attrs=["fire"], tiers=["mid"], seeds=1)
    with pytest.raises(VfxError, match="set.json"):
        variant_run.run_set(tmp_path, project)
    with pytest.raises(VfxError, match="save-root"):
        variant_run.run_set(ledger_path.parent, project, save_root="C:/x", each=True)


def test_timing_sums_done_variants():
    entries = [
        {"state": "done", "seconds": {"wall": 20.0, "unity_build": 1.0, "unity_render": 3.0}},
        {"state": "done", "seconds": {"wall": 10.0, "unity_build": 0.5, "unity_render": 0.5}},
        {"state": "failed", "seconds": {"wall": 99.0, "unity_build": None, "unity_render": None}},
        {"state": "expanded", "seconds": None},
    ]
    summary = variant_run.timing(entries)
    assert summary == {"wall_total": 30.0, "unity_inside": 5.0, "per_variant_mean": 15.0,
                       "startup_ratio": round(1 - 5.0 / 30.0, 3), "measured": 2,
                       "unity_wall": None, "mode": "each", "retries": 0}
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
    _, ledger, _ = variant_run.run_set(ledger_path.parent, project, each=True)
    states = {e["name"]: e["state"] for e in ledger["variants"]}
    assert states == {"hit_fire_mid": "failed", "hit_fire_weak": "done"}
    failed = next(e for e in ledger["variants"] if e["name"] == "hit_fire_mid")
    assert failed["issues"][0]["detail"] == "OSError: 반쯤 쓴 파일"
    assert _ledger(ledger_path) == ledger


# ── 묶어 굽기 — 가짜 Unity 실물로 준비 → Unity 한 번 → 판마다 마무리 (묶어굽기설계 4절 · 6-2) ──

import sys
from pathlib import Path

import numpy as np
from PIL import Image

from vfxtool.unity import lock

FAKE_UNITY = Path(__file__).parent / "data" / "unity" / "fake_unity.py"
NAMES4 = ["hit_fire_mid_s0", "hit_fire_mid_s1", "hit_fire_weak_s0", "hit_fire_weak_s1"]


@pytest.fixture
def batch(tmp_path, monkeypatch):
    """4판 묶음과 가짜 Unity 명령. run(*손잡이, **run_set 인자) → (장부, issues)."""
    monkeypatch.setattr(lock, "list_unity_processes", lambda: [])
    ledger_path, project = _expand(tmp_path, attrs=["fire"], tiers=["weak", "mid"], seeds=2)
    settings = project / "ProjectSettings"
    settings.mkdir()
    (settings / "ProjectVersion.txt").write_text("m_EditorVersion: 6000.3.23f1\n", encoding="utf-8")
    dot = np.zeros((256, 256, 4), dtype=np.uint8)
    dot[120:136, 120:136] = [0xFF, 0xC2, 0x3D, 255]
    Image.fromarray(dot, "RGBA").save(tmp_path / "dot.png")

    def run(*extra, **kwargs):
        parts = [sys.executable, str(FAKE_UNITY), "--frame-png", str(tmp_path / "dot.png")] + list(extra)
        unity = " ".join(f'"{part}"' for part in parts)
        _, ledger, issues = variant_run.run_set(ledger_path.parent, project, unity=unity, **kwargs)
        return ledger, issues

    run.set_dir = ledger_path.parent
    run.marker = tmp_path / "died.txt"
    return run


def _states(ledger):
    return {e["name"]: e["state"] for e in ledger["variants"]}


def _rules(ledger, name):
    return [i["rule"] for e in ledger["variants"] if e["name"] == name for i in e["issues"]]


def test_batch_bakes_all_in_one_unity(batch):
    ledger, issues = batch()
    assert issues == []
    assert set(_states(ledger).values()) == {"done"}
    jobs = json.loads((batch.set_dir / "jobs.json").read_text(encoding="utf-8"))["jobs"]
    assert [Path(p).parent.name for p in jobs] == NAMES4
    assert not (batch.set_dir / "unity_retry.log").exists()
    log = (batch.set_dir / "unity.log").read_text(encoding="utf-8")
    assert log.count("[VFXTOOL] jobs n=4 ") == 1 and log.count("[VFXTOOL] item ") == 4
    seconds = ledger["variants"][0]["seconds"]
    assert seconds == {"wall": None, "unity_build": 0.1, "unity_render": 0.1}
    for name in NAMES4:
        assert (batch.set_dir / name / "measure.json").is_file()
        assert not (batch.set_dir / name / "unity.log").exists()
    summary = variant_run.timing(ledger["variants"], ledger["run"])
    assert (summary["mode"], summary["retries"], summary["measured"]) == ("batch", 0, 4)
    assert summary["wall_total"] == ledger["run"]["wall"] > summary["unity_wall"] > 0
    assert summary["unity_inside"] == 0.8
    assert summary["startup_ratio"] == round(1 - 0.8 / summary["wall_total"], 3)
    assert _ledger(batch.set_dir / "set.json") == ledger


def test_batch_middle_failure_only_fails_that_variant(batch):
    ledger, _ = batch("--fail-at", "3")
    states = _states(ledger)
    assert states.pop("hit_fire_weak_s0") == "failed"
    assert set(states.values()) == {"done"}
    assert _rules(ledger, "hit_fire_weak_s0")[0] == "variant.run"
    assert ledger["run"]["retries"] == 0


def test_batch_crash_once_retries_rest(batch):
    ledger, _ = batch("--die-at", "2", "--die-once", str(batch.marker))
    assert set(_states(ledger).values()) == {"done"}
    assert ledger["run"]["retries"] == 1
    assert (batch.set_dir / "unity_retry.log").is_file()
    # 재시도 목록 — 첫 빈 판(죽인 판일 가능성)을 맨 뒤로(설계 9-1 대안 1)
    jobs = json.loads((batch.set_dir / "jobs.json").read_text(encoding="utf-8"))["jobs"]
    assert [Path(p).parent.name for p in jobs] == ["hit_fire_weak_s0", "hit_fire_weak_s1", "hit_fire_mid_s1"]


def test_batch_crash_always_loses_only_unfinished(batch):
    # 첫 판 : 목록 2번(mid_s1)에서 죽음 → 재시도 목록 [weak_s0, weak_s1, mid_s1] 의 2번(weak_s1)에서 또 죽음
    ledger, _ = batch("--die-at", "2")
    assert _states(ledger) == {"hit_fire_mid_s0": "done", "hit_fire_mid_s1": "failed",
                               "hit_fire_weak_s0": "done", "hit_fire_weak_s1": "failed"}
    assert _rules(ledger, "hit_fire_mid_s1") == ["variant.unity_lost"]
    lost = next(e for e in ledger["variants"] if e["name"] == "hit_fire_weak_s1")
    assert "3" in lost["issues"][0]["detail"]   # 두 판 종료 코드
    assert lost["seconds"] == {"wall": None, "unity_build": None, "unity_render": None}
    assert ledger["run"]["retries"] == 1


def test_batch_list_error_exits_2_and_leaves_expanded(batch):
    with pytest.raises(VfxError, match="목록"):
        batch("--list-error")
    on_disk = _ledger(batch.set_dir / "set.json")
    assert {e["state"] for e in on_disk["variants"]} == {"expanded"}
    assert not (batch.set_dir / "unity_retry.log").exists()


def test_batch_timeout_retries_and_limit(batch, monkeypatch):
    """첫 Unity 가 시간을 넘김(가짜로 바로 VfxError) → 빈 판 다 재시도. 상한 = 60 + 판 수 × 20."""
    real = variant_run.run_unity
    limits = []

    def flaky(unity, args, timeout):
        limits.append(timeout)
        if len(limits) == 1:
            raise VfxError("Unity 가 140초 안에 안 끝나 끊었다")
        return real(unity, args, timeout)

    monkeypatch.setattr(variant_run, "run_unity", flaky)
    ledger, _ = batch()
    assert set(_states(ledger).values()) == {"done"}
    assert limits == [140, 140]
    assert ledger["run"]["retries"] == 1


def test_batch_limit_counts_remaining_and_explicit_timeout(batch, monkeypatch):
    real = variant_run.run_unity
    limits = []
    monkeypatch.setattr(variant_run, "run_unity", lambda u, a, timeout: limits.append(timeout) or real(u, a, timeout))
    batch("--die-at", "3", "--die-once", str(batch.marker))
    assert limits == [140, 100]


def test_batch_explicit_timeout_is_per_process(batch, monkeypatch):
    real = variant_run.run_unity
    limits = []
    monkeypatch.setattr(variant_run, "run_unity", lambda u, a, timeout: limits.append(timeout) or real(u, a, timeout))
    batch("--die-at", "3", "--die-once", str(batch.marker), timeout=50.0)
    assert limits == [50.0, 50.0]


def test_batch_prepare_failure_not_in_list(batch):
    (batch.set_dir / "hit_fire_mid_s1" / "recipe.json").unlink()
    ledger, _ = batch()
    assert _states(ledger)["hit_fire_mid_s1"] == "failed"
    jobs = json.loads((batch.set_dir / "jobs.json").read_text(encoding="utf-8"))["jobs"]
    assert [Path(p).parent.name for p in jobs] == ["hit_fire_mid_s0", "hit_fire_weak_s0", "hit_fire_weak_s1"]


def test_each_timeout_default_is_300(tmp_path, fake):
    ledger_path, project = _expand(tmp_path, attrs=["fire"], tiers=["mid"], seeds=1)
    pipeline = fake(ledger_path)
    _, ledger, _ = variant_run.run_set(ledger_path.parent, project, each=True)
    assert pipeline.settings[0]["timeout"] == 300
    assert ledger["run"]["mode"] == "each"
    summary = variant_run.timing(ledger["variants"], ledger["run"])
    assert (summary["mode"], summary["retries"], summary["unity_wall"]) == ("each", 0, None)


def test_startup_heavy_only_in_each_mode():
    """묶음은 이미 묶어 굽기라 startup_heavy 를 안 낸다(묶어굽기설계 A19)."""
    each = {"startup_ratio": 0.9, "mode": "each"}
    batched = {"startup_ratio": 0.9, "mode": "batch"}
    assert "--each" in variant_run.timing_issues(each)[0]["detail"]
    assert variant_run.timing_issues(batched) == []


def test_batch_killer_job_loses_only_itself(batch):
    """한 판이 늘 Unity 를 죽여도 재시도 때 맨 뒤로 가니 그 판만 lost, 나머지 done."""
    ledger, _ = batch("--die-job", "hit_fire_mid_s1")
    states = _states(ledger)
    assert states.pop("hit_fire_mid_s1") == "failed"
    assert set(states.values()) == {"done"}
    assert _rules(ledger, "hit_fire_mid_s1") == ["variant.unity_lost"]
    assert ledger["run"]["retries"] == 1


def test_batch_compile_error_no_retry(batch):
    """첫 로그에 error CS 가 있으면 다시 돌려도 같다 — 재시도 없이 lost."""
    ledger, _ = batch("--log-line", "Assets/X.cs(1,1): error CS0103: 없는 이름", "--die-at", "1")
    assert set(_states(ledger).values()) == {"failed"}
    assert "컴파일" in next(e for e in ledger["variants"])["issues"][0]["detail"]
    assert ledger["run"]["retries"] == 0
    assert not (batch.set_dir / "unity_retry.log").exists()


def test_batch_lock_checked_before_retry(batch, monkeypatch):
    """재시도 전에 같은 프로젝트를 연 Unity 가 생겼으면 다시 안 띄우고 남은 판은 lost."""
    real = variant_run.run_unity
    ran = []

    def run_once(unity, args, timeout):
        ran.append(1)
        return real(unity, args, timeout)

    def processes():  # 준비 단계 잠금 검사는 통과, Unity 를 한 번 띄운 뒤로는 막힘
        if ran:
            return [{"ProcessId": 7, "CommandLine": None}]
        return []

    monkeypatch.setattr(variant_run, "run_unity", run_once)
    monkeypatch.setattr(lock, "list_unity_processes", processes)
    ledger, _ = batch("--die-at", "2", "--die-once", str(batch.marker))
    assert _states(ledger)["hit_fire_mid_s0"] == "done"
    lost = next(e for e in ledger["variants"] if e["name"] == "hit_fire_mid_s1")
    assert lost["issues"][0]["rule"] == "variant.unity_lost" and "잠금" in lost["issues"][0]["detail"]
    assert ledger["run"]["retries"] == 0 and len(ran) == 1


def test_batch_clears_old_retry_log_and_counts_sent(batch):
    (batch.set_dir / "unity_retry.log").write_text("지난 판", encoding="utf-8")
    (batch.set_dir / "hit_fire_mid_s1" / "recipe.json").unlink()
    ledger, _ = batch()
    assert not (batch.set_dir / "unity_retry.log").exists()
    assert ledger["run"]["variants"] == ["hit_fire_mid_s0", "hit_fire_weak_s0", "hit_fire_weak_s1"]
    missing = next(e for e in ledger["variants"] if e["name"] == "hit_fire_mid_s1")
    assert missing["seconds"]["wall"] is None


def test_batch_missing_log_span_is_info(batch, monkeypatch):
    monkeypatch.setattr(variant_run, "job_spans", lambda log_file: {variant_run.TAIL: (0, 0)})
    ledger, _ = batch()
    assert set(_states(ledger).values()) == {"done"}
    assert "variant.log_span" in _rules(ledger, "hit_fire_mid_s0")
