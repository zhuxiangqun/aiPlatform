# ADR-DRAFT — 本体 → D1（图服务独立）

> **状态**：Draft · **非 Accepted** · P0 W2  
> **当前允许**：D1c only  
> **注意**：抽取难度最高；放路线图后段

## 动机

GraphIndex / DomainRouter 与控制面共进程导致发布耦合与存储纠缠。

## 非目标

- 不在 D1 前重写全部 ontology YAML 生态
- 不把 Knowledge 三分（语义/检索/证据）揉进单服务

## D1c → D1 门槛

1. 图读写 API 契约 + schema 边界（ADR-03 data owner 对齐）  
2. 独立存储迁移路径（含回填）  
3. 编辑器经 API；core 只留客户端  
4. 双写/回滚演练  
5. 联签 Accepted  

## 回滚

停图服务；读路径切回 core 内嵌 GraphIndex。
