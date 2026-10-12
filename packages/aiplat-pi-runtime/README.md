# @aiplat/pi-runtime

Thin **Pi Package** Runtime for aiPlat factory **Agent-mode** artifacts.

- **aiPlat** = heavy factory (PRD → AGENT.md / SKILL.md / `agent_manifest.json`)
- **This package** = user-side Runtime (Pi extensions + package `skills/`)

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
# POST /v1/chat            Authorization: Bearer dev
# POST /v1/skills/demo_skill   → handler.py if present

bash scripts/http_smoke.sh
```

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

See [PHASE0.md](./PHASE0.md) and `docs/architecture/plans/pi-thin-runtime.md`.
