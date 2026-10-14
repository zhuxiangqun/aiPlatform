#!/usr/bin/env node
/**
 * Hybrid enterprise tool-proxy smoke (no Pi / no core required).
 *
 * 1) Allowlist empty → tools off
 * 2) Mock core: POST /tools/{name}/execute
 * 3) L1/L2/L3 tier allowlist + L3 approval gate (mirrors enterprise_tools.ts)
 *
 * Tier logic is inlined (extensionless .ts imports + @earendil-works/* break
 * Node strip-types import of enterprise_tools.ts). Keep in sync with
 * resolveToolAllowlist / executeEnterpriseTool L3 gate in that file.
 */
import http from "node:http";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ENT = path.join(__dirname, "..", "extensions", "enterprise_tools.ts");

function envTruthy(name) {
  const v = (process.env[name] || "").trim().toLowerCase();
  return v === "1" || v === "true" || v === "yes" || v === "on";
}

function parseNameList(raw) {
  const s = String(raw || "").trim();
  if (!s) return [];
  return s
    .split(/[,;\s]+/)
    .map((x) => x.trim())
    .filter(Boolean);
}

function parseAllowlist() {
  return parseNameList(process.env.AIPLAT_ENTERPRISE_TOOLS || "");
}

/** Mirror of enterprise_tools.resolveToolAllowlist */
function resolveToolAllowlist() {
  const l1 = parseNameList(process.env.AIPLAT_ENTERPRISE_TOOLS_L1 || "");
  const l2 = parseNameList(process.env.AIPLAT_ENTERPRISE_TOOLS_L2 || "");
  const l3 = parseNameList(process.env.AIPLAT_ENTERPRISE_TOOLS_L3 || "");
  const flat = parseAllowlist();
  const ceilingRaw = (process.env.AIPLAT_ENTERPRISE_TOOL_CEILING || "L3")
    .trim()
    .toUpperCase();
  let ceiling = 3;
  if (ceilingRaw === "1" || ceilingRaw === "L1") ceiling = 1;
  else if (ceilingRaw === "2" || ceilingRaw === "L2") ceiling = 2;
  const tiered = l1.length + l2.length + l3.length > 0;
  const tiers = {};
  if (!tiered) {
    for (const n of flat) tiers[n] = 2;
    const allowlist = Object.keys(tiers).filter((n) => tiers[n] <= ceiling);
    return { allowlist, tiers, ceiling, tierMode: "flat" };
  }
  for (const n of l1) tiers[n] = 1;
  for (const n of l2) tiers[n] = 2;
  for (const n of l3) tiers[n] = 3;
  for (const n of flat) {
    if (!(n in tiers)) tiers[n] = 2;
  }
  const allowlist = Object.keys(tiers).filter((n) => tiers[n] <= ceiling);
  return { allowlist, tiers, ceiling, tierMode: "tiered" };
}

/** Mirror of executeEnterpriseTool L3 gate (no network). */
function l3GateError(toolName, cfg) {
  const name = String(toolName || "").trim();
  if (!cfg.allowlist.includes(name)) {
    const tier = cfg.tiers[name];
    if (tier && tier > cfg.ceiling) {
      return `tool_above_ceiling: ${name} is L${tier} but ceiling=L${cfg.ceiling}`;
    }
    return `tool_not_allowlisted: ${name}`;
  }
  const tier = cfg.tiers[name] ?? 2;
  if (tier >= 3 && !envTruthy("AIPLAT_ENTERPRISE_APPROVAL")) {
    return "l3_requires_approval: set AIPLAT_ENTERPRISE_APPROVAL=1 before L3 (write) tools";
  }
  return null;
}

function withApiCorePrefix(base) {
  const b = String(base || "").trim().replace(/\/+$/, "");
  if (!b) return "";
  if (b.endsWith("/api/core")) return b;
  if (b.endsWith("/api")) return `${b}/core`;
  try {
    const u = new URL(b);
    const path = (u.pathname || "/").replace(/\/+$/, "") || "/";
    if (path === "/") {
      u.pathname = "/api/core";
      return u.toString().replace(/\/+$/, "");
    }
  } catch {
    /* keep */
  }
  return b;
}

