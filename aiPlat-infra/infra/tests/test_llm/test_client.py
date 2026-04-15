"""llm 模块测试"""

import pytest


class TestLLMClient:
    """LLM 客户端测试"""

    def test_openai_client(self):
        """测试 OpenAI 客户端"""
        from infra.llm.providers.openai import OpenAIClient
        from infra.llm.schemas import LLMConfig

        config = LLMConfig(provider="openai", model="gpt-4")
        client = OpenAIClient(config)
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
        """测试成本计算"""
        from infra.llm.cost_tracker import CostTracker

        tracker = CostTracker()
        cost = tracker.calculate(
            model="gpt-4",
            input_tokens=100,
            output_tokens=50,
        )
        assert cost > 0
