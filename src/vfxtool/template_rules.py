"""템플릿 전용 레시피 단계 규칙(설계 4-2 표의 「템플릿 check」 중 Unity 전에 볼 수 있는 것).

규칙 꼴 : {"rule", "layer"(템플릿 층 이름), "args"}. kind: "frame" 규칙은 measure 몫이라 여기 안 온다.
"""

from vfxtool.errors import VfxError
from vfxtool.report import issue


def run(rule, recipe, call_name, by_short):
    name = rule["rule"]
    args = rule.get("args", {})
    layer = None
    if rule.get("layer"):
        layer = by_short.get(rule["layer"])
        if layer is None:
            return []
    full = f"template.{name}"
    if name == "burst_only":
        return _burst_only(layer, full)
    if name == "max_duration":
        if recipe["duration"] <= args["max"]:
            return []
        return [issue(full, "error", f"duration {recipe['duration']} > 템플릿 상한 {args['max']}", layer=call_name, hint=["duration"])]
    if name == "loop":
        if recipe.get("loop", False) is args.get("value", True):
            return []
        return [issue(full, "error", f"이 템플릿은 loop: {str(args.get('value', True)).lower()} 로 쓴다", layer=call_name, hint=["loop"])]
    if name == "start_frame_random":
        start = layer.get("textureSheet", {}).get("startFrame")
        if isinstance(start, dict) and "random" in start:
            return []
        return [issue(full, "error", "플립북 시작 프레임은 random 이어야 한다", layer=layer["name"], hint=["textureSheet.startFrame"])]
    raise VfxError(f"템플릿 규칙을 모른다 : {name}")


def _burst_only(layer, full):
    emission = layer.get("emission", {})
    if emission.get("rateOverTime", 0) == 0 and emission.get("bursts"):
        return []
    return [issue(full, "error", "버스트만 쓴다 — rateOverTime 0 · bursts 하나 이상", layer=layer["name"], hint=["emission"])]
