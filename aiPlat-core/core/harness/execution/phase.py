"""Harness 内核级 Pipeline 阶段常量（通用，无业务概念）。

替代 BuilderSessionPhase 的业务枚举依赖。
所有阶段名称均为字符串常量，可直接比较或作为 state key 使用。
"""


class PipelinePhase:
    """Pipeline 执行阶段的通用标识符。

    这些常量不绑定任何业务模块的语义。
    状态机使用阶段名称做字符串匹配，而非枚举类型比较。
    """

    DIALOGUE = "dialogue"
    EXECUTING = "executing"
    PAUSED = "paused"
    DONE = "done"
    FAILED = "failed"
