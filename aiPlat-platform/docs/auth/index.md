# auth 模块（Platform Layer 2：身份认证与授权）

## 定位

platform 层是**唯一权威**的身份与权限解析/签发方。`auth/` 负责 JWT/API Key 的解析和身份注入，下游（core/app）只消费注入的身份信息，不得自行推断或扩权。

## 已实现能力

| 能力 | 代码位置 | 状态 |
|------|---------|:--:|
| JWT 解析与验证 | platform/auth/identity_provider.py | ✅ |
| API Key 验证 | platform/auth/ | ✅ |
| tenant_id + actor_id + scopes 注入 | 标准透传 headers | ✅ |
| SSO/OIDC 集成 | Keycloak/Azure AD/Okta | ✅ |
| 用户注册 → 邮箱验证 → API Key 发放 | api/rest/routes.py | ✅ |
| 标准透传 headers | X-AIPLAT-REQUEST-ID/TENANT-ID/ACTOR-ID/SCOPES | ✅ |

## 边界

- platform 只做身份解析和注入，不做权限判断
- 权限判断在 core 的 PolicyGate 中统一执行
- 不管理用户存储（委托给 Identity Provider）

## 透传 headers

```
X-AIPLAT-REQUEST-ID  → 请求追踪 ID
X-AIPLAT-TENANT-ID   → 租户 ID
X-AIPLAT-ACTOR-ID    → 用户 ID
X-AIPLAT-SCOPES      → 逗号分隔的权限范围
```
