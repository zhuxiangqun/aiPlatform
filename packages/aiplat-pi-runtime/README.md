# @aiplat/pi-runtime

Thin **Pi Package** Runtime for aiPlat factory **Agent-mode** artifacts.

- **aiPlat** = heavy factory (PRD → AGENT.md / SKILL.md / `agent_manifest.json`)
- **This package** = **厂外** user-side thin host (Pi extensions + package `skills/`)

## Two axes (do not merge)

See [`docs/architecture/plans/pi-thin-runtime.md`](../../docs/architecture/plans/pi-thin-runtime.md).

| Axis | Role of Pi | Status |
|------|------------|--------|
| **(B) Factory-out** | User-side host for artifacts | **Shipped** — this package |
| **(A) Factory-in** | Optional coding exec kernel behind PolicyGate | **Merge-closed** (`blank_not_proven`) — Execute bypass removed; offline probes only |

**Product decision (locked)**

| Mode | Meaning |
|------|---------|
| **Pi-only** (default) | Artifacts run with Pi alone: SOP + skills + handler + your LLM. No 8002/8003. |
| **Pi + aiPlat** (enterprise) | Same Pi shell; opt-in hybrid (`AIPLAT_ENTERPRISE=1`). **KB** + **allowlisted tools** + **native tool gate** + **Memory capture** + **Approval wait** (`AIPLAT_ENTERPRISE_APPROVAL=1` → status/pending/wait + Unattended Inbox via `AIPLAT_ENTERPRISE_ATTENDANCE`; humans approve in platform UI). |
| Thick aiPlat-only on user machine | **Not** the default delivery shape. |

**Layered, not two parallel products:** aiPlat already has agent loops / tools / multi-model in the **platform** sense. Pi exists so **factory artifacts can run without installing the full stack**. Overlap in capability lists ≠ redundant delivery. Do not market Pi and aiPlat as two peer platforms with separate auth/audit. Enterprise entry remains aiPlat (or Pi shell reconnecting to aiPlat).

Do not claim Pi-only equals full in-factory agent. Enterprise thickness is **Pi + aiPlat**, not “stuff the platform into the Pi process”.

## Enterprise hybrid (opt-in)

Default remains Pi-only. See [`docs/HYBRID_ENTERPRISE.md`](./docs/HYBRID_ENTERPRISE.md) and delivery appendix [`docs/HYBRID_ENTERPRISE_DELIVERY.md`](./docs/HYBRID_ENTERPRISE_DELIVERY.md) (SKU + KB citation acceptance).

```bash
export AIPLAT_ENTERPRISE=1
export AIPLAT_PLATFORM_URL=http://127.0.0.1:8003      # or :8000/api GW; NOT :8003/api
export AIPLAT_TENANT_TOKEN=<bearer>                # or AIPLAT_API_KEY
# optional KB: AIPLAT_KB_COLLECTION_ID=default
# optional tools (empty = tools off, KB only):
export AIPLAT_ENTERPRISE_TOOLS=calculator
# optional: AIPLAT_CORE_URL=http://127.0.0.1:8002
# native gate ON by default under ENTERPRISE=1 (bash/write/edit blocked)
# escape: AIPLAT_ENTERPRISE_ALLOW_NATIVE=1  or  AIPLAT_ENTERPRISE_TOOL_GATE=0
# optional memory writeback:
# export AIPLAT_ENTERPRISE_MEMORY=1
# optional approval wait (no approve from Pi):
# export AIPLAT_ENTERPRISE_APPROVAL=1
# export AIPLAT_ENTERPRISE_ATTENDANCE=inbox   # attended|inbox|auto
# export AIPLAT_ENTERPRISE_SESSION_ID=my-pi-session

pi -e .
# /aiplat-status          → enterprise_hybrid / tools / tool_gate / memory / approval
# /aiplat-enterprise      → KB reconnect status
# /aiplat-memory          → memory writeback status
# /aiplat-approval        → approval wait-bridge status
# tools: aiplat_kb_retrieve | aiplat_tool_execute | aiplat_memory_capture
#        | aiplat_approval_status | aiplat_approval_pending | aiplat_approval_wait
#        | aiplat_unattended_inbox | aiplat_unattended_wait
```

Offline gates (mock HTTP / pure policy, no platform process):

```bash
node packages/aiplat-pi-runtime/scripts/enterprise_kb_smoke.mjs
node --experimental-strip-types packages/aiplat-pi-runtime/scripts/enterprise_kb_citation_smoke.mjs
node packages/aiplat-pi-runtime/scripts/enterprise_delivery_scan_smoke.mjs
node packages/aiplat-pi-runtime/scripts/enterprise_kb_health_smoke.mjs
node packages/aiplat-pi-runtime/scripts/enterprise_tools_smoke.mjs
node packages/aiplat-pi-runtime/scripts/enterprise_tool_gate_smoke.mjs
node packages/aiplat-pi-runtime/scripts/enterprise_memory_smoke.mjs
node packages/aiplat-pi-runtime/scripts/enterprise_approval_smoke.mjs
```

PolicyGate / RBAC stay on the server; extensions only forward the bearer token. The native gate **blocks** host-mutating Pi tools so they cannot bypass that server path.

## Scheme A (Skills)

Skills are **copied into** the package `skills/` directory at export time. Pi auto-discovers them. There is **no** `registerSkill` API.

## Quick start

