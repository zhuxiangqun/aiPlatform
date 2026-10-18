#!/usr/bin/env node
/**
 * Enterprise memory writeback smoke (no Pi / no platform required).
 * Mirrors packages/aiplat-pi-runtime/extensions/enterprise_memory.ts gating + URL + extract.
 */
function envTruthy(name) {
  const v = (process.env[name] || "").trim().toLowerCase();
  return v === "1" || v === "true" || v === "yes" || v === "on";
}

function envExplicitlyOff(name) {
  const raw = (process.env[name] || "").trim();
  if (!raw) return false;
  const v = raw.toLowerCase();
  return v === "0" || v === "false" || v === "no" || v === "off";
}

function memoryCaptureUrl(baseUrl) {
  const b = String(baseUrl || "").trim().replace(/\/+$/, "");
  if (!b) return "";
  if (b.endsWith("/platform/memory/capture")) return b;
  if (b.endsWith("/platform")) return `${b}/memory/capture`;
  return `${b}/platform/memory/capture`;
}

function memoryArchiveUrl(baseUrl) {
  const sticky = memoryStickyUrl(baseUrl);
  if (!sticky) return "";
  if (sticky.endsWith("/sticky")) return `${sticky.slice(0, -"/sticky".length)}/archive`;
  return `${sticky}/archive`;
}

function memoryStickyUrl(baseUrl) {
  const capture = memoryCaptureUrl(baseUrl);
  if (!capture) return "";
  if (capture.endsWith("/capture")) return `${capture.slice(0, -"/capture".length)}/sticky`;
  return `${capture}/sticky`;
}

function loadMemoryBridgeConfig() {
  const baseUrl = (process.env.AIPLAT_PLATFORM_URL || "").trim().replace(/\/+$/, "");
  const token = (
    process.env.AIPLAT_TENANT_TOKEN ||
    process.env.AIPLAT_API_KEY ||
    ""
  ).trim();
  const enterpriseOn = envTruthy("AIPLAT_ENTERPRISE") && !!baseUrl && !!token;
  const sessionId = (
    process.env.AIPLAT_ENTERPRISE_SESSION_ID ||
    process.env.AIPLAT_SESSION_ID ||
    ""
  ).trim();
  if (!enterpriseOn) {
    return {
      memoryEnabled: false,
      autoCapture: false,
      reasonMemoryOff: !envTruthy("AIPLAT_ENTERPRISE")
        ? "AIPLAT_ENTERPRISE unset"
        : !baseUrl
          ? "AIPLAT_PLATFORM_URL unset"
          : "token unset",
      baseUrl,
      sessionId,
    };
  }
  if (!envTruthy("AIPLAT_ENTERPRISE_MEMORY")) {
    return {
      memoryEnabled: false,
      autoCapture: false,
      reasonMemoryOff: "AIPLAT_ENTERPRISE_MEMORY unset",
      baseUrl,
      sessionId,
    };
  }
  return {
    memoryEnabled: true,
    autoCapture: !envExplicitlyOff("AIPLAT_ENTERPRISE_MEMORY_AUTO"),
    reasonMemoryOff: "",
    baseUrl,
    sessionId,
  };
}

function extractTurnSummary(messages) {
  let prompt = "";
  let result = "";
  for (const m of messages || []) {
    if (!m || typeof m !== "object") continue;
    const role = String(m.role || m.type || "").toLowerCase();
    let text = "";
    if (typeof m.content === "string") text = m.content;
    else if (typeof m.text === "string") text = m.text;
    text = text.trim();
    if (!text) continue;
    if (role.includes("user")) prompt = text;
    if (role.includes("assistant")) result = text;
  }
  return { prompt: prompt.slice(0, 4000), result: result.slice(0, 8000) };
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

function clearEnv() {
  for (const k of [
    "AIPLAT_ENTERPRISE",
    "AIPLAT_PLATFORM_URL",
    "AIPLAT_TENANT_TOKEN",
    "AIPLAT_API_KEY",
    "AIPLAT_ENTERPRISE_MEMORY",
    "AIPLAT_ENTERPRISE_MEMORY_AUTO",
    "AIPLAT_ENTERPRISE_SESSION_ID",
    "AIPLAT_SESSION_ID",
  ]) {
    delete process.env[k];
  }
}

function main() {
  clearEnv();
  let c = loadMemoryBridgeConfig();
  assert(!c.memoryEnabled, "pi-only: memory off");
  console.log("PASS: Pi-only leaves memory writeback off");

  process.env.AIPLAT_ENTERPRISE = "1";
  process.env.AIPLAT_PLATFORM_URL = "http://127.0.0.1:8003/api";
  process.env.AIPLAT_TENANT_TOKEN = "tok";
  c = loadMemoryBridgeConfig();
  assert(!c.memoryEnabled, "enterprise without MEMORY flag: off");
  console.log("PASS: MEMORY flag required");

  process.env.AIPLAT_ENTERPRISE_MEMORY = "1";
  c = loadMemoryBridgeConfig();
  assert(c.memoryEnabled, "MEMORY=1 enables");
  assert(c.autoCapture, "auto on by default");
  assert(
    memoryCaptureUrl(c.baseUrl) === "http://127.0.0.1:8003/api/platform/memory/capture",
    "capture URL",
  );
  assert(
    memoryStickyUrl(c.baseUrl) === "http://127.0.0.1:8003/api/platform/memory/sticky",
    "sticky URL",
  );
  assert(
    memoryArchiveUrl(c.baseUrl) === "http://127.0.0.1:8003/api/platform/memory/archive",
    "archive URL",
  );
  console.log("PASS: MEMORY=1 enables + capture/sticky URL");

  process.env.AIPLAT_ENTERPRISE_MEMORY_AUTO = "0";
  c = loadMemoryBridgeConfig();
  assert(c.memoryEnabled && !c.autoCapture, "AUTO=0 disables auto only");
  console.log("PASS: MEMORY_AUTO=0 opt-out");

  const turn = extractTurnSummary([
    { role: "user", content: "hello" },
    { role: "assistant", content: "world" },
  ]);
  assert(turn.prompt === "hello" && turn.result === "world", "extract turn");
  console.log("PASS: extractTurnSummary");

  console.log("AIPLAT_ENTERPRISE_MEMORY_SMOKE_OK");
}

main();
