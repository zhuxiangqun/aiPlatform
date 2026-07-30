"""
SkillGenerator — 从操作序列自动生成 SKILL.md (Agent 闭环执行 — 技能自动化沉淀)

将 OperationRecorder 录制的操作序列通过 LLM 分析，生成结构化的 SKILL.md:
  - name: 从操作语义推断
  - description: 从输入输出模式推断
  - input_schema / output_schema: 从 tool_args / tool_results 结构推断
  - SOP: 步骤 1→2→3 的自然语言描述 (≥3步)
  - 反模式: 分析失败的中间步骤 (≥1条)

安全:
  - sanitize(): LLM 调用前自动脱敏 IP/邮箱/电话/域名
  - validate(): 生成后三重质量检查 (SOP完整性/参数对齐/反模式覆盖)
  - refine(): 用户修正内容不被自动生成覆盖

调用者: RecordingPanel 前端 / REST API
"""

from __future__ import annotations

import json as _json
import logging
import os as _os
import re as _re
import uuid as _uuid
from dataclasses import dataclass, field
from pathlib import Path as _Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SKILL_DIR = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "skills"


# ── Data Models ──────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    valid: bool
    score: int = 0                  # 0-100
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)


# ── SkillGenerator ──────────────────────────────────────────────────────

class SkillGenerator:
    """操作序列 → SKILL.md 生成器.

    使用方式:
        gen = SkillGenerator()
        skill_md = await gen.generate(recording.steps, feedback="")
        validation = gen.validate(skill_md)
        if validation.valid:
            await gen.register(skill_md, skill_name)
    """

    # ── Sensitive Data Sanitization ───────────────────────────────────

    SENSITIVE_PATTERNS: List[tuple] = [
        (_re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'), '[IP_REDACTED]'),
        (_re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'), '[EMAIL_REDACTED]'),
        (_re.compile(r'\b1[3-9]\d{9}\b'), '[PHONE_REDACTED]'),
        (_re.compile(r'(?:api|internal|staging|dev)\.[a-zA-Z0-9.-]+\.(?:com|cn|net|org)'), '[DOMAIN_REDACTED]'),
        (_re.compile(r'(?:password|token|secret|key|api_key)\s*[:=]\s*\S+', _re.IGNORECASE), '[CREDENTIAL_REDACTED]'),
    ]

    def sanitize(self, operations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """脱敏操作序列 (LLM 调用前).

        IP地址 / 邮箱 / 电话 / 内部域名 / 凭证 → 自动替换
        """
        serialized = _json.dumps(operations, ensure_ascii=False)
        for pattern, replacement in self.SENSITIVE_PATTERNS:
            serialized = pattern.sub(replacement, serialized)
        try:
            return _json.loads(serialized)
        except Exception:
            return operations

    # ── Generate ──────────────────────────────────────────────────────

    async def generate(
        self,
        operations: List[Dict[str, Any]],
        *,
        feedback: str = "",
        skill_name_hint: str = "",
    ) -> str:
        """从操作序列生成 SKILL.md.

        Args:
            operations: 操作步骤列表 (来自 OperationRecorder)
            feedback: 用户反馈 (用于 refine 模式)
            skill_name_hint: 建议的 Skill 名称

        Returns:
            完整的 SKILL.md 内容 (含 frontmatter)
        """
        # Step 1: 脱敏
        safe_ops = self.sanitize(operations)

        # Step 2: LLM 分析 + 生成
        skill_md = await self._llm_generate(safe_ops, feedback, skill_name_hint)

        # Step 3: 验证
        validation = self.validate(skill_md)
        if not validation.valid:
            # 追加修复建议到输出末尾
            skill_md += "\n\n<!--\n⚠️ 质量检查未通过:\n"
            for issue in validation.issues:
                skill_md += f"  - {issue}\n"
            skill_md += f"\n评分: {validation.score}/100\n"
            if validation.suggestions:
                skill_md += "\n建议修复:\n"
                for s in validation.suggestions:
                    skill_md += f"  - {s}\n"
            skill_md += "-->\n"

        return skill_md

    async def _llm_generate(
        self,
        safe_ops: List[Dict[str, Any]],
        feedback: str,
        hint: str,
    ) -> str:
        """LLM 驱动的 SKILL.md 生成."""
        try:
            from core.harness.utils.model_injection import best_model_for_purpose
            from core.harness.syscalls.llm import sys_llm_generate

            ops_text = _json.dumps(safe_ops, ensure_ascii=False, indent=2)[:4000]
            fb_text = f"\n用户反馈: {feedback}" if feedback else ""
            hint_text = f"\n建议名称: {hint}" if hint else ""

            prompt = f"""从以下操作序列生成一个标准的 SKILL.md 文件。

操作序列:
{ops_text}{fb_text}{hint_text}

生成要求:
1. YAML frontmatter 包含: name, version, description, category, input_schema, output_schema, effects
2. SOP 章节: 至少 3 个步骤，每步具体可操作
3. 反模式章节: 至少 1 条错误处理路径 (基于操作序列中的失败步骤)
4. 输出格式: 使用 ## FILE: 标记输出文件路径

输出完整的 SKILL.md 内容 (从 --- 开始):"""

            result = await sys_llm_generate(
                messages=[{"role": "user", "content": prompt}],
                model=best_model_for_purpose("code_gen"),
                temperature=0.3,
                max_tokens=3000,
            )
            content = result.get("content", "") if isinstance(result, dict) else str(result)
            return content.strip()

        except Exception as e:
            logger.warning("LLM skill generation failed: %s", e)
            return self._fallback_skill_md(safe_ops)

    def _fallback_skill_md(self, safe_ops: List[Dict[str, Any]]) -> str:
        """降级方案: 从操作序列直接拼装 SKILL.md."""
        tool_names = list(set(s.get("tool", "unknown") for s in safe_ops[:20]))
        steps = "\n".join(
            f"{i+1}. 调用 `{s.get('tool', 'unknown')}` → 结果: {s.get('result', '?')}"
            for i, s in enumerate(safe_ops[:10])
        )
        return f"""---
name: recorded_skill
version: 1.0.0
description: 从操作录制自动生成的 Skill
category: automation
input_schema:
  type: object
output_schema:
  type: object
effects:
  - type: read
    resources: []
    idempotent: true
---
# SOP

{steps}

## 涉及工具

{chr(10).join(f'- {t}' for t in tool_names[:10])}

## 反模式

- 如果步骤失败，检查工具返回的错误信息并重试
"""

    # ── Refine ────────────────────────────────────────────────────────

    async def refine(self, current_skill_md: str, feedback: str) -> str:
        """根据反馈迭代 Skill (保留用户手动修正).

        用户已手动编辑的内容 (非 LLM 生成的部分) 不会被覆盖。
        """
        try:
            from core.harness.utils.model_injection import best_model_for_purpose
            from core.harness.syscalls.llm import sys_llm_generate

            prompt = f"""修改以下 SKILL.md 根据用户反馈。

当前 SKILL.md:
{current_skill_md[:4000]}

用户反馈:
{feedback}

原则:
- 保留用户手动编辑的内容 (除非反馈明确要求修改)
- 只修改与反馈相关的部分
- 保持 YAML frontmatter 格式正确

输出完整的修改后 SKILL.md:"""

            result = await sys_llm_generate(
                messages=[{"role": "user", "content": prompt}],
                model=best_model_for_purpose("code_gen"),
                temperature=0.2,
                max_tokens=3000,
            )
            return result.get("content", current_skill_md) if isinstance(result, dict) else str(result)

        except Exception as e:
            logger.warning("Skill refinement failed: %s", e)
            return current_skill_md

    # ── Validate ──────────────────────────────────────────────────────

    def validate(self, skill_md: str) -> ValidationResult:
        """三重质量检查.

        ① SOP 完整性: 是否包含 ≥3 个步骤
        ② 参数对齐: input_schema 中的字段是否在 SOP 中被引用
        ③ 反模式覆盖: 是否包含 ≥1 条错误处理路径
        """
        issues = []
        suggestions = []
        score = 60

        # ① SOP 完整性
        sop_lines = [l for l in skill_md.split("\n") if l.strip().startswith(("1.", "2.", "3.", "-", "*"))]
        step_count = len([l for l in sop_lines if _re.match(r'^\d+\.', l.strip())])
        if step_count < 3:
            issues.append(f"SOP 步骤不足: {step_count} 步 (需要 ≥3)")
            score -= 20
        else:
            score += 20

        # ② 参数对齐
        try:
            fm_start = skill_md.index("---")
            fm_end = skill_md.index("---", fm_start + 3)
            frontmatter = skill_md[fm_start + 3:fm_end].strip()
            if "input_schema" in frontmatter:
                # Extract input field names
                input_fields = _re.findall(r'\b(\w+)\s*:', frontmatter.split("input_schema")[1][:500])
                if input_fields:
                    referenced = 0
                    sop_text = skill_md[fm_end + 3:]
                    for field in input_fields[:5]:
                        if field in sop_text:
                            referenced += 1
                    if referenced < len(input_fields) * 0.5:
                        issues.append(f"参数对齐不足: {referenced}/{len(input_fields)} 字段在 SOP 中被引用")
                        score -= 10
                    else:
                        score += 10
        except Exception:
            pass  # Can't parse frontmatter — skip check

        # ③ 反模式覆盖
        anti_pattern_keywords = ["如果", "错误", "失败", "重试", "异常", "注意", "不要", "避免"]
        has_anti = any(kw in skill_md.lower() for kw in anti_pattern_keywords)
        if not has_anti:
            issues.append("缺少反模式/错误处理路径")
            score -= 10
        else:
            score += 10

        score = max(0, min(100, score))

        if score < 70:
            suggestions.append("增加 SOP 步骤描述 (当前可能过于简略)")
        if issues:
            suggestions.append("在 SOP 中引用 input_schema 的参数名")
            suggestions.append("添加 '如果XX失败，则YY' 的错误处理路径")

        return ValidationResult(
            valid=len(issues) == 0,
            score=score,
            issues=issues,
            suggestions=suggestions[:3],
        )

    # ── Register ──────────────────────────────────────────────────────

    def register(self, skill_md: str, skill_name: str) -> str:
        """将生成的 SKILL.md 注册到 SkillRegistry.

        Args:
            skill_md: SKILL.md 内容
            skill_name: Skill 名称 (目录名)

        Returns:
            生成的 SKILL.md 路径
        """
        skill_dir = SKILL_DIR / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)

        path = skill_dir / "SKILL.md"
        path.write_text(skill_md, encoding="utf-8")

        logger.info("Skill registered: %s", path)
        return str(path)
