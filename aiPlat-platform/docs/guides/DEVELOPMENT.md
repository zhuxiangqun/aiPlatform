# 平台层开发规范

> 继承系统级开发规范，针对平台层的特定要求

---

## 继承规范

本文档继承 [系统级开发规范](../../../docs/guides/DEVELOPMENT.md)，所有系统级规范在本层必须遵守。

---

## 特定规范

### 层级定位

平台层（Layer 2）对外暴露 API，提供平台级服务，依赖核心层：

```
aiPlat-platform (Layer 2)
    ↓ 依赖
    aiPlat-core（通过 CoreFacade）
    ↑ 被依赖
    aiPlat-app（通过 REST/GraphQL API）
```

**允许的依赖**：
- ✅ `aiPlat_core`（通过 CoreFacade）
- ✅ Python 标准库
- ✅ 第三方库（FastAPI, GraphQL 等）

**禁止的依赖**：
- ❌ `aiPlat_infra`（应通过 core 层间接访问）
- ❌ `aiPlat_app`

---

## API 设计规范

### REST API 规范

```python
# platform/api/agents.py
from fastapi import APIRouter, Depends, HTTPException
from typing import Any

router = APIRouter(prefix="/agents", tags=["agents"])

@router.post("/", response_model=AgentResponse)
async def create_agent(
    request: CreateAgentRequest,
    current_user: User = Depends(get_current_user)
) -> AgentResponse:
    """创建 Agent"""
    ...

@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: str,
    current_user: User = Depends(get_current_user)
) -> AgentResponse:
    """获取 Agent"""
    ...

@router.post("/{agent_id}/execute", response_model=ExecuteResponse)
async def execute_agent(
    agent_id: str,
    request: ExecuteRequest,
    current_user: User = Depends(get_current_user)
) -> ExecuteResponse:
    """执行 Agent"""
    ...
```

### 认证规范

```python
# platform/auth/jwt.py
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer

security = HTTPBearer()

async def get_current_user(token: str = Depends(security)) -> User:
    """获取当前用户"""
    try:
        payload = decode_jwt(token.credentials)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        return await get_user(user_id)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
```

---

## 开发检查清单

- [ ] API 版本管理（/api/v1/）
- [ ] 认证授权检查
- [ ] 请求验证
- [ ] 错误处理（统一错误格式）
- [ ] 日志记录
- [ ] 编写单元测试（覆盖率 ≥ 70%）
- [ ] 编写集成测试（覆盖率 ≥ 70%）

---

## 测试规范

详细测试规范见：[系统级测试指南](../../../docs/TESTING_GUIDE.md)

| 测试类型 | 覆盖率要求 |
|----------|-----------|
| 单元测试 | ≥ 70% |
| 集成测试 | ≥ 70% |

---

## 相关链接

- [系统级开发规范](../../../docs/guides/DEVELOPMENT.md)
- [系统级测试指南](../../../docs/TESTING_GUIDE.md)
- [platform层部署指南](./DEPLOYMENT.md)

---

*最后更新: 2026-04-11*
