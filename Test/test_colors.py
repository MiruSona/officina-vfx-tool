"""색 값 네 꼴 — hex · p<n> · gradient 키 수 · 풀이."""

import pytest

from vfxtool.recipe import colors

PALETTE = ["#FFE08A", "#F0A040", "#C04020", "#602010"]


def _gradient(color_keys, alpha_keys=None, mode=None):
    body = {"color": color_keys}
    if alpha_keys is not None:
        body["alpha"] = alpha_keys
    value = {"gradient": body}
    if mode is not None:
        value["mode"] = mode
    return value


@pytest.mark.parametrize("value", [
    "#FFE08A",
    "#ffe08a80",
    "p3",
    {"random": ["p0", "#FFFFFF"]},
    _gradient([[0, "p0"], [1, "p3"]], [[0, 1], [0.8, 0]]),
    _gradient([[0, "#FFFFFF"]], mode="blend"),
    {"random_gradient": [_gradient([[0, "p0"]]), _gradient([[0, "p1"]])]},
])
def test_good_colors_pass(value):
    assert colors.color_problems(value) == []


@pytest.mark.parametrize("value", [
    "#FFF",
    "red",
    "p",
    3,
    {"random": ["p0"]},
    {"random": ["p0", "blue"]},
    _gradient([[0, "#FFE08A80"]]),
    _gradient([[0, "p0"]], [[0, 2]]),
    _gradient([[0.5, "p0"], [0.2, "p1"]]),
    _gradient([[0, "p0"]], mode="smooth"),
    {"gradient": {"color": [[0, "p0"]], "extra": 1}},
    {"random_gradient": [_gradient([[0, "p0"]])]},
])
def test_bad_colors_are_schema(value):
    problems = colors.color_problems(value)
    assert problems and problems[0][0] == "recipe.schema"


def test_more_than_eight_keys_is_gradient_keys():
    keys = [[i / 10, "p0"] for i in range(9)]
    assert colors.color_problems(_gradient(keys))[0][0] == "recipe.gradient_keys"
    alpha = [[i / 10, 1] for i in range(9)]
    assert colors.color_problems(_gradient([[0, "p0"]], alpha))[0][0] == "recipe.gradient_keys"


def test_to_hex_resolves_palette_and_upper():
    assert colors.to_hex("p2", PALETTE) == "#C04020"
    assert colors.to_hex("#ffe08a", PALETTE) == "#FFE08A"
    with pytest.raises(IndexError):
        colors.to_hex("p4", PALETTE)


def test_resolve_fills_mode_and_alpha():
    resolved = colors.resolve(_gradient([[0, "p0"], [1, "p1"]]), PALETTE)
    assert resolved == {
        "gradient": {"color": [[0, "#FFE08A"], [1, "#F0A040"]], "alpha": [[0, 1], [1, 1]]},
        "mode": "fixed",
    }
    assert colors.resolve({"random": ["p0", "p3"]}, PALETTE) == {"random": ["#FFE08A", "#602010"]}


def test_refs_alphas_blend():
    value = {"random_gradient": [_gradient([[0, "p0"]], [[0, 0.5]], mode="blend"), _gradient([[0, "p1"]])]}
    assert colors.refs_of(value) == ["p0", "p1"]
    assert colors.alphas_of(value) == [0.5]
    assert colors.uses_blend(value) is True
    assert colors.alphas_of("#FFFFFF80") == [128 / 255]
    assert colors.uses_blend("p0") is False
