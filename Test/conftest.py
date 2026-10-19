"""시험 공용 — src 를 경로에 넣고, 설계 2-6 예시 레시피 사본을 준다."""

import copy
import json
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

DATA = Path(__file__).resolve().parent / "data"
RECIPE_PATH = DATA / "recipes" / "hit_sparks_a.json"
PROFILE_PATH = DATA / "profile.json"


@pytest.fixture
def recipe():
    """설계 2-6 예시 레시피(고쳐도 되는 사본)."""
    return copy.deepcopy(json.loads(RECIPE_PATH.read_text(encoding="utf-8")))


@pytest.fixture
def layer(recipe):
    return recipe["layers"][0]


def write_set(folder, **fields):
    """변형 묶음 시험 판 — folder 에 시험 프로필 사본과 묶음 JSON(설계 2-1 예제 꼴)을 쓰고 묶음 경로를 준다."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "profile.json").write_bytes(PROFILE_PATH.read_bytes())
    data = {"version": 1, "name": "hit", "template": "hit_sparks", "profile": "profile.json", "duration": 0.6,
            "seed": 1000, "params": {"ring": True}, "preset": None,
            "attrs": ["fire", "ice"], "tiers": ["weak", "mid", "strong"], "seeds": 2}
    data.update(fields)
    path = folder / "set.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path
