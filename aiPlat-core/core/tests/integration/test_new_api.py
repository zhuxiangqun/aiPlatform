"""
Core API 集成测试

测试新增的 API 端点一致性 - 现在测试 server.py
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime


class TestSkillAPIConsistency:
    """Skill API 端点一致性测试"""
    
    @pytest.mark.asyncio
    async def test_trigger_conditions_endpoints_defined(self):
        """测试 trigger_conditions 端点已定义"""
        from core.server import api_router
        
        routes_list = [r.path for r in api_router.routes]
        
        assert "/skills/{skill_id}/trigger-conditions" in routes_list
        assert "/skills/{skill_id}/test-trigger" in routes_list
    
    @pytest.mark.asyncio
    async def test_evolution_endpoints_defined(self):
        """测试 evolution 端点已定义"""
        from core.server import api_router
        
        routes_list = [r.path for r in api_router.routes]
        
        assert "/skills/{skill_id}/evolution" in routes_list
        assert "/skills/{skill_id}/lineage" in routes_list
        assert "/skills/{skill_id}/captures" in routes_list
        assert "/skills/{skill_id}/derived" in routes_list
    
    @pytest.mark.asyncio
    async def test_all_new_skill_endpoints_count(self):
        """测试新增端点数量"""
        from core.server import api_router
        
        routes_list = [r.path for r in api_router.routes]
        
        new_endpoints = [
            "/skills/{skill_id}/trigger-conditions",
            "/skills/{skill_id}/test-trigger",
            "/skills/{skill_id}/evolution",
            "/skills/{skill_id}/lineage",
            "/skills/{skill_id}/captures",
            "/skills/{skill_id}/fixes",
            "/skills/{skill_id}/derived"
        ]
        
        found_count = sum(1 for ep in new_endpoints if ep in routes_list)
        
        assert found_count >= 6


class TestMemoryStatsEndpoint:
    """Memory stats 端点测试"""
    
    @pytest.mark.asyncio
    async def test_memory_stats_endpoint_defined(self):
        """测试 memory/stats 端点已定义"""
        from core.server import api_router
        
        routes_list = [r.path for r in api_router.routes]
        
        assert "/memory/stats" in routes_list


class TestCoreAPIClientConsistency:
    """CoreAPIClient 方法一致性测试"""
    
    def test_client_has_trigger_conditions_methods(self):
        """测试 Client 包含 trigger_conditions 方法"""
        from management.core_client import CoreAPIClient
        
        assert hasattr(CoreAPIClient, 'get_skill_trigger_conditions')
        assert hasattr(CoreAPIClient, 'update_skill_trigger_conditions')
        assert hasattr(CoreAPIClient, 'test_skill_trigger')
    
    def test_client_has_evolution_methods(self):
        """测试 Client 包含 evolution 方法"""
        from management.core_client import CoreAPIClient
        
        assert hasattr(CoreAPIClient, 'get_skill_evolution_status')
        assert hasattr(CoreAPIClient, 'trigger_skill_evolution')
        assert hasattr(CoreAPIClient, 'get_skill_lineage')
        assert hasattr(CoreAPIClient, 'get_skill_captures')
        assert hasattr(CoreAPIClient, 'get_skill_fixes')
        assert hasattr(CoreAPIClient, 'get_skill_derived')
    
    def test_new_methods_count(self):
        """测试新增方法数量"""
        from management.core_client import CoreAPIClient
        
        new_methods = [
            'get_skill_trigger_conditions',
            'update_skill_trigger_conditions',
            'test_skill_trigger',
            'get_skill_evolution_status',
            'trigger_skill_evolution',
            'get_skill_lineage',
            'get_skill_captures',
            'get_skill_fixes',
            'get_skill_derived'
        ]
        
        found = sum(1 for m in new_methods if hasattr(CoreAPIClient, m))
        
        assert found >= 8


class TestAPIClientMethodSignature:
    """API 方法签名测试"""
    
    def test_get_skill_trigger_conditions_signature(self):
        """测试获取触发条件方法签名"""
        from management.core_client import CoreAPIClient
        import inspect
        
        sig = inspect.signature(CoreAPIClient.get_skill_trigger_conditions)
        params = list(sig.parameters.keys())
        
        assert 'skill_id' in params
    
    def test_update_skill_trigger_conditions_signature(self):
        """测试更新触发条件方法签名"""
        from management.core_client import CoreAPIClient
        import inspect
        
        sig = inspect.signature(CoreAPIClient.update_skill_trigger_conditions)
        params = list(sig.parameters.keys())
        
        assert 'skill_id' in params
        assert 'conditions' in params
    
    def test_get_evolution_status_signature(self):
        """测试获取进化状态方法签名"""
        from management.core_client import CoreAPIClient
        import inspect
        
        sig = inspect.signature(CoreAPIClient.get_skill_evolution_status)
        params = list(sig.parameters.keys())
        
        assert 'skill_id' in params
    
    def test_trigger_evolution_signature(self):
        """测试触发进化方法签名"""
        from management.core_client import CoreAPIClient
        import inspect
        
        sig = inspect.signature(CoreAPIClient.trigger_skill_evolution)
        params = list(sig.parameters.keys())
        
        assert 'skill_id' in params
        assert 'trigger_type' in params


class TestEndpointPathConsistency:
    """端点路径一致性测试"""
    
    def test_api_routes_match_client_calls(self):
        """测试 API 路由与 Client 调用匹配"""
        from management.core_client import CoreAPIClient
        from core.server import api_router
        
        client_methods = [
            ('get_skill_trigger_conditions', '/skills/{skill_id}/trigger-conditions'),
            ('update_skill_trigger_conditions', '/skills/{skill_id}/trigger-conditions'),
            ('get_skill_evolution_status', '/skills/{skill_id}/evolution'),
            ('trigger_skill_evolution', '/skills/{skill_id}/evolution'),
            ('get_skill_captures', '/skills/{skill_id}/captures'),
            ('get_skill_derived', '/skills/{skill_id}/derived'),
        ]
        
        routes_list = [r.path for r in api_router.routes]
        
        for method_name, expected_path in client_methods:
            assert hasattr(CoreAPIClient, method_name), f"Missing method: {method_name}"
            
            path_found = expected_path in routes_list
            
            assert path_found, f"Path not found for {method_name}: {expected_path}"
