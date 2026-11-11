---
doc_type: Architecture
---

# External Agent Eval Contract — Pull Mode (Chat HTTP v1)

> **Status**: Implementable contract (v1 adds ordered tool-name trajectory).  
> **Slice**: Pull mode + conversational HTTP + optional tool-order matching.  
> **Orthogonal to**: named workspace (local partition) and remote Core profiles (which aiPlat host).

## 1. Terms

| Term | Meaning |
|---|---|
| external target | Registered HTTP endpoint evaluated by aiPlat; not a workspace Agent on disk |
| pull mode | aiPlat loads an exam paper and POSTs each task to the target; target returns text (+ optional trajectory) |
| `ext:{target_id}` | Synthetic agent_id used when persisting `eval_results` (avoids colliding with local agents) |
| named workspace | Still isolates local `agents/` + `eval_results/`; external target registry is per-workspace |
| trajectory (v1) | Ordered list of tool **names** only; params/side effects are not scored |

## 2. Storage

| Workspace | Targets file |
|---|---|
| `default` | `$AIPLAT_HOME/external_targets.yaml` |
| other local id | `$AIPLAT_HOME/workspaces/{id}/external_targets.yaml` |

Schema: `schema_version: 1`, `targets: [...]`. Atomic write + file lock (same style as workspace registry). Secrets are **not** stored in YAML; use `auth_secret_env` (env var name) only.

Fields: `target_id`, `label`, `kind: http_chat_pull`, `base_url`, `path`, `auth_header_name`, `auth_secret_env`, `timeout_ms`, `response_mode` (`aiplat_v0` \| `openai_chat` \| `plain_text`).

## 3. Protocol

### 3.1 Request (platform → external)

Platform may send `schema: aiplat.external_eval.chat_pull.v1` (v0 clients still accepted on the wire as the same body shape):

```json
{
  "schema": "aiplat.external_eval.chat_pull.v1",
  "task_id": "...",
  "user_input": "...",
  "metadata": { "set_id": "...", "agent_target_id": "..." }
}
```

### 3.2 Response (external → platform)

**v1 (preferred)**

```json
{
  "schema": "aiplat.external_eval.chat_pull.v1",
  "output_text": "...",
  "trajectory": {
    "tool_calls": [{"name": "lookup", "ok": true}]
  }
}
```

**v0 (compatible)** — `trajectory` null/absent; text-only scoring as before.

Rules:
- Always consume `output_text` (or openai / plain_text adapters).
- v1 trajectory: only ordered `tool_calls[].name` strings; ignore params; malformed trajectory → warn and treat as empty (default lenient).
- When the exam task declares `expected_tools`, match with `EvalMetricsEngine.compute_trajectory_quality` using **`IN_ORDER`**.
- Trajectory match ≠ tool-gold sufficiency ≠ side-effect verification. `accuracy_claim` and `sufficiency_claim` stay false.
- `gold.trajectory_scored=true` only when the paper has ≥1 `expected_tools` task **and** at least one parseable external tool sequence was returned.

## 4. SSRF / egress

- Only hosts registered on the target may be called (URL rebuilt from registered `base_url` + `path`).
- Method: POST only. Redirects forbidden. Body and timeout capped.
- Default: block private / loopback / link-local / metadata hosts (reuse `is_blocked_url` semantics).
- Dev escape: `AIPLAT_EXTERNAL_EVAL_ALLOW_PRIVATE=1` (audit-logged).

## 5. Exam API honesty

- `accuracy_claim=false`, `sufficiency_claim=false`.
- dry-run (`live=false`): validate target + paper; no scoring claim from remote execution.
- live: pull → lexical + optional IN_ORDER tool sequence → attributable report → persist under current named workspace `eval_results`.
- Writes require `X-Aiplat-Workspace-Id` (same as other eval writes).

## 6. UI copy (required)

- No trajectory scored: 「外部拉模式 · 仅对话文本结果；≠ 本机 live Agent；≠ 轨迹充分。」
- Trajectory scored: 「外部拉模式 · 对话文本 + 工具序（IN_ORDER）；≠ 副作用充分 / ≠ 准确率。」

## 7. Out of scope

- Push-mode result ingest API
- Trajectory params / side-effect / permission-bypass scoring
- Pretending external targets are local workspace Agents
- Arbitrary URL forwarding / open proxy
