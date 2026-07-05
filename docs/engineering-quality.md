# aiPlat 工程质量标准

## PR 审查要求

### 必须通过 (MUST)

| Gate | 工具 | 阻断? |
|:---|:---|:--:|
| Lint | `ruff check core/` | ✅ 阻断 |
| Type Check | `mypy core/ --ignore-missing-imports` | ⚠️ 警告 |
| Unit Tests | `pytest tests/ -v --tb=short -q` | ✅ 阻断 |
| L5 Depth Tests | `pytest tests/autonomy/test_l5_capabilities.py -v` | ✅ 阻断 |
| Architecture Guard | `bash scripts/architecture_guard.sh` | ✅ 阻断 |
| Frontend Build | `cd frontend && npm run build` | ✅ 阻断 (仅前端改动) |

### 推荐通过 (SHOULD)

| Gate | 工具 | 阻断? |
|:---|:---|:--:|
| Coverage | `pytest --cov=. --cov-report=term` | ⚠️ 不降低 |
| Complexity | `radon cc core/ -a -nc` | ⚠️ 无新增 D-F |
| Commitlint | `commitlint` | ⚠️ 警告 |

## 分支保护规则

以下配置在 GitHub → Settings → Branches → Add rule 中设置：

```yaml
branches: [main]
rules:
  - require_pull_request: true
    required_approving_review_count: 1
    dismiss_stale_reviews: true
    require_code_owner_review: false
  
  - require_status_checks: true
    strict: true
    contexts:
      - "Lint & Type Check"
      - "Test (aiPlat-core)"
      - "L5 Depth Tests"
      - "Architecture Compliance > guard"
  
  - require_conversation_resolution: true
  - restrict_pushes: true
  - enforce_admins: true
```

## CODEOWNERS (推荐)

```bash
# aiPlat-core
aiPlat-core/core/harness/execution/ @platform-team
aiPlat-core/core/harness/infrastructure/gates/ @security-team

# aiPlat-infra
aiPlat-infra/infra/management/model/ @model-team

# Documentation
docs/ @architecture-team
```

## 质量仪表盘

启动后访问 `http://localhost:8000/overview/overview.html` 查看:
- 四层健康状态
- 架构守卫通过率
- L0-L5 自主性等级
