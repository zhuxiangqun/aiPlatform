"""Agent-bound required_skills must not force a second HITL mid-loop."""

from core.apps.tools.skill_tools import is_agent_bound_required_skill
from core.harness.utils.inline_autoreview_workspace import (
    extract_file_names_from_inline,
    extract_file_sections,
    inline_code_to_review_blob,
    autoreview_git_env_for_inline,
)
from core.engine.skills.autoreview.diff_loader import load_diff


def test_is_agent_bound_required_skill_true():
    assert is_agent_bound_required_skill(
        "autoreview",
        {"_bound_skill_ids": ["code_generation", "autoreview"]},
    )


def test_is_agent_bound_required_skill_false_when_unbound():
    assert not is_agent_bound_required_skill(
        "autoreview",
        {"_bound_skill_ids": ["code_generation"]},
    )


def test_is_agent_bound_required_skill_false_without_args():
    assert not is_agent_bound_required_skill("autoreview", None)
    assert not is_agent_bound_required_skill("autoreview", {})
    assert not is_agent_bound_required_skill("", {"_bound_skill_ids": ["autoreview"]})


def test_inline_code_to_review_blob_adds_plus_prefix():
    blob = inline_code_to_review_blob("## FILE: a.ts\n```ts\nexport const x = 1\n```")
    assert "diff --git" in blob
    assert "+## FILE: a.ts" in blob
    assert "+export const x = 1" in blob


def test_extract_file_names_from_inline():
    names = extract_file_names_from_inline(
        "## FILE: src/api.ts\ncode\n## FILE: src/App.tsx\nmore"
    )
    assert names == ["src/api.ts", "src/App.tsx"]


def test_extract_file_sections_strips_fence():
    secs = extract_file_sections(
        "## FILE: src/api.ts\n```typescript\nexport const n = 1\n```\n"
    )
    assert secs == [("src/api.ts", "export const n = 1")]


def test_autoreview_git_env_makes_stock_load_diff_see_inline():
    """Harness stages ## FILE into a worktree; load_diff(cwd=...) reviews it."""
    inline = (
        "## FILE: src/apiClient.ts\n"
        "```typescript\n"
        "export async function createReport() { return 1 }\n"
        "```\n"
    )
    with autoreview_git_env_for_inline(inline) as wt:
        assert wt
        diff = load_diff("diff", cwd=wt)
    assert diff.content
    assert "apiClient" in diff.content or "createReport" in diff.content
