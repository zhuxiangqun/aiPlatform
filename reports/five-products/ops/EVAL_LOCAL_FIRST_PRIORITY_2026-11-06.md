# EVAL 优先级 — 先本地做完、测完（2026-11-06）

- **产品确认**：当前**不对外发布**；须先在本机把评测系统本身做完并测通，再另议公网/生产。
- **A1**：以[本地签认](./EVAL_A1_DEPLOY_SIGNOFF_local_20261105.md)为准（[范围决策](./EVAL_A1_SCOPE_DECISION_LOCAL_SUFFICIENT_2026-11-06.md)）。
- **禁止**：用「缺正式 BASE / 缺 staging」卡住本地评测能力、门禁或 UI 联调收口。

## 优先级（强制）

| 序 | 目标 | 是否本阶段必须 |
|---:|---|---|
| 1 | 本机 Eval Center + package runners/gates 可跑、可复现 | **是** |
| 2 | 本地轨 closeout（含 P2 context/memory/self_learn）绿 | **是** |
| 3 | 人侧已做证据（G2b scoped / Arena pilot / calibration）留档 | **是（已做）** |
| 4 | 正式 BASE / CDN / 对外发布 A1 | **否（延后）** |
| 5 | P2-4 生产治理 / process_split | **否（Parked）** |

## 本机 E2E（2026-11-06）

- `start.sh` 默认 `AIPLAT_EVAL_LOCAL_PROXY=1` → `:8010` + worker + `AIPLAT_EVAL_SERVICE_URL`（与 mineru 冲突时用 `AIPLAT_EVAL_PORT=8011`）
- Center tabs：Session / Arena / Skill / P2 Research；Job 平面需 **mode=proxy**（总览 `upstream=proxy`）。若仍是 `cohost`：先 `bash packages/aiplat-evaluation/scripts/local_proxy_up.sh`，再**重启 platform** 并导出 `AIPLAT_EVAL_SERVICE_URL=http://127.0.0.1:8010`（env 不会热更新）
- `local_proxy_up` 用工作区 `.venv`；缺 `PyJWT` 时 API 起不来 → UI 停在 cohost（`pip install 'PyJWT>=2.8'`）
- 关停：`stop.sh` 或 `packages/aiplat-evaluation/scripts/local_proxy_down.sh`
- 日常门：`bash packages/aiplat-evaluation/scripts/local_track_closeout.sh`
- **Live LLM smoke（本机 Ollama）**：`AIPLAT_EVAL_LLM_LIVE=1` + `qwen2.5:3b` → gate ok · `llm_ok_n=30` · evidence `docs/a3/drills/local-eval-live-llm-20261106T012344Z.json`（仍 `accuracy_claim=false`）
- **Skill fixture**：`start.sh` 在 Docker Desktop 可用时默认 `AIPLAT_EVAL_SANDBOX_BACKEND=docker`（否则 `local_stub`，Skill 仍 `sandbox_required`）。镜像 `alpine:3.20`；本机已验 enqueue→`succeeded`（`tools_executed=false`，非真实 skill 工具）。强制 stub：`AIPLAT_EVAL_SANDBOX_BACKEND=local_stub`

## 诚实锁

本地完备 ≠ 对外已发布 ≠ accuracy 认证 ≠ process_split。  
FDE **可以用本机评本机**；生产宣称另开轨道。