function resolveCoreBase(platformBase) {
  const override = (process.env.AIPLAT_CORE_URL || "").trim().replace(/\/+$/, "");
  if (override) return withApiCorePrefix(override);
  const b = String(platformBase || "").trim().replace(/\/+$/, "");
  if (!b) return "";
  if (b.endsWith("/api") || b.endsWith("/api/core")) return withApiCorePrefix(b);
  try {
    const u = new URL(b);
    if (u.port === "8003") {
      u.port = "8002";
      u.pathname = "/api/core";
      return u.toString().replace(/\/+$/, "");
    }
  } catch {
    /* keep */
  }
  return withApiCorePrefix(b);
}

function loadCfg() {
  const baseUrl = (process.env.AIPLAT_PLATFORM_URL || "").trim().replace(/\/+$/, "");
  const token = (process.env.AIPLAT_TENANT_TOKEN || process.env.AIPLAT_API_KEY || "").trim();
  const allowlist = parseAllowlist();
  const coreBaseUrl = resolveCoreBase(baseUrl);
  const enterpriseOn = envTruthy("AIPLAT_ENTERPRISE") && !!baseUrl && !!token;
  const toolsEnabled = enterpriseOn && allowlist.length > 0 && !!coreBaseUrl;
  return { enterpriseOn, toolsEnabled, allowlist, coreBaseUrl, token };
}

