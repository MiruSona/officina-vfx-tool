"""job.json · 프레임 시각 표(설계 6-2)."""

import json

import pytest

from vfxtool.errors import VfxError
from vfxtool.unity import job as jobs


def _resolved(duration, layers, loop=False):
    return {"duration": duration, "loop": loop,
            "layers": [{"name": f"l{i}", "main": m} for i, m in enumerate(layers)]}


@pytest.mark.parametrize("value, expected", [
    (0.3, 0.3),
    (2, 2.0),
    ({"random": [0.25, 0.45]}, 0.45),
    ({"curve": [[0, 1], [0.5, 2], [1, 0]], "mult": 1.5, "step": True}, 3.0),
    ({"curve": [[0, 1], [1, 3]]}, 3.0),
    ({"random_curve": [[[0, 1], [1, 0]], [[0, 2], [1, 0]]], "mult": 2}, 4.0),
    ({"curve": [[0, -1], [1, 2]], "mult": -1}, 1.0),
])
def test_value_max(value, expected):
    assert jobs.value_max(value) == pytest.approx(expected)


@pytest.mark.parametrize("value", ["0.3", True, {"from": 1, "to": 0}, [1, 2]])
def test_value_max_rejects_unknown(value):
    with pytest.raises(VfxError):
        jobs.value_max(value)


def test_one_shot_frames():
    # 0.5 + 지연 0.1 + 수명 최대 0.45 = 1.05초 × 12 = 12.6 → 13장
    resolved = _resolved(0.5, [{"startDelay": 0.1, "startLifetime": {"random": [0.25, 0.45]}},
                               {"startLifetime": 0.2}])
    frames = jobs.frame_times(resolved, 12)
    assert len(frames) == 13
    assert frames[0] == {"i": 1, "t": round(0.5 / 12, 6)}
    assert frames[-1] == {"i": 13, "t": round(12.5 / 12, 6)}
    assert all(f["t"] > 0 for f in frames)


def test_first_frame_lands_in_flipbook_cell_zero():
    # fps 12 플립북의 0번 칸은 [0, 1/12). 첫 장이 거기 들어가야 0번 칸이 찍힌다.
    for fps in (8, 12, 24):
        frames = jobs.frame_times(_resolved(0.5, [{"startLifetime": 0.5}]), fps)
        assert 0 <= frames[0]["t"] < 1 / fps
        # 장 k(0부터)는 k번 칸 [k/fps, (k+1)/fps) 안
        for k, frame in enumerate(frames):
            assert k / fps <= frame["t"] < (k + 1) / fps


def test_one_shot_exact_product_has_no_extra_frame():
    # 0.25 + 0.25 = 0.5초 × 12 = 6.0 → 6장 (소수점 오차로 7이 되면 안 됨)
    resolved = _resolved(0.25, [{"startLifetime": 0.25}])
    assert len(jobs.frame_times(resolved, 12)) == 6


def test_one_shot_caps_at_48():
    resolved = _resolved(3.0, [{"startLifetime": 2.0}])
    frames = jobs.frame_times(resolved, 16)
    assert len(frames) == 48
    assert frames[-1]["i"] == 48


def test_missing_lifetime_uses_unity_default():
    # Unity 기본 수명 5초 → 상한 48
    assert len(jobs.frame_times(_resolved(0.1, [{}]), 12)) == 48


def test_loop_frames_start_after_one_cycle():
    resolved = _resolved(2.0, [{"startLifetime": 9}], loop=True)
    frames = jobs.frame_times(resolved, 12)
    assert len(frames) == 24
    assert frames[0]["t"] == pytest.approx(2.0 + 0.5 / 12, abs=1e-6)
    assert frames[-1]["t"] == pytest.approx(2.0 + 23.5 / 12, abs=1e-6)
    # 꼬리 장도 한 바퀴(2.0~4.0) 안 — 다음 바퀴 0번 칸으로 넘어가지 않는다
    assert frames[-1]["t"] < 4.0


def test_bad_fps():
    with pytest.raises(VfxError):
        jobs.frame_times(_resolved(1, [{}]), 0)


@pytest.mark.parametrize("given, expected", [
    ("Assets/Vfx/Generated", "Assets/Vfx/Generated"),
    ("Assets\\Game\\Fx\\", "Assets/Game/Fx"),
    ("./Assets/./Fx", "Assets/Fx"),
])
def test_save_root_ok(given, expected):
    assert jobs.normalize_save_root(given) == expected


@pytest.mark.parametrize("given", ["", "/Assets/x", "C:/p/Assets", "Assets/../ProjectSettings",
                                   "Packages/x", "Assets/a/../../b"])
def test_save_root_rejected(given):
    with pytest.raises(VfxError):
        jobs.normalize_save_root(given)


@pytest.mark.parametrize("given", ["Assets/VfxToolVerify/bad ", "Assets/bad./x", " Assets/x", "   "])
def test_save_root_rejects_trailing_space_or_dot_in_segment(given):
    # 벗기지 않고 거절한다 — Windows 는 조각 끝 공백 · 점을 몰래 벗겨 `bad/` 같은 다른 자리에 저장한다.
    with pytest.raises(VfxError):
        jobs.normalize_save_root(given)


def test_backgrounds():
    assert jobs.parse_backgrounds(None) == ["transparent"]
    assert jobs.parse_backgrounds("black, white") == ["black", "white"]
    with pytest.raises(VfxError):
        jobs.parse_backgrounds("black,pink")


def test_write_job_fields(tmp_path):
    recipe = tmp_path / "resolved.json"
    recipe.write_text("{}", encoding="utf-8")
    job = jobs.make_job(recipe, "render", "Assets/Vfx/Generated", tmp_path / "frames",
                        [{"i": 1, "t": 0.083333}], ["transparent"])
    path = jobs.write_job(tmp_path / "round_1" / "job.json", job)
    data = json.loads(path.read_text(encoding="utf-8"))
    # C# VfxJob 은 모르는 칸을 MissingMemberHandling.Error 로 거절한다 — 칸 목록 · 순서를 고정한다(설계 5-4).
    assert list(data) == ["recipe", "mode", "saveRoot", "outDir", "frames", "backgrounds"]
    assert all(list(frame) == ["i", "t"] for frame in data["frames"])
    assert data["recipe"] == str(recipe.resolve())
    assert data["mode"] == "render"
    with pytest.raises(VfxError):
        jobs.make_job(recipe, "bake", "Assets", tmp_path, [], [])


# ── 묶어 굽기 jobs.json (묶어굽기설계 2-2) ──

def test_write_job_list_fields(tmp_path):
    paths = [tmp_path / "a" / "job.json", tmp_path / "b" / "job.json"]
    out = jobs.write_job_list(tmp_path / "jobs.json", paths)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert list(data) == ["jobs"]
    assert data["jobs"] == [str(p) for p in paths]


@pytest.mark.parametrize("bad, match", [
    (["rel/job.json"], "절대 경로"),
    ([], "1~48"),
    (["{0}/a/job.json", "{0}/A/other.json"], "겹친다"),
    (["{0}/j%d.json" % i for i in range(49)], "1~48"),
])
def test_write_job_list_rejects(tmp_path, bad, match):
    paths = [p.format(tmp_path) for p in bad]
    with pytest.raises(VfxError, match=match):
        jobs.write_job_list(tmp_path / "jobs.json", paths)
    assert not (tmp_path / "jobs.json").exists()
