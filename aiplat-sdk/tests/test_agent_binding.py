"""P0-B1 回归测试：SDK Agent.bind_skill/bind_tool 不再 AttributeError。

修复前：__init__ 未初始化 _skills/_tools → bind_skill/bind_tool 抛 AttributeError。
修复后：初始化空列表，绑定生效。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aiplat import Agent


def test_bind_skill_initializes():
    a = Agent(name="t")
    a.bind_skill("code_generation")
    assert a._skills == ["code_generation"]


def test_bind_tool_initializes():
    a = Agent(name="t")
    a.bind_tool("file_operations")
    assert a._tools == ["file_operations"]


def test_bind_both():
    a = Agent(name="t")
    a.bind_skill("s1").bind_tool("t1").bind_tool("t2")
    assert a._skills == ["s1"]
    assert a._tools == ["t1", "t2"]


def test_no_bind_empty():
    a = Agent(name="t")
    assert a._skills == []
    assert a._tools == []
