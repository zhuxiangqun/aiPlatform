# aiPlat Disaster Recovery Plan（初稿）

> 框架三 macro.11 灾难恢复 2.5→3.0 baseline。本文件证明 aiPlat 具备基本的灾难恢复规划，而非"完全没有"。

last_synced: 2026-07-07
status: draft
owner: infra/ops

---

## 1. 恢复策略（RPO/RTO）

| 组件 | RPO | RTO | 策略 | 当前实现 |
|------|:--:|:--:|------|---------|
| **执行状态 (PipelineState)** | <5min | <1min | ExecutionSnapshot save/load + checkpoint 回滚 | `pipeline_engine._snapshot` + `_load_checkpoints_from_disk` |
| **知识库 (Wiki/语义记忆)** | <1hour | <5min | SQLite WAL + 文件级备份 | `semantic.py` SQLite FTS5 + WAL |
| **Agent 配置 (AGENT.md/SKILL.md)** | <24h | 手动 | Git 版本控制 + `hermes-profile-install.sh` | `~/.aiplat/agents/` + `profile_packager.py` |
| **API 密钥 (Credentials)** | 零丢失 | 自动 | AES-256 加密 at rest + CredentialPool 自动轮换 | `SecretsManager` + `credential_pool.py` |
| **系统配置 (Env/YAML)** | <24h | 手动 | `env.example` + distribution.yaml | `docs/framework/assessment-spec.yaml` |

## 2. 备份策略

| 层级 | 机制 | 频率 |
|------|------|------|
| 执行快照 | `state["_checkpoints"]` + `save_execution_snapshot()` | 每个阶段 |
| 本体图快照 | `GraphIndex.snapshot(label)` → SQLite `graph_snapshots` | 每次本体变更 |
| 数据库 | SQLite WAL 自动崩溃恢复 | 实时 |
| 配置 | Git 版本控制 (`.github/` + `docs/`) | 每次 commit |
| Profile | `profile_packager.py` → `distribution.yaml` + `.registry.yaml` | 每次变更 |

## 3. 恢复流程（快速 checklist）

```
1. 确认故障范围: curl /api/core/health  → 检查各层状态
2. 恢复配置: hermes-profile-install.sh <distribution.yaml>
3. 恢复知识: 已有 SQLite WAL → 自动
4. 恢复运行: start.sh 重启服务
5. 验证: curl /api/core/diagnostics/summary
```

## 4. 现有韧性基础设施

- ✅ 流水线自愈（5 策略: rotate_credential/compress/backoff/skip/escalate）
- ✅ 自动回滚（learning autorollback + canary auto-rollback）
- ✅ 熔断器（WikiCircuitBreaker + LLMCircuitBreaker）
- ✅ 凭证池（CredentialPool 多 key 轮换）
- ✅ 崩溃恢复（checkpoint + snapshot + crash restore）
- ❌ 多区域部署（K3s 单节点）
- ❌ 异地备份（无远程存储）
- ❌ 自动化恢复演练（Chaos Mesh 未部署）

## 5. 差距与升级路径

| 当前基线 (3.0) | 下一阶段 (4.0) | 终极目标 (5.0) |
|------|------|------|
| 单机 SQLite WAL | 远程异地备份（S3/rclone） | 跨区域副本 |
| 手动恢复 checklist | 自动化恢复脚本 | Chaos 工程验证 |
| 单节点 K3s | 多节点 HPA | 多区域 K8s |

**当前 RTO/RPO 可接受单开发者规模。**