```bash
# Install Pi (Node >= 22.19)
npm install -g --ignore-scripts @earendil-works/pi-coding-agent

# Smoke this package
cd packages/aiplat-pi-runtime
pi -e .
# /aiplat-status
# /skill:fixture-skill
# /aiplat-sop-check
```

With an exported app:

```bash
export AIPLAT_APP_HOME=/path/to/exported-app   # contains agent_manifest.json
pi -e /path/to/aiplat-pi-runtime
# or: aiplat-run
```

Export from aiPlat disk deploy:

```bash
python3 scripts/export_pi_bundle.py --app-home ~/.aiplat/apps/<project_id>/current --out dist/aiplat-app-<id>
pi install ./dist/aiplat-app-<id>
```

## Thin HTTP (Phase 2)

```bash
AIPLAT_HTTP_STUB=1 AIPLAT_APP_HOME=./fixtures/sample-app \
  AIPLAT_HTTP_API_KEY=dev node bin/aiplat-http.mjs
# GET  /health
# GET  /healthz            # D1 contract: status/version/product_id
# POST /v1/chat            Authorization: Bearer dev
# POST /v1/skills/demo_skill   → handler.py if present

bash scripts/http_smoke.sh
```

## D1 install (edge prefix)

```bash
export AIPLAT_HOME=/tmp/aiplat-pi-d1   # optional isolate
bash scripts/d1_install.sh --smoke
# docs: docs/INSTALL.md — upgrade / rollback / backup reuse Gate3 Thin
```

## Pi Thin independent process (optional · ADR-09)

**Status**: Gate3 pilot remains the operational path; ADR-09 accepted **Pi Thin** as a single-product optional deploy (`reports/five-products/ADR09_NEXT_PI_THIN_DECISION.md`). Boundary: `ADR09_PI_THIN_BOUNDARY.md`.

- **Optional** process separation from the aiPlat control plane — **not** a forced production default.
- Independent env (`AIPLAT_ENTERPRISE` must stay `0`). Do **not** reuse control-plane secret files.
- Compose: one-shot (`compose.pi-thin-optional.yml`) **or** optional long-running (`compose.pi-thin-long-running.yml`) — **not** forced production default.

```bash
cd packages/aiplat-pi-runtime
# ADR-09 names (aliases) — same behavior as Gate3 pilot paths:
cp scripts/pi_thin_optional.env.example .env.gate3-pi-thin   # or gate3_pi_thin.env.example
bash scripts/pi_thin_optional_pilot.sh                       # alias → gate3_pi_thin_pilot.sh
# optional one-shot container:
#   docker compose -f compose.pi-thin-optional.yml up        # include → compose.gate3-pi-thin.yml
#   docker compose -f compose.pi-thin-optional.yml down -v
# optional long-running (ADR-09 compose 长驻 · BOUNDARY B/C):
#   docker compose -f compose.pi-thin-long-running.yml up -d
#   docker compose -f compose.pi-thin-long-running.yml down -v
#   # or: bash ../../scripts/adr09_compose_pi_thin_long_running_smoke.sh
# Rollback (Bundle-first): reports/five-products/GATE3_PI_THIN_ROLLBACK_DRILL.md
```

| ADR-09 name | Gate3 canonical (unchanged) |
|-------------|------------------------------|
| `pi_thin_optional_pilot.sh` | `gate3_pi_thin_pilot.sh` |
| `pi_thin_optional.env.example` | `gate3_pi_thin.env.example` |
| `compose.pi-thin-optional.yml` | `compose.gate3-pi-thin.yml` |
| `compose.pi-thin-long-running.yml` | `compose.gate3-pi-thin.yml` + `restart: unless-stopped` |

Historical Gate3 pilot spec: `reports/five-products/GATE3_PI_THIN_PILOT.md`.


Agent mode (OpenAI-compatible — Ollama default):

```bash
# ensures ~/.pi/agent/models.json has ollama provider (for CLI)
bash scripts/ensure_ollama_models_json.sh

AIPLAT_PI_MODEL=ollama/qwen2.5:3b AIPLAT_APP_HOME=./fixtures/sample-app \
  AIPLAT_HTTP_API_KEY=dev node bin/aiplat-http.mjs
# Optional: AIPLAT_PI_BASE_URL / AIPLAT_PI_API_KEY / AIPLAT_PI_SDK_ROOT

# Full live gate (offline + stub HTTP + CLI + HTTP agent)
AIPLAT_PI_MODEL=ollama/qwen2.5:3b bash scripts/live_smoke.sh
```

## Factory-in (merge-closed — offline archive only)

Way-4 Execute bypass was **removed** (`blank_not_proven`). Optional offline CLI remains for probes only; it does **not** replace ReActLoop / PipelineEngine and is **not** on the Workspace Execute path.

```bash
python3 scripts/test_coding_exec_unit.py
bash scripts/coding_exec_smoke.sh
python3 scripts/factory_in_evidence_smoke.py
```

See [docs/FACTORY_IN_EXPERIMENT.md](./docs/FACTORY_IN_EXPERIMENT.md) §⓪.

## Phase 0 验证记录（归档入口）

阶段门禁与结果已收敛为历史记录，日常以本文 Quick start / Live smoke 为准：

- [PHASE0.md](./PHASE0.md) — 阶段检查项  
- [PHASE0_RESULTS.md](./PHASE0_RESULTS.md) — 结果摘录  

战略边界见 [`docs/architecture/plans/pi-thin-runtime.md`](../../docs/architecture/plans/pi-thin-runtime.md)。
