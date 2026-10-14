/**
 * Offline smoke for KB health bridge (mirrors enterprise_kb_smoke style).
 * Does not import .ts (enterprise_kb pulls citation / Pi resolution footguns).
 *
 * 1) Enterprise off → soft-fail copy
 * 2) Mock platform GET /platform/delivery/kb-health → summary lines
 */
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ENT = path.join(__dirname, "..", "extensions", "enterprise_kb_health.ts");

function envTruthy(name) {
  const v = (process.env[name] || "").trim().toLowerCase();
  return v === "1" || v === "true" || v === "yes" || v === "on";
}

function loadCfg() {
  const baseUrl = (process.env.AIPLAT_PLATFORM_URL || "").trim().replace(/\/+$/, "");
  const token = (
    process.env.AIPLAT_TENANT_TOKEN ||
    process.env.AIPLAT_API_KEY ||
    ""
  ).trim();
  const collectionId =
    (process.env.AIPLAT_KB_COLLECTION_ID || "default").trim() || "default";
  if (!envTruthy("AIPLAT_ENTERPRISE")) {
    return {
      enabled: false,
      baseUrl,
      token,
      collectionId,
      reasonOff: "AIPLAT_ENTERPRISE unset",
    };
  }
  if (!baseUrl) {
    return { enabled: false, baseUrl, token, collectionId, reasonOff: "PLATFORM_URL unset" };
  }
  if (!token) {
    return { enabled: false, baseUrl, token, collectionId, reasonOff: "token unset" };
  }
  return { enabled: true, baseUrl, token, collectionId, reasonOff: "" };
}

function joinPlatform(base, pathSuffix) {
  const b = String(base || "").replace(/\/+$/, "");
  const p = pathSuffix.startsWith("/") ? pathSuffix : `/${pathSuffix}`;
  if (b.endsWith("/api")) {
    return `${b}${p.startsWith("/platform") ? p : `/platform${p}`}`;
  }
  return `${b}${p.startsWith("/platform") ? p : `/platform${p}`}`;
}

/** Mirror enterprise_kb_health.fetchKbHealthSummary (no TS import). */
async function fetchKbHealthSummary(c) {
  if (!c.enabled) {
    return {
      ok: false,
      text: "知识库健康面板暂不可用（未启用企业回连：AIPLAT_ENTERPRISE=1）",
    };
  }
  if (!c.baseUrl || !c.token) {
    return { ok: false, text: "知识库健康面板暂不可用（缺少 PLATFORM_URL / token）" };
  }
  const url = new URL(joinPlatform(c.baseUrl, "/platform/delivery/kb-health"));
  url.searchParams.set("collection_id", c.collectionId || "default");
  url.searchParams.set("window_hours", "168");
  url.searchParams.set("format", "json");
  const res = await fetch(url.toString(), {
    headers: {
      authorization: `Bearer ${c.token}`,
      accept: "application/json",
    },
  });
  const text = await res.text();
  if (!res.ok) {
    return { ok: false, text: `知识库健康面板暂不可用（http=${res.status}）` };
  }
  let parsed = {};
  try {
    parsed = JSON.parse(text);
  } catch {
    return { ok: false, text: "知识库健康面板暂不可用（响应非 JSON）" };
  }
  const health = parsed.health || {};
  const metrics = parsed.metrics || {};
  const stats = parsed.stats || {};
  const week = parsed.docs_this_week || {};
  const tips = Array.isArray(parsed.suggestions) ? parsed.suggestions : [];
  const lines = [
    `知识库健康分: ${health.score ?? "n/a"}/100（${health.label ?? "-"}）`,
    `本周查询 ${metrics.total_queries ?? "n/a"} 次 | 文档 ${stats.documents ?? "n/a"} 篇 | 新增 ${week.count ?? "n/a"} 篇`,
    `漏召率 ${metrics.no_answer_rate_pct ?? "n/a"}% | 引用覆盖率 ${metrics.citation_coverage_pct ?? "n/a"}%`,
    "",
    `建议: ${tips[0] || "维持当前入库节奏"}`,
  ];
  return { ok: true, text: lines.join("\n") };
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

async function main() {
  const prev = { ...process.env };
  try {
    delete process.env.AIPLAT_ENTERPRISE;
    delete process.env.AIPLAT_PLATFORM_URL;
    delete process.env.AIPLAT_TENANT_TOKEN;

    const off = await fetchKbHealthSummary(loadCfg());
    assert(off.ok === false, "enterprise off → ok=false");
    assert(off.text.includes("暂不可用"), "soft-fail copy");
    console.log("PASS: kb-health soft-fail when enterprise off");

    assert(
      joinPlatform("http://127.0.0.1:8003", "/platform/delivery/kb-health") ===
        "http://127.0.0.1:8003/platform/delivery/kb-health",
      "direct platform join",
    );
    assert(
      joinPlatform("http://127.0.0.1:8000/api", "/platform/delivery/kb-health") ===
        "http://127.0.0.1:8000/api/platform/delivery/kb-health",
      "GW /api join",
    );
    console.log("PASS: kb-health URL join");

    const server = http.createServer((req, res) => {
      if ((req.url || "").startsWith("/platform/delivery/kb-health")) {
        res.writeHead(200, { "content-type": "application/json" });
        res.end(
          JSON.stringify({
            status: "ok",
            health: { score: 82, label: "良好", band: "blue" },
            metrics: {
              total_queries: 100,
              no_answer_rate_pct: 12.3,
              citation_coverage_pct: 87.7,
            },
            stats: { documents: 156 },
            docs_this_week: { count: 12 },
            suggestions: ["建议补充「差旅报销标准」相关文档（来自漏召 TOP）"],
          }),
        );
        return;
      }
      res.writeHead(404);
      res.end();
    });
    await new Promise((r) => server.listen(0, "127.0.0.1", r));
    const { port } = server.address();
    process.env.AIPLAT_ENTERPRISE = "1";
    process.env.AIPLAT_PLATFORM_URL = `http://127.0.0.1:${port}`;
    process.env.AIPLAT_TENANT_TOKEN = "dev";
    const on = await fetchKbHealthSummary(loadCfg());
    server.close();
    assert(on.ok === true, "mock health ok");
    assert(on.text.includes("82/100"), "score in summary");
    assert(on.text.includes("差旅报销标准"), "suggestion in summary");
    console.log("PASS: kb-health mock platform summary");
    console.log(`PASS: enterprise_kb_health_smoke (${ENT} is TS source of truth)`);
  } finally {
    for (const k of ["AIPLAT_ENTERPRISE", "AIPLAT_PLATFORM_URL", "AIPLAT_TENANT_TOKEN"]) {
      if (prev[k] !== undefined) process.env[k] = prev[k];
      else delete process.env[k];
    }
  }
  console.log("AIPLAT_ENTERPRISE_KB_HEALTH_SMOKE_OK");
}

main().catch((e) => {
  console.error("FAIL:", e && e.message ? e.message : e);
  process.exit(1);
});
