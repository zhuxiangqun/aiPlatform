"""
Prompt Audit Rules — extractable check definitions for AGENT.md quality.

These are consumed by prompt_auditor.py. Add new check patterns here.
"""

# Vague adjective patterns (Rule 1: AI 不能执行形容词)
# Format: (regex, tag)
VAGUE_ADJECTIVES = [
    (r"写高质量代码", "vague_quality_code"),
    (r"遵循最佳实践", "vague_best_practices"),
    (r"注意安全", "vague_security"),
    (r"充分测试", "vague_full_testing"),
    (r"确保代码可维护", "vague_maintainable"),
    (r"编写优雅的", "vague_elegant"),
    (r"高性能", "vague_performance"),
]

# Required handoff fields (Rule 2.1: 交接协议 5 项字段)
HANDOFF_FIELDS = ["做了什么", "产出物在哪", "如何验证", "已知问题", "下一步"]

# Required frontmatter fields for pipeline agents
PIPELINE_FM_FIELDS = ["agent_type", "output_artifact", "phase"]
