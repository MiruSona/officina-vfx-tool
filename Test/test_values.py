"""다형 값 다섯 꼴 — 검사 · 펼치기 · 단위."""

import pytest

from vfxtool.recipe import values


@pytest.mark.parametrize("value", [
    0.3,
    2,
    {"random": [0.2, 0.5]},
    {"curve": [[0, 1], [0.5, 2], [1, 0]], "mult": 1, "step": True},
    {"curve": [[0, 1], [1, 0]]},
    {"random_curve": [[[0, 1], [1, 0]], [[0, 2], [1, 0]]]},
    {"from": 2, "to": 0, "ease": "out"},
    {"from": 2, "to": 0},
])
def test_good_forms_pass(value):
    assert values.value_problems(value) == []


@pytest.mark.parametrize("value", [
    True,
    "1",
    None,
    float("nan"),
    {},
    {"random": [1]},
    {"random": [1, "a"]},
    {"random": [1, 2], "mult": 3},
    {"curve": [[0, 1]]},
    {"curve": [[0, 1], [0, 2]]},
    {"curve": [[0.5, 1], [0.2, 2]]},
    {"curve": [[0, 1], [1.5, 2]]},
    {"curve": [[t / 10, 1] for t in range(9)]},
    {"curve": [[0, 1], [1, 2]], "step": "yes"},
    {"random_curve": [[[0, 1], [1, 0]]]},
    {"random_curve": [[[0, 1], [1, 0]], [[0, 1]]]},
    {"from": 1},
    {"from": 1, "to": 2, "ease": "bounce"},
])
def test_bad_forms_fail(value):
    assert values.value_problems(value) != []


def test_ease_expands_to_five_keys():
    keys = values.expand_ease({"from": 2, "to": 0, "ease": "linear"})
    assert keys == [[0.0, 2.0], [0.25, 1.5], [0.5, 1.0], [0.75, 0.5], [1.0, 0.0]]


def test_ease_out_is_fast_first():
    keys = values.expand_ease({"from": 0, "to": 1, "ease": "out"})
    assert keys[1][1] == 0.4375
    keys = values.expand_ease({"from": 0, "to": 1, "ease": "in"})
    assert keys[1][1] == 0.0625
    keys = values.expand_ease({"from": 0, "to": 1, "ease": "inout"})
    assert [v for _, v in keys] == [0.0, 0.125, 0.5, 0.875, 1.0]


def test_normalize_fills_curve_defaults():
    assert values.normalize({"curve": [[0, 2], [1, 1]]}) == {"curve": [[0, 2], [1, 1]], "mult": 1, "step": False}
    assert values.normalize({"curve": [[0, 2], [1, 1]]}, step_default=True)["step"] is True
    assert values.normalize({"curve": [[0, 2], [1, 1]], "step": False}, step_default=True)["step"] is False
    eased = values.normalize({"from": 2, "to": 1}, step_default=True)
    assert eased["step"] is True and len(eased["curve"]) == 5


def test_normalize_leaves_only_four_forms():
    for value in (1, {"random": [1, 2]}, {"from": 1, "to": 0}, {"random_curve": [[[0, 1], [1, 0]], [[0, 2], [1, 0]]]}):
        assert values.form_of(values.normalize(value)) in ("constant", "random", "curve", "random_curve")


def test_scale_divides_numbers_not_times():
    assert values.scale(64, 1 / 32) == 2.0
    assert values.scale({"random": [40, 90]}, 1 / 32) == {"random": [1.25, 2.8125]}
    scaled = values.scale({"curve": [[0, 32], [1, 16]], "mult": 2, "step": True}, 1 / 32)
    assert scaled == {"curve": [[0, 1.0], [1, 0.5]], "mult": 2, "step": True}
    pair = values.scale({"random_curve": [[[0, 32], [1, 0]], [[0, 64], [1, 0]]]}, 1 / 32)
    assert pair["random_curve"][1][0] == [0, 2.0]


def test_texels_to_units():
    assert values.texels_to_units(1, 32) == 0.03125
    assert values.texels_to_units(3, 16) == 0.1875


def test_numbers_of():
    assert values.numbers_of(1) == [1]
    assert values.numbers_of({"random": [1, 2]}) == [1, 2]
    assert values.numbers_of({"curve": [[0, 2], [1, 1]], "mult": 2}) == [4, 2]
    assert values.numbers_of({"from": 2, "to": 1, "ease": "linear"}) == [2.0, 1.75, 1.5, 1.25, 1.0]
