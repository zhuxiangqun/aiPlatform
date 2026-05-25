"""
Code generation Skill handler — routes through CodeGenerationSkill.execute().

Execution mode is handler-based (execution_mode: handler). The SkillExecutor
detects the Python CodeGenerationSkill class with execute() method and calls it
directly rather than creating a temporary prompt-based agent.

The actual implementation lives in core/apps/skills/base.py::CodeGenerationSkill.
"""
