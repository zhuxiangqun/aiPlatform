# aiPlatform 知识库本体系统 — 架构总览

> 版本: v2.1 | 更新: 2026-06-15

## 系统架构图

```mermaid
flowchart TB
    subgraph Input[入口层]
        UQ["用户问题"]
        PD["PDF/DOC 入库"]
    end

    subgraph Mapping["检索层 (查询增强)"]
        QM["Ontology Query Mapper"]
        QM --> |"T-Box 类/属性解析"| TBox
        QM --> |"A-Box 实例匹配"| ABox
        UQ --> QM
        QM --> RAG["RAG 检索"]
        RAG --> FTS5["FTS5 全文"]
        RAG --> VEC["向量检索"]
        RAG --> RER["重排器"]
    end

    subgraph Ontology["本体核心"]
        TBox["T-Box\n类/属性/公理"]
        ABox["A-Box\nSPO 三元组实例"]
        TBox <--> ABox
    end

    subgraph Pipeline["执行层"]
        direction TB
        PIP["Pipeline 引擎"]
        PIP --> |"执行前: check_stage_ontology_guard"| G1{{"⚡ Markings + RBAC"}}
        PIP --> ACT["OntologyAction + 状态机"]
        ACT --> |"执行后: _verify_stage_output"| G2{{"⚡ 预期校验 + 回放"}}
        ACT --> |"写回"| WB["外部系统 WriteBack"]
    end

    subgraph Governance["治理钩子"]
        G1 -.-> MARK["血缘传播 Markings"]
        G2 -.-> VER["验证 + 回放\n(replay_versioning)"]
        G2 -.-> FLS["字段级脱敏"]
    end

    subgraph Evolution["增长与演化层"]
        GAP["知识盲区检测"]
        EVO["LLM 演化建议"]
        GRO["知识复利指标"]
        GAP --> |"检测缺口"| TBox
        EVO --> |"建议修改"| TBox
        GRO --> |"指标追踪"| ABox
        TBox --> |"更新索引\n(inference_cache 失效)"| FTS5
        ABox --> |"更新索引\n(inference_cache 失效)"| VEC
    end

    subgraph Learning["AI 学习教练"]
        LP["学习路径"]
        CH["章节+习题"]
        AS["评估引擎"]
        PR["进度+雷达图"]
        LP --> |"读取结构"| TBox
        CH --> |"写入掌握度"| ABox
        AS --> |"读取前置依赖"| TBox
        PR --> |"查询进度"| ABox
    end

    subgraph Frontend["展示层"]
        OBS["Obsidian Vault"]
        API["REST API"]
    end

    PD --> |"文档解析"| ABox
    PIP --> |"知识原子抽取"| ABox
    ACT --> |"固化知识"| ABox
    WB --> API
    VER --> |"tbox_hash 校验"| TBox
    OBS --> |".md 文件"| ABox
```

## 层次职责

| 层次 | 职责 | 核心模块 |
|------|------|------|
| **入口层** | 用户输入、文档入库 | — |
| **检索层** | 本体查询映射 → 多路检索 → 重排 | `ontology_query_mapper.py`, `hybrid_retriever.py`, `wiki_context.py` |
| **本体核心** | T-Box 类/属性/公理, A-Box SPO 三元组 | `knowledge_ontology.py`, `knowledge_abox_builder.py`, `wiki_engine.py` |
| **执行层** | Pipeline 编排, Action 执行, 写回 | `pipeline_engine.py`, `knowledge_action.py`, `knowledge_writeback.py` |
| **治理钩子** | 安全过滤、验证、脱敏（纵向注入） | `policy_gate.py`, `verification.py`, `field_level_security.py` |
| **增长与演化** | 盲区检测、LLM 建议、增长指标 | `knowledge_quality.py`, `knowledge_growth.py`, `knowledge_evolution_llm.py` |
| **AI 学习教练** | 三条内置路径、评估引擎、双向本体连接 | `learning_ontology.py`, `learning_paths.py`, `learning_assessment.py` |
| **展示层** | Obsidian Vault, REST API | — |

## 关键闭环

| 闭环 | 路径 | 状态 |
|------|------|:---:|
| **入库→检索** | PDF → chunk → embed → FTS5/Vector | ✅ |
| **检索→盲区** | query → match → gap_detection → prompt | ✅ |
| **执行→本体** | Pipeline → OntologyAction → A-Box | ✅ (Phase 1) |
| **本体→安全** | A-Box → Markings propagation → access_check | ✅ (Phase 2) |
| **演化→索引** | write_page → invalidate cache → reindex | ✅ (修正 2) |
| **教练→本体** | complete_chapter → mastery triples → A-Box | ✅ (修正 3) |
| **回放→版本** | tbox_hash → stale_check → skip_or_compare | ✅ (修正 4) |
| **查询→映射** | question → T-Box match → rewritten_query | ✅ (修正 1) |

## 已知待观察项

| 项 | 说明 |
|------|------|
| KB 路径安全入口不一致 | `sys_knowledge_retrieve` 未透传 `actor_scopes` 到 KB 子路径，详见 Issue #TBD |
| Wiki/KB 分数未归一化 | 余弦相似度与 RRF+BM25 混排，不同量纲直接比较 |
