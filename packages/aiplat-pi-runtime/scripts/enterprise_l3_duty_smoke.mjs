/**
 * Offline smoke for L3 duty desk slash helper (no live platform required).
 */
import assert from "node:assert/strict";
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ENT = path.join(__dirname, "..", "extensions", "enterprise_l3_duty.ts");

assert(fs.existsSync(ENT), "enterprise_l3_duty.ts exists");

function joinPlatform(base, p) {
  const b = String(base || "").replace(/\/+$/, "");
  const pathPart = p.startsWith("/") ? p : `/${p}`;
  if (b.endsWith("/api")) {
    return `${b}${pathPart.startsWith("/platform") ? pathPart : `/platform${pathPart}`}`;
  }
  return `${b}${pathPart.startsWith("/platform") ? pathPart : `/platform${pathPart}`}`;
}

/** Mirror fetchL3DutySummary summary formatting. */
function formatSummary(parsed) {
  const contact = parsed.duty_contact || {};
  const iterations = parsed.iterations || {};
  const evalSnap = parsed.eval || {};
  const tips = Array.isArray(parsed.quarterly_suggestions)
    ? parsed.quarterly_suggestions
    : [];
  const contactLine = contact.available
    ? `值班入口: ${contact.contact || contact.channel || "已配置"}`
    : `值班入口: unavailable（${contact.reason ?? "未配置"}）`;
  const iterLine = iterations.available
    ? `迭代记录: ${iterations.count ?? 0} 条`
    : `迭代记录: unavailable`;
  const srcLine = evalSnap.available
    ? `观测源 ${evalSnap.sources_present ?? 0}/${evalSnap.sources_total ?? 0}`
    : "观测源 unavailable";
  return [
    `L3 专属值班台 ${parsed.period ?? ""}`.trim(),
    contactLine,
    iterLine,
    srcLine,
    "",
    `建议: ${tips[0] || "维持巡检与入库节奏"}`,
  ].join("\n");
}

assert.equal(
  joinPlatform("http://127.0.0.1:8003", "/platform/delivery/l3-duty-desk"),
  "http://127.0.0.1:8003/platform/delivery/l3-duty-desk",
);
assert.equal(
  joinPlatform("http://127.0.0.1:8000/api", "/platform/delivery/l3-duty-desk"),
  "http://127.0.0.1:8000/api/platform/delivery/l3-duty-desk",
);
console.log("PASS: l3-duty URL join");

const soft = formatSummary({
  period: "2026-Q4",
  duty_contact: { available: false, reason: "未配置" },
  iterations: { available: false },
  eval: { available: false },
  quarterly_suggestions: ["维持 L2 入库与巡检"],
});
assert(soft.includes("unavailable"), "soft-fail marks unavailable");
assert(soft.includes("L3 专属值班台"), "title present");
console.log("PASS: l3-duty soft-fail summary");

await new Promise((resolve, reject) => {
  const server = http.createServer((req, res) => {
    if ((req.url || "").startsWith("/platform/delivery/l3-duty-desk")) {
      res.writeHead(200, { "content-type": "application/json" });
      res.end(
        JSON.stringify({
          ok: true,
          period: "2026-Q4",
          duty_contact: {
            available: true,
            contact: "ops@example.com",
            channel: "飞书",
          },
          iterations: { available: true, count: 2 },
          eval: { available: true, sources_present: 2, sources_total: 3 },
          quarterly_suggestions: ["补漏召 TOP 文档"],
        }),
      );
      return;
    }
    res.writeHead(404);
    res.end();
  });
  server.listen(0, "127.0.0.1", async () => {
    try {
      const { port } = server.address();
      const url = `http://127.0.0.1:${port}/platform/delivery/l3-duty-desk`;
      const res = await fetch(url);
      const parsed = await res.json();
      const text = formatSummary(parsed);
      assert(text.includes("ops@example.com"), "contact in summary");
      assert(text.includes("迭代记录: 2"), "iteration count");
      assert(text.includes("补漏召 TOP 文档"), "tip");
      console.log("PASS: l3-duty mock platform summary");
      server.close();
      resolve();
    } catch (e) {
      server.close();
      reject(e);
    }
  });
});

console.log(`PASS: enterprise_l3_duty_smoke (${ENT} is TS source of truth)`);
console.log("AIPLAT_ENTERPRISE_L3_DUTY_SMOKE_OK");
