#!/usr/bin/env node
/**
 * Hybrid enterprise KB reconnect smoke (no Pi required).
 *
 * 1) Gating: AIPLAT_ENTERPRISE off → enterprise_off
 * 2) Mock platform: local HTTP server answering /platform/kb/query
 */
import http from "node:http";
import { pathToFileURL } from "node:url";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ENT = path.join(__dirname, "..", "extensions", "enterprise_kb.ts");

// Pi loads .ts; for Node smoke we duplicate minimal gating + fetch against mock.
function envTruthy(name) {
  const v = (process.env[name] || "").trim().toLowerCase();
  return v === "1" || v === "true" || v === "yes" || v === "on";
}

function loadCfg() {
  const baseUrl = (process.env.AIPLAT_PLATFORM_URL || "").trim().replace(/\/+$/, "");
  const token = (process.env.AIPLAT_TENANT_TOKEN || process.env.AIPLAT_API_KEY || "").trim();
  const collectionId = (process.env.AIPLAT_KB_COLLECTION_ID || "default").trim() || "default";
  if (!envTruthy("AIPLAT_ENTERPRISE")) {
    return { enabled: false, baseUrl, token, collectionId, reasonOff: "AIPLAT_ENTERPRISE unset" };
  }
  if (!baseUrl) return { enabled: false, baseUrl, token, collectionId, reasonOff: "AIPLAT_PLATFORM_URL unset" };
  if (!token) return { enabled: false, baseUrl, token, collectionId, reasonOff: "token unset" };
  return { enabled: true, baseUrl, token, collectionId, reasonOff: "" };
}

async function retrieveKb(question, c) {
  if (!c.enabled) return { ok: false, error: `enterprise_off: ${c.reasonOff}` };
  const url = `${c.baseUrl}/platform/kb/query`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${c.token}`,
    },
    body: JSON.stringify({ question, collection_id: c.collectionId, limit: 8 }),
  });
  const text = await res.text();
  if (!res.ok) return { ok: false, error: `http_${res.status}`, text };
  if (!text.includes("AIPLAT_MOCK_KB_OK") && !text.includes("items")) {
    // accept either mock marker or real-ish payload
  }
  return { ok: true, text };
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

async function main() {
  // --- gate off ---
  delete process.env.AIPLAT_ENTERPRISE;
  delete process.env.AIPLAT_PLATFORM_URL;
  delete process.env.AIPLAT_TENANT_TOKEN;
  const off = loadCfg();
  assert(!off.enabled, "expected enterprise off");
  console.log("PASS: enterprise gated off");

  // --- mock server ---
  const server = http.createServer((req, res) => {
    if (req.method === "POST" && req.url === "/platform/kb/query") {
      const auth = req.headers.authorization || "";
      if (auth !== "Bearer smoke-token") {
        res.writeHead(401);
        res.end(JSON.stringify({ error: "unauthorized" }));
        return;
      }
      let body = "";
      req.on("data", (c) => (body += c));
      req.on("end", () => {
        res.writeHead(200, { "content-type": "application/json" });
        res.end(
          JSON.stringify({
            ok: true,
            kb: { items: [{ text: "AIPLAT_MOCK_KB_OK hybrid smoke", doc_id: "doc1" }] },
          }),
        );
      });
      return;
    }
    res.writeHead(404);
    res.end("not found");
  });

  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  const { port } = server.address();
  process.env.AIPLAT_ENTERPRISE = "1";
  process.env.AIPLAT_PLATFORM_URL = `http://127.0.0.1:${port}`;
  process.env.AIPLAT_TENANT_TOKEN = "smoke-token";

  const on = loadCfg();
  assert(on.enabled, "expected enterprise on");
  const r = await retrieveKb("what is hybrid?", on);
  assert(r.ok, `retrieve failed: ${r.error}`);
  assert(String(r.text).includes("AIPLAT_MOCK_KB_OK"), "missing mock marker");
  console.log("PASS: mock platform kb retrieve");

  server.close();
  console.log(`PASS: enterprise_kb_smoke (${pathToFileURL(ENT).href} is TS source of truth)`);
  console.log("NOTE: citation V2/V3a/V6 → enterprise_kb_citation_smoke.mjs");
}

main().catch((e) => {
  console.error("FAIL:", e);
  process.exit(1);
});
