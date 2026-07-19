> ⚠️ **已归档** — 本文档为历史版本，API 引用可能已过期。最新文档请参见 [FDE 交付手册](../fde-delivery-manual.md)。

# FDE 自演进系统操作指南

> **自演进系统 = 系统能自己发现问题、修复问题、不断优化——FDE 只需定期检查，不需要手动运维。**

---

## 0. 自演进是什么

你的系统有四层自动运转能力：

| 层 | 功能 | 触发方式 | 查看手段 |
|:--:|------|------|------|
| **观察层** | 每次健康检查自动记快照，积累历史数据 | `/fde/health` 调用后自动 | `/fde/trends/system` |
| **诊断层** | 5 条规则跨子系统分析：SECI 停滞、证据退化、技能退化、知识断层、收敛失效 | 每 10 次 Agent 对话 + 后台每小时 | `/system/diagnose` |
| **修复层** | 对已知模式自动修复（confidence ≥ 0.9 时激活） | 诊断发现可修复问题后自动 | `/system/heal` |
| **演化层** | 从知识缺口和模式中发现新术语、新方案原型 | 后台每小时 + 诊断触发后 | `/system/evolve` |

**所有操作都是 GraphIndex 读写，零 LLM/token 成本。**

---

## 1. 数据积累预期（重要！）

自演进需要数据。系统刚上线时，诊断和演化返回的会是"数据不足"。

| 功能 | 需要什么数据 | 预计多久生效 |
|------|------|:--:|
| 系统趋势分析 | ≥ 10 条 SystemSnapshot（即 ≥ 5 小时运行） | 半天 |
| SECI 停滞检测 | ≥ 2 周快照数据 | 2 周 |
| 证据退化检测 | ≥ 3 次诊断 | 取决于诊断频率 |
| 知识断层检测 | ≥ 4 周快照数据 | 4 周 |
| 收敛失效检测 | atom_count > 20 | 取决于 Agent 使用频率 |
| 术语自动发布 | 同一概念 ≥ 3 次出现在知识缺口 | 取决于诊断频率 |
| 方案草稿生成 | pattern 原子 ≥ 5 + 跨域 ≥ 2 | 取决于使用频率 |

**这是正常的——不需要手动干预。** 系统会自己积累数据。你只需要确保系统在运行。

---

## 2. 自演进系统操作

### 2.1 日常检查（每周一次）

```bash
# 看后台调度器是否在跑
curl GET /system/overview | jq .scheduler

# 预期输出：
# {"active": true, "interval_seconds": 3600, "mode": "diagnose→heal→evolve (zero token)"}
```

### 2.2 手动全周期自检

当你想主动触发一次完整自检（非等待自动触发）：

```bash
curl -X POST /system/self-check
```

返回三个阶段的结果：
```json
{
  "diagnosis": {"overall_health": "healthy", "findings": [...]},
  "heal": {"auto_fixed": 0, "reason": "诊断置信度不足（0.45 < 0.9），跳过自动修复"},
  "evolution": {"evolved": 0, "drafted": 0, "patterns_detected": 0},
  "elapsed_ms": 120
}
```

### 2.3 诊断解读

```bash
curl GET /system/diagnose
```

**关键字段**：
- `overall_health`: `healthy` / `warning` / `critical`
- `overall_confidence`: 诊断置信度（< 0.9 时不自动修复）
- `findings[].severity`: `error`（需立即处理）/ `warning`（需关注）/ `info`（仅供参考）
- `findings[].insufficient_data`: `true` 表示数据不足（不是问题）
- `correlated`: 跨子系统关联分析（如"SECI 停滞 + 收敛失效 → 知识管道阻塞"）

**示例**（系统刚上线时）：
```json
{
  "overall_health": "healthy",
  "overall_confidence": 0.0,
  "findings": [
    {"rule": "seci_stagnation", "severity": "info",
     "finding": "数据不足，无法诊断（需积累≥2周健康快照）",
     "insufficient_data": true}
  ]
}
```

这是正常的——不是 bug。

### 2.4 手动修复

```bash
curl -X POST /system/heal
```

**何时用**：诊断发现了可修复的 warning/error，但你不想等自动修复。

**安全门**：`confidence < 0.9` 时跳过修复并返回原因——不会在不确定时乱修。

### 2.5 演化

```bash
curl GET /system/evolve
```

**何时用**：想看看系统从运行数据中发现了什么新模式。

**返回解读**：
- `evolved`: 自动发布的数量（术语定义）
- `drafted`: 需要人工审批的数量（方案原型）
- `patterns_detected`: 检测到的模式数
- `results[].action`: `published`（已自动发布）/ `draft`（待审批）

**示例**（系统积累足够数据后）：
```json
{
  "evolved": 2,
  "drafted": 1,
  "results": [
    {"pattern": "term:围标串标", "type": "term", "action": "published", "score": 0.85},
    {"pattern": "term:关联图谱构建", "type": "term", "action": "published", "score": 0.92},
    {"pattern": "solution:cross-domain-pattern", "type": "archetype", "action": "draft"}
  ]
}
```

---

## 3. 故障排查流程

### 3.1 系统整体异常

```
症状：dashboard 显示 pipeline_health = error 或 degraded
排查：
  1. curl GET /fde/pipeline-status          → 看哪一层注入失败
  2. curl GET /fde/health                   → 看哪个组件异常
  3. curl GET /system/diagnose              → 看根因分析
  4. curl -X POST /system/heal              → 尝试自动修复
```

### 3.2 诊断报告质量下降

```
症状：ontology-coverage 持续下降
排查：
  1. curl GET /fde/sessions/{id}/ontology-coverage  → 量化证据覆盖率
  2. curl GET /fde/sessions/{id}/improve             → 获取改进建议
  3. 按建议执行：补充术语定义 / 扩展本体类 / 增加历史案例
```

### 3.3 技能执行异常

```
症状：某个 Skill 执行成功率持续 < 50%
排查：
  1. curl GET /system/diagnose              → 看 skill_degradation 规则
  2. curl -X POST /system/heal              → 自动下调该 Skill 权重
```

### 3.4 知识沉淀断层

```
症状：atom_count 增长但 delivery_rate 下降
含义：系统在产出知识，但诊断结果没有转化为交付行动
排查：
  1. 检查客户的交付反馈是否及时录入
  2. curl GET /fde/alerts?min_severity=warning   → 看是否有阻塞行动
  3. 手动推进被阻塞的交付行动
```

---

## 4. 术语字典管理

### 4.1 查看当前术语

```bash
# 通过诊断注入查看（术语表自动渲染）
curl GET /fde/pipeline-status | jq .data_availability
```

### 4.2 手动补充术语定义

当系统自动播种了术语桩但定义为空时：

```bash
# 查看哪些术语缺少定义
curl GET /fde/sessions/{id}/improve

# 手动编辑 Term 实体
# 编辑 enterprise-terms GraphIndex 对应条目
```

### 4.3 跨域术语管理

系统会自动检测同名概念在不同域中出现，并创建 `similar_to` 关联。不需要手动操作。
