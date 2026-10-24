# MB-01 / E-06 再核实（2026-10-24）

> 首切片合入后盘点；**Gate 2 批准后**开始分批改经 CoreFacade。

## 1. 分层结果（以代码为准）

| 层 | 结果 |
|----|------|
| **platform** `aiPlat-platform/apps/fde` | **0** `from core.harness` — 经 CoreFacade |
| **core** `aiPlat-core/core/apps/fde` | Gate2 首批：knowledge / ontology_engine / knowledge_pipeline / 相关 gates·store **已改** `from core.api.core_facade` |

残留（非 E-06 主债 / 下一批）：

- `service/agent.py` → `interfaces.agent`（AgentContext/Config）
- `prompts/__init__.py` → `prompt_loader._register`
- `service/_archive/builder.py` → archive，不接线

## 2. 结论

| 项 | 状态 |
|----|------|
| MB-01 首批 | ✅ 已实施（Gate2） |
| 全量清零 | 未宣称；按残留清单续批 |
| Gate 3 | ❌ 未批 |

## 3. 解耦顺序（续）

1. ~~映射已有 Facade 导出~~  
2. ~~缺口补 re-export（PolicyDecision / OntologyCaseStore / register_all / embed / OWL / json_change_diff 等）~~  
3. 残留 interfaces / prompts 小批  
4. 禁止搬目录或拆微服务  