async function executeTool(name, params, c) {
  if (!c.toolsEnabled) return { ok: false, error: "tools_off" };
  if (!c.allowlist.includes(name)) return { ok: false, error: "not_allowlisted" };
  const url = `${c.coreBaseUrl}/tools/${encodeURIComponent(name)}/execute`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${c.token}`,
    },
    body: JSON.stringify(params),
  });
  const text = await res.text();
  if (!res.ok) return { ok: false, error: `http_${res.status}`, text };
  return { ok: true, text };
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

async function main() {
  delete process.env.AIPLAT_ENTERPRISE;
  delete process.env.AIPLAT_ENTERPRISE_TOOLS;
  delete process.env.AIPLAT_PLATFORM_URL;
  delete process.env.AIPLAT_CORE_URL;
  delete process.env.AIPLAT_TENANT_TOKEN;
  const off = loadCfg();
  assert(!off.toolsEnabled, "expected tools off");
  console.log("PASS: tools gated off (no allowlist)");

  // URL resolution (mirrors enterprise_tools.ts resolveCoreBaseUrl)
  assert(
    withApiCorePrefix("http://127.0.0.1:8002") === "http://127.0.0.1:8002/api/core",
    "bare :8002 must get /api/core",
  );
  assert(
    withApiCorePrefix("http://host/api") === "http://host/api/core",
    "…/api must become …/api/core",
  );
  assert(
    withApiCorePrefix("http://host/api/core") === "http://host/api/core",
    "…/api/core idempotent",
  );
  delete process.env.AIPLAT_CORE_URL;
  assert(
    resolveCoreBase("http://127.0.0.1:8003") === "http://127.0.0.1:8002/api/core",
    ":8003 → sibling :8002/api/core",
  );
  console.log("PASS: core base URL resolution");

  const server = http.createServer((req, res) => {
    // Core mounts tools under /api/core/tools/{name}/execute
    const okPath =
      req.url === "/api/core/tools/calculator/execute" ||
      req.url === "/tools/calculator/execute";
    if (req.method === "POST" && okPath) {
      const auth = req.headers.authorization || "";
      if (auth !== "Bearer smoke-token") {
        res.writeHead(401);
        res.end(JSON.stringify({ error: "unauthorized" }));
        return;
      }
      res.writeHead(200, { "content-type": "application/json" });
      res.end(
        JSON.stringify({
          ok: true,
          run_id: "run_smoke",
          status: "completed",
          output: { marker: "AIPLAT_MOCK_TOOL_OK" },
        }),
      );
      return;
    }
    res.writeHead(404);
    res.end("not found");
  });

  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  const { port } = server.address();
  process.env.AIPLAT_ENTERPRISE = "1";
  process.env.AIPLAT_PLATFORM_URL = `http://127.0.0.1:${port}`;
  // Bare origin → client appends /api/core (matches real Core FastAPI mount)
  process.env.AIPLAT_CORE_URL = `http://127.0.0.1:${port}`;
  process.env.AIPLAT_TENANT_TOKEN = "smoke-token";
  process.env.AIPLAT_ENTERPRISE_TOOLS = "calculator";

  const on = loadCfg();
  assert(on.toolsEnabled, "expected tools on");
  assert(
    on.coreBaseUrl === `http://127.0.0.1:${port}/api/core`,
    `expected /api/core suffix, got ${on.coreBaseUrl}`,
  );
  const blocked = await executeTool("not_listed", {}, on);
  assert(!blocked.ok, "expected non-allowlisted blocked");
  console.log("PASS: non-allowlisted blocked");

  const r = await executeTool("calculator", { expression: "1+1" }, on);
  assert(r.ok, `execute failed: ${r.error}`);
  assert(String(r.text).includes("AIPLAT_MOCK_TOOL_OK"), "missing mock marker");
  console.log("PASS: mock core tool execute");

  server.close();

  // Tiered allowlist + L3 approval gate (mirror of enterprise_tools.ts)
  delete process.env.AIPLAT_ENTERPRISE_TOOLS;
  delete process.env.AIPLAT_ENTERPRISE_TOOLS_L1;
  delete process.env.AIPLAT_ENTERPRISE_TOOLS_L2;
  delete process.env.AIPLAT_ENTERPRISE_TOOLS_L3;
  delete process.env.AIPLAT_ENTERPRISE_TOOL_CEILING;
  delete process.env.AIPLAT_ENTERPRISE_APPROVAL;

  process.env.AIPLAT_ENTERPRISE_TOOLS_L1 = "wiki_search";
  process.env.AIPLAT_ENTERPRISE_TOOLS_L2 = "calculator";
  process.env.AIPLAT_ENTERPRISE_TOOLS_L3 = "deploy_tool";
  process.env.AIPLAT_ENTERPRISE_TOOL_CEILING = "L2";
  const resolved = resolveToolAllowlist();
  assert(resolved.tierMode === "tiered", "expected tiered mode");
  assert(resolved.ceiling === 2, "ceiling L2");
  assert(resolved.allowlist.includes("wiki_search"), "L1 in allowlist");
  assert(resolved.allowlist.includes("calculator"), "L2 in allowlist");
  assert(!resolved.allowlist.includes("deploy_tool"), "L3 above ceiling excluded");

  const l3Cfg = {
    allowlist: ["deploy_tool"],
    tiers: { deploy_tool: 3 },
    ceiling: 3,
  };
  const l3Blocked = l3GateError("deploy_tool", l3Cfg);
  assert(
    l3Blocked && l3Blocked.includes("l3_requires_approval"),
    "L3 needs approval",
  );
  process.env.AIPLAT_ENTERPRISE_APPROVAL = "1";
  assert(l3GateError("deploy_tool", l3Cfg) === null, "APPROVAL=1 opens L3 gate");

  // flat legacy still L2
  delete process.env.AIPLAT_ENTERPRISE_TOOLS_L1;
  delete process.env.AIPLAT_ENTERPRISE_TOOLS_L2;
  delete process.env.AIPLAT_ENTERPRISE_TOOLS_L3;
  delete process.env.AIPLAT_ENTERPRISE_TOOL_CEILING;
  process.env.AIPLAT_ENTERPRISE_TOOLS = "calculator,wiki_search";
  const flat = resolveToolAllowlist();
  assert(flat.tierMode === "flat", "flat mode");
  assert(flat.tiers.calculator === 2 && flat.tiers.wiki_search === 2, "flat → L2");
  console.log("PASS: L1/L2/L3 tier allowlist + L3 approval gate");

  console.log(`PASS: enterprise_tools_smoke (${pathToFileURL(ENT).href} is TS source of truth)`);
}

main().catch((e) => {
  console.error("FAIL:", e);
  process.exit(1);
});
