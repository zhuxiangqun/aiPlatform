# ADR-09 决定 — compose 长驻（可选运维 profile）

- **状态**：**Accepted（窄）** · 2026-10-27  
- **批准句**：批准 ADR-09：**compose 长驻**。接受兼任并承担全拆后果。范围：仅该项。compose 长驻：**含**。不含超边界 E4 承诺。  
- **填空理由**：五产品单产品边界均已收口；批句点名长驻且填 **含**  
- **不含**：超边界 E4；默示改 Identity 双重权威；一次强制全环境改生产默认长驻；本决定 PR 大搬仓

## 授权 / 禁止

| 项 | |
|----|--|
| ✅ | 为已批单产品提供**正式可选** compose 长驻 profile（显式 `up -d` / 文档化停机） |
| ✅ | 回滚默认：`docker compose … down -v`；切回 one-shot / 主机脚本路径 |
| ❌ | 超边界 E4 承诺 |
| ❌ | 强制把所有环境的生产默认从 one-shot 改为长驻（须分环境另决） |
| ❌ | 借机拆第二 Identity / PolicyGate 或改 ADR-02 |

## 与既有 compose 关系

| 既有 | 关系 |
|------|------|
| `compose.adr10-diagnosis-mvp.yml`（`run --rm`） | one-shot 保留；长驻为**另文件/另 profile**，不覆盖 |
| `compose.gate3-pi-thin.yml` / `compose.pi-thin-optional.yml` | 试点/可选仍有效；长驻升格须 BOUNDARY 分 PR |
| FDE / 本体 / 控制面 | 仅健康探针 one-shot 已有；长驻 compose 另立 |

## 后续（另 PR）

1. compose 长驻边界清单（哪些产品 profile / 端口 / 数据卷 / 回滚）  
2. 分 PR 落地（BOUNDARY 序 A→B→C）；禁止一次全仓写满五套长驻  

## 签署

架构 × 业务（兼任）· 2026-10-27 · **仅 compose 长驻；≠ 强制生产默认；≠ E4**
