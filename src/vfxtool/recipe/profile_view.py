"""profile.json 을 읽어 기본값과 합친 view 를 준다. check · resolve · measure · sheet 가 같이 쓴다.

기본값 표와 칸 검사는 profile/common(DEFAULTS · normalize) 한 곳에 둔다. 칸 값은 그대로이거나
{"value", "source"} 꼴 둘 다 읽는다.
"""

from vfxtool.errors import VfxError
from vfxtool.paths import read_json
from vfxtool.profile import common


def load_profile(path):
    """파일을 읽어 view 를 돌려준다. 고칠 수 없는 프로필(팔레트 없음 등)은 VfxError(종료 2)."""
    data = read_json(path)
    if not isinstance(data, dict):
        raise VfxError(f"프로필은 JSON 객체여야 한다 : {path}")
    return make_view(data, str(path))


def make_view(data, where="profile"):
    view = common.defaults()
    for name, default in common.DEFAULTS.items():
        value = _unwrap(data.get(name))
        if value is None:
            continue
        try:
            view[name] = common.normalize(name, value, default)
        except ValueError as exc:
            raise VfxError(f"프로필 {name} : {exc} — {where}") from None
    if not view["palette"]:
        raise VfxError(f"프로필 palette 가 비었거나 없다 : {where}")
    return view


def _unwrap(raw):
    if isinstance(raw, dict) and "value" in raw:
        return raw["value"]
    return raw
