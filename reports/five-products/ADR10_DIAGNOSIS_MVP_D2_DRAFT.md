# ADR-10 D2 草案 — 平台默认绑定（第 2 步剩余）

- **状态**：**已升格 Accepted** · 2026-10-26 — 见 `ADR10_DIAGNOSIS_MVP_D2_DECISION.md`；落地 PR [#434](https://github.com/zhuxiangqun/aiPlatform/pull/434) → `968f3a7`  
- **入口**：`POST /api/platform/apps/fde/acceptance/signoff` → `validate_slice_signoff_reports`  
- **回滚**：`AIPLAT_DIAGNOSIS_PROD_DEFAULT=0`  
- **仍禁止**：对外 E4；ADR-09 Accepted / 全拆；compose 长驻 profile（本批未含）

获批前检查表与批准句模板已归档于 git 历史；本文件仅保留升格指针，避免与 DECISION 双源。
