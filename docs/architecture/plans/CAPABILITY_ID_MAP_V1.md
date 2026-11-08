# Capability ID Map v1（冻结稿）

> **类型**：契约冻结 / P0 阻塞前置  
> **版本**：`capability_id_map.v1` · 2026-11-08  
> **状态**：**Frozen**（owner 已签）  
> **权威消费**：覆盖报表、Suite Profile quotas、`EvalCase.capabilities`、legacy alias 解析  
> **关联**：[eval-capability-driven-case-pack.md](./eval-capability-driven-case-pack.md) §4.2 · [ADR-EVAL-CAPABILITY-CASE-PACK-V1.md](../decisions/ADR-EVAL-CAPABILITY-CASE-PACK-V1.md) §6.1

---

## 0. 冻结元数据


| 字段                | 值                                  |
| ----------------- | ---------------------------------- |
| schema            | `eval.capability_id_map.v1`        |
| map_version       | `1.0.0`                            |
| object_type_focus | `agent`（Prompt/KB 等另表扩展）           |
| owner             | 朱向群（评测方法负责人）                       |
| approved_at       | 2026-11-08                         |
| change_policy     | **改映射 = bump map_version**；禁止原地改语义 |


---



## 1. 规则（硬）

1. **canonical_id 是唯一主键**；覆盖报表 / Profile quotas **只认 canonical**。
2. **legacy_id 仅 alias**；解析时 `legacy → canonical`，写入新 case 时只写 canonical。
3. 未知 legacy → **fail closed**（报错或标 `unknown_capability`），禁止静默丢弃。
4. 同一 canonical 可有多个 legacy；同一 legacy **不得**映射到两个 canonical。
5. 新 ID 只能追加到本表新版本；删除 legacy 须 deprecate 一行并保留历史。

---



## 2. Canonical 能力表（Agent）


| matrix_id | canonical_id        | 中文名      | v1_in_scope（现行 = v1.1） |
| --------- | ------------------- | -------- | ----------------------- |
| A1        | `task_completion`   | 任务理解与完成  | yes                     |
| A2        | `planning`          | 计划与分解    | limited                 |
| A3        | `tool_selection`    | 工具选择     | **yes（mock）** · ≠ live |
| A4        | `tool_args`         | 工具参数正确性  | **yes（mock）** · ≠ live |
| A5        | `tool_result_use`   | 工具结果使用   | **yes（mock）** · ≠ live |
| A6        | `error_recovery`    | 错误检测与恢复  | limited（措辞/定位）          |
| A7        | `safety`            | 安全/拒绝/转交 | yes                     |
| A8        | `multi_turn_memory` | 多轮记忆     | **yes（session）**       |
| A9        | `long_context`      | 长上下文/检索  | **yes（fixture）**       |
| A10       | `robustness`        | 鲁棒性/抗干扰  | yes                     |
| A11       | `efficiency`        | 效率/成本    | yes                     |
| A12       | `observability`     | 可观测性     | yes                     |
| A13       | `clarification`     | 缺信息追问/澄清 | yes                     |


`v1_in_scope` 细节以 [eval-capability-driven-case-pack.md](./eval-capability-driven-case-pack.md) §4.2.2（`SIGNED v1_1_measurable_subset`）为准。升域工程：[eval-agent-tool-session-inscope.md](./eval-agent-tool-session-inscope.md)（T0–T3 Done）。claim / Certification 仍关闭。

---



## 3. Legacy ↔ Canonical 全量映射

来源：`aiPlat-core/core/engine/eval_sets/applicability_draft.json` 全量扫描 + Agent 矩阵扩展。


| legacy_id            | canonical_id        | 说明                                      |
| -------------------- | ------------------- | --------------------------------------- |
| `clarify_or_ask`     | `clarification`     | **必保**：`default/missing_info` 依赖此 alias |
| `error_recovery`     | `error_recovery`    | 同名                                      |
| `multi_turn_memory`  | `multi_turn_memory` | 同名；v1 Profile 默认不配额                     |
| `skill_invoke`       | `task_completion`   | Agent 技能调用→任务完成                         |
| `http_chat_pull`     | `task_completion`   | 外部 HTTP 目标                              |
| `pi_export`          | `task_completion`   | 生成应用导出                                  |
| `format_constraint`  | `task_completion`   | Prompt 格式约束（对象扩展前 alias）                |
| `consistency`        | `robustness`        | 一致性≈抗扰                                  |
| `multi_slot_context` | `long_context`      | 多槽位上下文                                  |
| `long_chain`         | `planning`          | 长链≈分解                                   |


**显式不存在的 legacy 不得发明。** 若代码新增 capability 字符串，须先改本表再合并。

---



## 4. 解析伪代码

```text
resolve(id):
  if id in CANONICAL_SET: return id
  if id in LEGACY_MAP: return LEGACY_MAP[id]
  raise UnknownCapabilityId(id)
```

覆盖报表：先 `resolve`，再按 canonical 聚合。

---



## 5. 验收清单

- [x] `clarify_or_ask → clarification` 存在且唯一  
- [x] A13 `clarification` 在 canonical 表  
- [x] applicability_draft 中每个 capability 字符串均有映射  
- [x] 无一对多 / 多对一冲突  
- [x] owner + approved_at 已填  
- [x] ADR §6.1 #1 勾选  

---



## 6. 签字栏


| 角色        | 签字（GitHub Approve / 评论 `SIGNED capability_id_map.v1`） | 日期  |
| --------- | ----------------------------------------------------- | --- |
| 评测方法负责人   | `SIGNED capability_id_map.v1` · 朱向群                   | 2026-11-08 |
| 工程负责人（可选） |                                                       |     |


**已签字：状态 Frozen；实施变更单可宣称「对照表已冻结」。**