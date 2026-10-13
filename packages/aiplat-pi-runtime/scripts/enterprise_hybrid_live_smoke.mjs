#!/usr/bin/env node
/**
 * Live hybrid E2E against local management GW / platform / core (when up).
 *
 * Default: auto-pick AIPLAT_PLATFORM_URL among:
 *   env → http://127.0.0.1:8003 (direct /platform/*) → http://127.0.0.1:8000/api (GW)
 * Core: AIPLAT_CORE_URL or http://127.0.0.1:8002/api/core
 * SKIP (exit 0) if platform or core down.
 * Require: AIPLAT_HYBRID_LIVE=1 → fail if unreachable.
 *
 * Note: platform(:8003) mounts /platform/*; GW(:8000) mounts /api/platform/*.
 * Never use http://host:8003/api (404). Runtime normalizePlatformBaseUrl strips that footgun.
 *
 * Env:
 *   AIPLAT_TENANT_TOKEN / AIPLAT_API_KEY (optional; local may be auth-off → "dev")
 */
const TOKEN = (
  process.env.AIPLAT_TENANT_TOKEN ||
  process.env.AIPLAT_API_KEY ||
  "dev"
).trim();
const REQUIRE = ["1", "true", "yes", "on"].includes(
  (process.env.AIPLAT_HYBRID_LIVE || "").trim().toLowerCase(),
);

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

