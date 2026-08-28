"""test_llm_syscall_store.py — LLM syscall 事件存储修复回归测试（2026-08-28）。

覆盖 chat 发送失败根因修复：
llm.py sys_llm_generate 的 syscall 事件记录（add_syscall_event）必须走
execution_store（syscall_mixin 提供该方法），不得使用 get_tenant_store()
（平台 TenantStore 仅租户配额/策略，无 add_syscall_event——修复前 platform
注入 tenant store 后每次 LLM 调用抛 AttributeError，chat 端点超时，
前端显示「发送失败，请重试」）。
"""
from __future__ import annotations

from pathlib import Path

_CORE_ROOT = Path(__file__).resolve().parents[4]


def test_sys_llm_generate_uses_execution_store_not_tenant_store():
    """sys_llm_generate 的 store 必须来自 runtime.execution_store。"""
    src = (_CORE_ROOT / "core/harness/syscalls/llm.py").read_text(encoding="utf-8")
    # 修复后所有 store 获取点统一为 execution_store
    assert "getattr(runtime, \"execution_store\", None)" in src
    # 不得再通过 get_tenant_store() 获取 syscall 事件 store
    assert "get_tenant_store() or" not in src
    assert "store = get_tenant_store" not in src
    # add_syscall_event 必须存在于 ExecutionStore（syscall_mixin）
    mixin_src = (_CORE_ROOT / "core/services/execution_store/syscall_mixin.py").read_text(
        encoding="utf-8"
    )
    assert "async def add_syscall_event" in mixin_src


def test_tenant_store_has_no_syscall_event_method():
    """平台 TenantStore 不应承担 syscall 事件记录（职责边界）。"""
    # 平台 TenantStore 类不得定义 add_syscall_event
    tenant_src = (
        _CORE_ROOT.parent / "aiPlat-platform/tenants/tenant_store.py"
    ).read_text(encoding="utf-8")
    assert "add_syscall_event" not in tenant_src
