#!/usr/bin/env node
/**
 * Platform URL normalize smoke (mirrors enterprise_kb.normalizePlatformBaseUrl).
 */
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

function kbQueryUrl(baseUrl) {
  const b = String(baseUrl || "").trim().replace(/\/+$/, "");
  if (!b) return "";
  if (b.endsWith("/platform/kb/query")) return b;
  if (b.endsWith("/platform")) return `${b}/kb/query`;
  return `${b}/platform/kb/query`;
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

function main() {
  assert(
    normalizePlatformBaseUrl("http://127.0.0.1:8003") === "http://127.0.0.1:8003",
    "bare 8003 unchanged",
  );
  assert(
    normalizePlatformBaseUrl("http://127.0.0.1:8003/api") === "http://127.0.0.1:8003",
    "8003/api footgun stripped",
  );
  assert(
    normalizePlatformBaseUrl("http://127.0.0.1:8003/api/platform") ===
      "http://127.0.0.1:8003/platform",
    "8003/api/platform → /platform",
  );
  assert(
    normalizePlatformBaseUrl("http://127.0.0.1:8000") === "http://127.0.0.1:8000/api",
    "bare 8000 → /api",
  );
  assert(
    normalizePlatformBaseUrl("http://127.0.0.1:8000/api") === "http://127.0.0.1:8000/api",
    "8000/api kept",
  );
  assert(
    kbQueryUrl(normalizePlatformBaseUrl("http://127.0.0.1:8003/api")) ===
      "http://127.0.0.1:8003/platform/kb/query",
    "normalized join for platform",
  );
  assert(
    kbQueryUrl(normalizePlatformBaseUrl("http://127.0.0.1:8000")) ===
      "http://127.0.0.1:8000/api/platform/kb/query",
    "normalized join for GW",
  );
  console.log("PASS: platform URL normalize + join");
  console.log("AIPLAT_ENTERPRISE_PLATFORM_URL_SMOKE_OK");
}

main();