async function fetchJson(url, init = {}) {
  const res = await fetch(url, {
    ...init,
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${TOKEN}`,
      ...(init.headers || {}),
    },
  });
  const text = await res.text();
  let parsed = text;
  try {
    parsed = JSON.parse(text);
  } catch {
    /* keep */
  }
  return { status: res.status, ok: res.ok, text, parsed };
}

async function healthyOrigin(origin) {
  const o = String(origin || "").trim().replace(/\/+$/, "");
  if (!o) return false;
  try {
    const r = await fetch(`${o}/health`, { signal: AbortSignal.timeout(2000) });
    return r.ok;
  } catch {
    return false;
  }
}

/** Strip /api or /api/core to host origin for /health. */
function toOrigin(base) {
  let b = String(base || "").trim().replace(/\/+$/, "");
  b = b.replace(/\/api\/core$/i, "").replace(/\/api$/i, "");
  return b;
}

/** Strip mistaken :8003/api (same as runtime normalizePlatformBaseUrl). */
function normalizePlatformBaseUrl(raw) {
  const b = String(raw || "").trim().replace(/\/+$/, "");
  if (!b) return "";
  try {
    const u = new URL(b);
    const path = (u.pathname || "/").replace(/\/+$/, "") || "/";
    if (u.port === "8003" && (path === "/api" || path.startsWith("/api/"))) {
      if (path === "/api") u.pathname = "/";
      else if (path.startsWith("/api/platform")) u.pathname = path.slice("/api".length) || "/";
      else u.pathname = path.slice("/api".length) || "/";
      return u.toString().replace(/\/+$/, "");
    }
    if (u.port === "8000" && path === "/") {
      u.pathname = "/api";
      return u.toString().replace(/\/+$/, "");
    }
  } catch {
    /* keep */
  }
  return b;
}

/**
 * Prefer direct platform (:8003 → /platform/*), then management GW (:8000/api).
 */
async function resolvePlatformBase() {
  const fromEnv = normalizePlatformBaseUrl(process.env.AIPLAT_PLATFORM_URL || "");
  const candidates = [
    fromEnv,
    "http://127.0.0.1:8003",
    "http://127.0.0.1:8000/api",
  ].filter(Boolean);

  const tried = new Set();
  for (const c0 of candidates) {
    const c = normalizePlatformBaseUrl(c0);
    if (!c || tried.has(c)) continue;
    tried.add(c);
    const origin = toOrigin(c);
    if (!(await healthyOrigin(origin))) continue;
    const probeUrl = c.endsWith("/platform")
      ? `${c}/memory/capture`
      : `${c}/platform/memory/capture`;
    try {
      const r = await fetch(probeUrl, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          authorization: `Bearer ${TOKEN}`,
        },
        body: JSON.stringify({ prompt: "probe", result: "probe" }),
        signal: AbortSignal.timeout(3000),
      });
      if (r.status === 404) continue;
      return c;
    } catch {
      continue;
    }
  }
  for (const c0 of candidates) {
    const c = normalizePlatformBaseUrl(c0);
    if (c && (await healthyOrigin(toOrigin(c)))) return c;
  }
  return fromEnv || "http://127.0.0.1:8003";
}

function platformPath(platformBase, suffix) {
  const b = String(platformBase || "").trim().replace(/\/+$/, "");
  if (b.endsWith("/platform")) return `${b}${suffix}`;
  return `${b}/platform${suffix}`;
}

async function main() {
  const PLATFORM = await resolvePlatformBase();
  const CORE = (
    process.env.AIPLAT_CORE_URL || "http://127.0.0.1:8002/api/core"
  )
    .trim()
    .replace(/\/+$/, "");

  const platUp = await healthyOrigin(toOrigin(PLATFORM));
  const coreUp = await healthyOrigin(toOrigin(CORE));

  if (!platUp || !coreUp) {
    const msg = `SKIP: hybrid live (platform_up=${platUp} core_up=${coreUp} platform=${PLATFORM})`;
    if (REQUIRE) throw new Error(msg.replace("SKIP:", "FAIL:"));
    console.log(msg);
    console.log("AIPLAT_HYBRID_LIVE_SMOKE_SKIP");
    return;
  }
  console.log(`LIVE: platform=${PLATFORM} core=${CORE}`);

  // 1) Memory capture (ladder 4)
  const mem = await fetchJson(platformPath(PLATFORM, "/memory/capture"), {
    method: "POST",
    body: JSON.stringify({
      prompt: "hybrid_live_smoke",
      result: "AIPLAT_HYBRID_LIVE_MEMORY_OK",
      source: "pi_runtime",
      tags: ["pi_runtime", "hybrid_live_smoke"],
      success: true,
    }),
  });
  assert(mem.status === 200, `memory/capture http ${mem.status}: ${mem.text.slice(0, 200)}`);
  const memOk =
    mem.parsed &&
    typeof mem.parsed === "object" &&
    (mem.parsed.ok === true || mem.parsed.status === "ok");
  assert(memOk, `memory capture not ok: ${mem.text.slice(0, 300)}`);
  console.log("PASS: live memory/capture");

  // 2) Tool execute calculator (ladder 2)
  const toolUrl = `${CORE}/tools/calculator/execute`;
  const tool = await fetchJson(toolUrl, {
    method: "POST",
    body: JSON.stringify({ expression: "1+1", user_id: "pi-hybrid-live" }),
  });
  assert(tool.status === 200, `tool execute http ${tool.status}`);
  const out =
    tool.parsed && typeof tool.parsed === "object"
      ? String(tool.parsed.output ?? "")
      : "";
  assert(
    out.includes("2") || tool.parsed?.ok === true,
    `calculator unexpected: ${tool.text.slice(0, 300)}`,
  );
  console.log("PASS: live tools/calculator/execute");

  // 3) KB query (ladder 1) — soft path: HTTP reachable; body may be skill-failed
  const kb = await fetchJson(platformPath(PLATFORM, "/kb/query"), {
    method: "POST",
    body: JSON.stringify({
      question: "hybrid live smoke",
      collection_id: "default",
      limit: 3,
    }),
  });
  assert(kb.status === 200 || kb.status === 503, `kb/query http ${kb.status}`);
  console.log(`PASS: live kb/query reachable (http=${kb.status})`);

  // 4) Approvals pending (ladder 5)
  // Platform process may return 503 (ApprovalManager not init); core often has the list.
  let ap = await fetchJson(platformPath(PLATFORM, "/approvals/pending"));
  let viaCore = false;
  if (ap.status === 503 || ap.status === 404) {
    const coreAp = await fetchJson(`${CORE}/approvals/pending`);
    if (coreAp.status === 200) {
      viaCore = true;
      ap = coreAp;
    }
  }
  assert(
    ap.status === 200 || ap.status === 503,
    `approvals/pending unexpected http ${ap.status}: ${ap.text.slice(0, 200)}`,
  );
  if (ap.status === 200 && viaCore) {
    console.log("PASS: live approvals/pending via core fallback");
  } else if (ap.status === 200) {
    console.log("PASS: live approvals/pending");
  } else {
    console.log("PASS: live approvals/pending soft (ApprovalManager not initialized)");
  }

  // 5) Native gate policy still offline-true
  const { spawnSync } = await import("node:child_process");
  const { fileURLToPath } = await import("node:url");
  const { resolve, dirname } = await import("node:path");
  const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
  const gate = spawnSync(
    process.execPath,
    ["packages/aiplat-pi-runtime/scripts/enterprise_tool_gate_smoke.mjs"],
    { cwd: repoRoot, encoding: "utf8" },
  );
  assert(gate.status === 0, `tool_gate smoke failed: ${gate.stderr || gate.stdout}`);
  console.log("PASS: native tool gate offline policy still green");

  console.log("AIPLAT_HYBRID_LIVE_SMOKE_OK");
}

main().catch((e) => {
  console.error("FAIL:", e && e.message ? e.message : e);
  process.exit(1);
});
