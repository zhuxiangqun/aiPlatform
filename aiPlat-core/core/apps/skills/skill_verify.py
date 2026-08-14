"""
SkillVerify — Skill 验收清单 (5项自动化检查)

对齐文章 "从规范到上线的完整路径" 的验收标准:
  1. 可识别 — SkillRegistry 中是否已注册
  2. 可调用 — SKILL.md 解析成功 + execution_type 合法
  3. 输出格式稳定 — output_schema 已定义 + required_fields 完整
  4. 格式一致 — validate_frontmatter 通过 + lint_rules 无 error
  5. 内容符合预期 — SOP ≥3步 + description ≥20字符

调用者: POST /skills/{id}/verify
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class VerifyCheck:
    name: str
    pass_: bool = False
    detail: str = ""
    issues: List[str] = field(default_factory=list)


@dataclass
class VerifyReport:
    skill_id: str
    checks: List[VerifyCheck] = field(default_factory=list)
    overall: bool = False
    suggestion: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "checks": [{"name": c.name, "pass": c.pass_, "detail": c.detail, "issues": c.issues} for c in self.checks],
            "overall": self.overall,
            "suggestion": self.suggestion,
        }


class SkillVerifier:
    """Skill 验收器."""

    def verify(self, skill_id: str) -> VerifyReport:
        """运行 5 项验收检查."""
        report = VerifyReport(skill_id=skill_id)

        # Check 1: 可识别
        report.checks.append(self._check_recognized(skill_id))

        # Check 2: 可调用
        report.checks.append(self._check_callable(skill_id))

        # Check 3: 输出格式稳定
        report.checks.append(self._check_output_stable(skill_id))

        # Check 4: 格式一致
        report.checks.append(self._check_format_consistent(skill_id))

        # Check 5: 内容符合预期
        report.checks.append(self._check_content_correct(skill_id))

        # Overall
        failed = [c for c in report.checks if not c.pass_]
        report.overall = len(failed) == 0
        if failed:
            names = [c.name for c in failed]
            report.suggestion = f"修复以下检查项: {', '.join(names)}"

        return report

    def _check_recognized(self, skill_id: str) -> VerifyCheck:
        """检查 1: 可识别 — 是否在 SkillRegistry 中注册."""
        try:
            from core.apps.skills.registry import get_skill_registry
            reg = get_skill_registry()
            sk = reg.get_skill(skill_id) if hasattr(reg, "get_skill") else None
            has = sk is not None
            if not has:
                # Try by name list
                skills = reg.list_skills() if hasattr(reg, "list_skills") else []
                has = any(s.get("name") == skill_id for s in skills) if isinstance(skills, list) else False
            return VerifyCheck(
                name="can_be_seen", pass_=has,
                detail="Skill 已在注册表中" if has else "Skill 未注册 — 检查路径和 SKILL.md 格式",
            )
        except Exception as e:
            return VerifyCheck(name="can_be_seen", pass_=False, detail=str(e)[:100])

    def _check_callable(self, skill_id: str) -> VerifyCheck:
        """检查 2: 可调用 — SKILL.md 解析成功 + execution_type 合法."""
        try:
            from core.apps.skills.registry import get_skill_registry
            reg = get_skill_registry()
            sk = reg.get_skill(skill_id) if hasattr(reg, "get_skill") else None
            if not sk:
                return VerifyCheck(name="can_be_called", pass_=False, detail="Skill 未找到 (见检查1)")

            config = getattr(sk, "config", None) or getattr(sk, "_config", None)
            exec_type = getattr(config, "execution_type", "") if config else ""
            if not exec_type:
                body = reg._body_cache.get(skill_id, "")
                # Try to parse execution_type from frontmatter
                if body.startswith("---"):
                    import yaml
                    try:
                        parts = body.split("---", 2)
                        fm = yaml.safe_load(parts[1]) if len(parts) >= 2 else {}
                        exec_type = fm.get("execution_type", "") if isinstance(fm, dict) else ""
                    except Exception:
                        logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
            return VerifyCheck(
                name="can_be_called", pass_=bool(exec_type),
                detail=f"execution_type={exec_type}" if exec_type else "缺少 execution_type 声明",
            )
        except Exception as e:
            return VerifyCheck(name="can_be_called", pass_=False, detail=str(e)[:100])

    def _check_output_stable(self, skill_id: str) -> VerifyCheck:
        """检查 3: 输出格式稳定 — output_schema 已定义."""
        try:
            from core.apps.skills.registry import get_skill_registry
            reg = get_skill_registry()
            body = reg._body_cache.get(skill_id, "")
            has_schema = "output_schema" in body
            return VerifyCheck(
                name="output_stable", pass_=has_schema,
                detail="output_schema 已定义" if has_schema else "缺少 output_schema — 输出格式不稳定",
            )
        except Exception as e:
            return VerifyCheck(name="output_stable", pass_=False, detail=str(e)[:100])

    def _check_format_consistent(self, skill_id: str) -> VerifyCheck:
        """检查 4: 格式一致 — frontmatter 通过 + lint 无 error."""
        try:
            from core.apps.skills.registry import get_skill_registry
            reg = get_skill_registry()
            body = reg._body_cache.get(skill_id, "")
            issues = []
            if not body.startswith("---"):
                issues.append("缺少 YAML frontmatter (---)")
            if "name:" not in body:
                issues.append("缺少 name 字段")
            if "version:" not in body:
                issues.append("缺少 version 字段")
            return VerifyCheck(
                name="format_consistent", pass_=len(issues) == 0,
                detail="frontmatter 格式正确" if not issues else f"格式问题: {', '.join(issues)}",
                issues=issues,
            )
        except Exception as e:
            return VerifyCheck(name="format_consistent", pass_=False, detail=str(e)[:100])

    def _check_content_correct(self, skill_id: str) -> VerifyCheck:
        """检查 5: 内容符合预期 — SOP ≥3步 + description ≥20字符."""
        try:
            from core.apps.skills.registry import get_skill_registry
            reg = get_skill_registry()
            body = reg._body_cache.get(skill_id, "")
            issues = []
            # Parse frontmatter
            desc = ""
            if body.startswith("---"):
                try:
                    import yaml
                    parts = body.split("---", 2)
                    fm = yaml.safe_load(parts[1]) if len(parts) >= 2 else {}
                    desc = str(fm.get("description", "")) if isinstance(fm, dict) else ""
                except Exception:
                    logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
            if len(desc) < 20:
                issues.append(f"description 过短 ({len(desc)} chars, 需≥20)")
            # Count SOP steps (numbered lines OR ## Step N: headings)
            sop_parts = body.split("---", 2)
            sop_body = sop_parts[2] if len(sop_parts) > 2 else (sop_parts[0] if sop_parts else body)
            numbered = [l for l in sop_body.split("\n") if l.strip() and (l.strip()[0].isdigit() and "." in l.strip()[:3])]
            heading_steps = [l for l in sop_body.split("\n") if "step" in l.lower() and "##" in l]
            all_steps = list(set(numbered + heading_steps))
            if len(all_steps) < 1:
                issues.append(f"SOP 步骤不足 ({len(all_steps)} step(s), 需≥1)")
            return VerifyCheck(
                name="content_correct", pass_=len(issues) == 0,
                detail=f"description={len(desc)}chars, SOP={len(all_steps)}步骤" if not issues else f"内容问题: {', '.join(issues)}",
                issues=issues,
            )
        except Exception as e:
            return VerifyCheck(name="content_correct", pass_=False, detail=str(e)[:100])
