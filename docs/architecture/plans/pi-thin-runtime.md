# Plan: aiPlat × Pi 薄 Runtime（1C + 2C）

> Living 摘要 · 2026-10-12 · 包：`packages/aiplat-pi-runtime/`  
> **状态**：Phase 0–2 + 工厂/FE/ZIP **已合并 main**（PR [#251](https://github.com/zhuxiangqun/aiPlatform/pull/251)）  
> **Live 门**：✅ `bash packages/aiplat-pi-runtime/scripts/live_smoke.sh`（Ollama `ollama/qwen2.5:3b` — CLI print + SOP + `/aiplat-status` + HTTP `createAgentSession`）

## 结论（Phase 0）

| 假设 | 文档结论 | 离线检查 | 在线 LLM 冒烟 |
|------|----------|:--------:|:-------------:|
| 包内 `skills/` 自动发现 | **成立**（Pi Skills / Packages 文档） | 结构 ✅ | ✅ live_smoke |
| `before_agent_start` 注入 systemPrompt | **成立**（可返回 `systemPrompt` / `forceSystemPrompt`） | 代码含事件 ✅ | ✅ SOP marker |
| `registerCommand` / `registerTool` | **成立** | 代码含 API ✅ | ✅ `/aiplat-status` |
| `registerSkill` API | **不存在** → **方案 A**（导出复制 skills/） | N/A | N/A |

Skills 策略锁定 **方案 A**：`scripts/export_pi_bundle.py` 把工厂 skills 复制进导出包；扩展只注册斜杠命令与 SOP 注入。

## 职责

| | aiPlat | Pi Runtime |
|--|--------|------------|
| 工厂 / 合规 / 工作区编辑 | 是 | 否 |
| 用户侧对话执行 | 现状全栈 | **目标** |
| PolicyGate / Memory / SECI | 是 | **不搬** |

## 路径

1. `packages/aiplat-pi-runtime` — Pi Package（扩展 + fixture skills）
2. `scripts/export_pi_bundle.py` — 从 `~/.aiplat/apps/{id}/current` 导出
3. Phase 1b handler 协议：JSON stdin/stdout（见 `fixtures/handler_echo.py`）
4. Phase 2：薄 HTTP — `packages/aiplat-pi-runtime/bin/aiplat-http.mjs`
   - `GET /health` · `POST /v1/chat` · `POST /v1/skills/:name`
   - 有 `handler.py` 时走确定性桥（硬失败）；否则注入 SKILL.md 再对话
   - stub：`AIPLAT_HTTP_STUB=1`；真 Agent：`AIPLAT_PI_MODEL=provider/id` + `createAgentSession`
5. 工厂一键导出：`builder/pi_bundle_export.py`；`deploy-to-app` 响应 `pi_bundle`；`POST …/export-pi-bundle`；`GET …/export-pi-bundle.zip`；管理端「导出 / 下载 ZIP」

## 命令

```bash
python3 packages/aiplat-pi-runtime/scripts/phase0_offline_check.py
bash packages/aiplat-pi-runtime/scripts/http_smoke.sh
# Full live gate (Ollama default; needs :11434 + model pulled)
AIPLAT_PI_MODEL=ollama/qwen2.5:3b bash packages/aiplat-pi-runtime/scripts/live_smoke.sh

python3 scripts/export_pi_bundle.py \
  --app-home packages/aiplat-pi-runtime/fixtures/sample-app \
  --out dist/aiplat-app-sample
AIPLAT_APP_HOME=$PWD/dist/aiplat-app-sample \
  pi -e dist/aiplat-app-sample --model ollama/qwen2.5:3b
# /aiplat-status  /skill-greet  /skill-demo_skill  /aiplat-sop-check

# Real HTTP Agent (Ollama / OpenAI-compatible)
# AIPLAT_PI_MODEL=ollama/qwen2.5:3b AIPLAT_APP_HOME=dist/aiplat-app-sample \
#   node packages/aiplat-pi-runtime/bin/aiplat-http.mjs
# Cloud: set AIPLAT_PI_BASE_URL + AIPLAT_PI_API_KEY, or pi /login + provider/id
```

## handler 协议

```json
{"skill":"demo_skill","params":{}}
→ stdout {"ok":true,"result":{...}} exit 0
```

`fixtures/handler_runner.py <handler.py>` 包装现有 `async def execute(params)`。
