"""레시피 단계 검사(설계 8-1) — Unity 를 띄우기 전에 틀린 값을 다 거른다.

흐름 : 최상위 칸 → 프로필 읽기 → 템플릿 펼치기 → 층 · 모듈 칸 → 규칙 → (error 없으면) resolved.
recipe.schema · unsupported 는 fields.py, recipe.fixed 는 템플릿 펼치기(vfxtool.template)가 낸다.
"""

from pathlib import Path

from vfxtool.errors import VfxError
from vfxtool.paths import ensure_inside
from vfxtool.recipe import fields, resolve
from vfxtool.recipe.check_rules import layer_rules, recipe_rules
from vfxtool.recipe.profile_view import load_profile
from vfxtool.report import has_errors, issue


class CheckResult:
    """check 한 판의 결과. resolved 는 error 가 없을 때만 채운다."""

    def __init__(self, issues, resolved=None, profile=None):
        self.issues = issues
        self.resolved = resolved
        self.profile = profile


def run_check(recipe, recipe_path, profile_path=None, input_root=None, template_dirs=()):
    """recipe 는 읽은 dict. profile_path 를 주면 레시피의 profile 칸 대신 쓴다(경로 감옥 밖이어도 된다)."""
    recipe_dir = Path(recipe_path).resolve().parent
    root = recipe_dir
    if input_root is not None:
        root = Path(input_root).resolve()
    issues = fields.check_top(recipe)
    if has_errors(issues):
        return CheckResult(issues)
    profile_file = _profile_file(recipe, recipe_dir, root, profile_path, issues)
    if profile_file is None:
        return CheckResult(issues)
    profile = load_profile(profile_file)
    expanded, template_issues = resolve.expand_templates(recipe, profile, template_dirs)
    issues.extend(template_issues)
    if has_errors(issues):
        return CheckResult(issues, profile=profile)
    issues.extend(fields.check_layers(expanded))
    if has_errors(issues):
        return CheckResult(issues, profile=profile)
    issues.extend(recipe_rules(expanded, profile))
    for layer in expanded["layers"]:
        issues.extend(layer_rules(layer, profile, recipe_dir, root))
    if has_errors(issues):
        return CheckResult(issues, profile=profile)
    return CheckResult(issues, resolve.resolve(expanded, profile, recipe_dir), profile)


def _profile_file(recipe, recipe_dir, root, profile_path, issues):
    """프로필 파일 자리. 레시피의 profile 칸이 감옥 밖이면 recipe.paths error 를 issues 에 넣고 None."""
    if profile_path is not None:
        return Path(profile_path)
    try:
        return ensure_inside(recipe_dir / recipe["profile"], root)
    except VfxError as exc:
        detail = f"profile : {exc.message} — 레시피 폴더 밖 파일이면 --input-root 로 그 위 폴더를 준다"
        issues.append(issue("recipe.paths", "error", detail, hint=["profile", "--input-root"]))
        return None
