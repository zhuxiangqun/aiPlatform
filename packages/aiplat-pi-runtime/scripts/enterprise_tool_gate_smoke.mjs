#!/usr/bin/env node
/**
 * Enterprise native-tool gate smoke (no Pi required).
 * Mirrors packages/aiplat-pi-runtime/extensions/enterprise_tool_gate.ts policy.
 */
const DEFAULT_NATIVE_BLOCK = ["bash", "powershell", "write", "edit"];
const DEFAULT_NATIVE_ALLOW = ["read", "grep", "find", "ls"];
const ALWAYS_ALLOW_PREFIXES = ["aiplat_"];

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

function parseList(name) {
  const raw = (process.env[name] || "").trim();
  if (!raw) return [];
  return raw
    .split(/[,;\s]+/)
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);
}

function uniq(xs) {
  return [...new Set(xs)];
}

function loadToolGateConfig() {
  const enterpriseOn = envTruthy("AIPLAT_ENTERPRISE");
  if (!enterpriseOn) {
    return {
      enterpriseOn: false,
      gateOn: false,
      allowlist: [],
      blocklist: [],
      reasonOff: "AIPLAT_ENTERPRISE unset",
    };
  }
  if (envTruthy("AIPLAT_ENTERPRISE_ALLOW_NATIVE")) {
    return {
      enterpriseOn: true,
      gateOn: false,
      allowlist: [],
      blocklist: [],
      reasonOff: "AIPLAT_ENTERPRISE_ALLOW_NATIVE=1",
    };
  }
  if (envExplicitlyOff("AIPLAT_ENTERPRISE_TOOL_GATE")) {
    return {
      enterpriseOn: true,
      gateOn: false,
      allowlist: [],
      blocklist: [],
      reasonOff: "AIPLAT_ENTERPRISE_TOOL_GATE=0",
    };
  }
  const extraAllow = parseList("AIPLAT_ENTERPRISE_NATIVE_ALLOWLIST");
  const extraBlock = parseList("AIPLAT_ENTERPRISE_NATIVE_BLOCKLIST");
  const blocklist = uniq([...DEFAULT_NATIVE_BLOCK, ...extraBlock]).filter(
    (t) => !extraAllow.includes(t),
  );
  const allowlist = uniq([...DEFAULT_NATIVE_ALLOW, ...extraAllow]).filter(
    (t) => !extraBlock.includes(t),
  );
  return {
    enterpriseOn: true,
    gateOn: true,
    allowlist,
    blocklist,
    reasonOff: "",
  };
}

function isToolAllowedByGate(toolName, cfg) {
  const c = cfg || loadToolGateConfig();
  const name = String(toolName || "").trim();
  if (!name) return { allowed: false, reason: "empty" };
  if (!c.gateOn) return { allowed: true, reason: c.reasonOff || "gate off" };
  const lower = name.toLowerCase();
  for (const p of ALWAYS_ALLOW_PREFIXES) {
    if (lower.startsWith(p)) return { allowed: true, reason: "aiplat" };
  }
  if (c.blocklist.includes(lower)) return { allowed: false, reason: "blocked" };
  if (c.allowlist.includes(lower)) return { allowed: true, reason: "allowlist" };
  return { allowed: false, reason: "unknown" };
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

function clearGateEnv() {
  for (const k of [
    "AIPLAT_ENTERPRISE",
    "AIPLAT_ENTERPRISE_ALLOW_NATIVE",
    "AIPLAT_ENTERPRISE_TOOL_GATE",
    "AIPLAT_ENTERPRISE_NATIVE_ALLOWLIST",
    "AIPLAT_ENTERPRISE_NATIVE_BLOCKLIST",
  ]) {
    delete process.env[k];
  }
}

function main() {
  clearGateEnv();
  let c = loadToolGateConfig();
  assert(!c.gateOn, "pi-only: gate off");
  assert(isToolAllowedByGate("bash", c).allowed, "pi-only: bash allowed");
  console.log("PASS: Pi-only leaves native tools ungated");

  process.env.AIPLAT_ENTERPRISE = "1";
  c = loadToolGateConfig();
  assert(c.gateOn, "enterprise intent: gate on (no URL/token required)");
  assert(!isToolAllowedByGate("bash", c).allowed, "bash blocked");
  assert(!isToolAllowedByGate("write", c).allowed, "write blocked");
  assert(!isToolAllowedByGate("edit", c).allowed, "edit blocked");
  assert(!isToolAllowedByGate("powershell", c).allowed, "powershell blocked");
  assert(isToolAllowedByGate("read", c).allowed, "read allowed");
  assert(isToolAllowedByGate("grep", c).allowed, "grep allowed");
  assert(isToolAllowedByGate("aiplat_tool_execute", c).allowed, "aiplat_* allowed");
  assert(isToolAllowedByGate("aiplat_handler", c).allowed, "aiplat_handler allowed");
  assert(!isToolAllowedByGate("some_mcp_tool", c).allowed, "unknown fail-closed");
  console.log("PASS: default enterprise blocks mutating natives, allows read-only + aiplat_*");

  process.env.AIPLAT_ENTERPRISE_NATIVE_ALLOWLIST = "bash";
  c = loadToolGateConfig();
  assert(isToolAllowedByGate("bash", c).allowed, "ALLOWLIST overrides default block");
  assert(!isToolAllowedByGate("write", c).allowed, "write still blocked");
  console.log("PASS: NATIVE_ALLOWLIST overrides default block");

  delete process.env.AIPLAT_ENTERPRISE_NATIVE_ALLOWLIST;
  process.env.AIPLAT_ENTERPRISE_NATIVE_BLOCKLIST = "read";
  c = loadToolGateConfig();
  assert(!isToolAllowedByGate("read", c).allowed, "BLOCKLIST can revoke read");
  console.log("PASS: NATIVE_BLOCKLIST extends blocks");

  delete process.env.AIPLAT_ENTERPRISE_NATIVE_BLOCKLIST;
  process.env.AIPLAT_ENTERPRISE_ALLOW_NATIVE = "1";
  c = loadToolGateConfig();
  assert(!c.gateOn, "ALLOW_NATIVE disables gate");
  assert(isToolAllowedByGate("bash", c).allowed, "ALLOW_NATIVE: bash ok");
  console.log("PASS: ALLOW_NATIVE escape hatch");

  delete process.env.AIPLAT_ENTERPRISE_ALLOW_NATIVE;
  process.env.AIPLAT_ENTERPRISE_TOOL_GATE = "0";
  c = loadToolGateConfig();
  assert(!c.gateOn && c.reasonOff.includes("TOOL_GATE"), "TOOL_GATE=0 disables");
  console.log("PASS: TOOL_GATE=0 opt-out");

  console.log("AIPLAT_ENTERPRISE_TOOL_GATE_SMOKE_OK");
}

main();
