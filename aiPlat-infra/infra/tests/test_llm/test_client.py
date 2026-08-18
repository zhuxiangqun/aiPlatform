"""llm 模块测试"""

import pytest


class TestLLMClient:
    """LLM 客户端测试"""

    def test_openai_client(self):
        """测试 OpenAI 兼容客户端（openai.py 已合并为 openai_compatible.py）"""
        from infra.llm.providers.openai_compatible import OpenAICompatibleClient
        from infra.llm.schemas import LLMConfig

        config = LLMConfig(provider="openai", model="gpt-4")
        client = OpenAICompatibleClient(config)
        assert client is not None


class TestLLMConfig:
    """LLM 配置测试"""

    def test_llm_models(self):
        """测试 LLM 模型配置"""
        from infra.llm.schemas import LLMConfig

        config = LLMConfig(provider="openai", model="gpt-4")
        assert config.model == "gpt-4"


class TestCostTracker:
    """成本追踪测试"""

    def test_cost_calculation(self):
        """测试成本计算（pricing 由配置注入，未注入时默认免费）"""
        from infra.llm.cost_tracker import CostTracker

        tracker = CostTracker(pricing={"gpt-4": {"prompt": 30.0, "completion": 60.0}})
        cost = tracker.calculate(
            model="gpt-4",
            input_tokens=100,
            output_tokens=50,
        )
        assert cost > 0

    def test_cost_zero_without_pricing(self):
        """无 pricing 注入时默认免费（本地模型安全默认）"""
        from infra.llm.cost_tracker import CostTracker

        tracker = CostTracker()
        assert tracker.calculate("gpt-4", 100, 50) == 0.0
