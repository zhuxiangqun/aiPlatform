"""config 模块测试"""

import pytest
import os
from dataclasses import asdict

from infra.config.config import Config
from infra.config.schemas import (
    DatabaseConfig,
    LLMConfig,
    FileSourceSetting,
    EnvSourceSetting,
)


class TestConfig:
    """Config 对象测试"""

    def test_config_get(self):
        """测试 get 方法"""
        data = {"database": {"host": "localhost", "port": 5432}}
        config = Config(data)

        assert config.get("database.host") == "localhost"
        assert config.get("database.port") == 5432
        assert config.get("nonexistent", "default") == "default"

    def test_config_set(self):
        """测试 set 方法"""
        config = Config({})
        config.set("database.host", "localhost")

        assert config.get("database.host") == "localhost"

    def test_config_has(self):
        """测试 has 方法"""
        data = {"database": {"host": "localhost"}}
        config = Config(data)

        assert config.has("database.host") is True
        assert config.has("database.password") is False

    def test_config_as_dict(self):
        """测试 as_dict 方法"""
        data = {"database": {"host": "localhost"}}
        config = Config(data)

        result = config.as_dict()
        assert result["database"]["host"] == "localhost"

    def test_config_nested_get(self):
        """测试嵌套键获取"""
        data = {"database": {"connection": {"host": "localhost", "port": 5432}}}
        config = Config(data)

        assert config.get("database.connection.host") == "localhost"
        assert config.get("database.connection.port") == 5432


class TestSchemas:
    """数据模型测试"""

    def test_database_config(self):
        """测试 DatabaseConfig"""
        config = DatabaseConfig(host="localhost", port=5432)
        assert config.host == "localhost"
        assert config.port == 5432

    def test_llm_config(self):
        """测试 LLMConfig"""
        config = LLMConfig(provider="openai", model="gpt-4")
        assert config.provider == "openai"
        assert config.model == "gpt-4"

    def test_file_source_setting(self):
        """测试 FileSourceSetting"""
        setting = FileSourceSetting(
            path="config/infra/default.yaml", priority=50, enabled=True
        )
        assert setting.path == "config/infra/default.yaml"
        assert setting.priority == 50
        assert setting.enabled is True

    def test_env_source_setting(self):
        """测试 EnvSourceSetting"""
        setting = EnvSourceSetting(priority=100, enabled=True)
        assert setting.priority == 100
        assert setting.enabled is True
