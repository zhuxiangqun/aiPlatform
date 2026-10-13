#!/usr/bin/env node
/**
 * Enterprise approval wait-bridge smoke (no Pi / no platform required).
 * Mirrors packages/aiplat-pi-runtime/extensions/enterprise_approval.ts gating + URL + extract.
 */
function envTruthy(name) {
  const v = (process.env[name] || "").trim().toLowerCase();
  return v === "1" || v === "true" || v === "yes" || v === "on";
}

function approvalsBaseUrl(baseUrl) {
  const b = String(baseUrl || "").trim().replace(/\/+$/, "");
  if (!b) return "";
  if (b.endsWith("/platform/approvals")) return b;
  if (b.endsWith("/platform")) return `${b}/approvals`;
  return `${b}/platform/approvals`;
}

function loadApprovalBridgeConfig() {
  const baseUrl = (process.env.AIPLAT_PLATFORM_URL || "").trim().replace(/\/+$/, "");
  const token = (
    process.env.AIPLAT_TENANT_TOKEN ||
    process.env.AIPLAT_API_KEY ||
    ""
  ).trim();
  const enterpriseOn = envTruthy("AIPLAT_ENTERPRISE") && !!baseUrl && !!token;
  if (!enterpriseOn) {
    return {
      approvalEnabled: false,
      reasonApprovalOff: !envTruthy("AIPLAT_ENTERPRISE")
        ? "AIPLAT_ENTERPRISE unset"
        : !baseUrl
          ? "AIPLAT_PLATFORM_URL unset"
          : "token unset",
      baseUrl,
    };
  }
  if (!envTruthy("AIPLAT_ENTERPRISE_APPROVAL")) {
    return {
      approvalEnabled: false,
      reasonApprovalOff: "AIPLAT_ENTERPRISE_APPROVAL unset",
      baseUrl,
    };
  }
  return { approvalEnabled: true, reasonApprovalOff: "", baseUrl };
}

function extractApprovalRequestId(parsed) {
  if (!parsed || typeof parsed !== "object") return "";
  if (typeof parsed.approval_request_id === "string") return parsed.approval_request_id.trim();
  if (parsed.error && typeof parsed.error === "object") {
    const d = parsed.error.detail;
    if (d && typeof d.approval_request_id === "string") return d.approval_request_id.trim();
  }
  return "";
}

function formatApprovalRequiredHint(requestId) {
  const id = String(requestId || "").trim();
  if (!id) return "";
  return `AIPLAT_APPROVAL_REQUIRED\napproval_request_id=${id}`;
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
    "AIPLAT_ENTERPRISE_APPROVAL",
  ]) {
    delete process.env[k];
  }
}

function main() {
  clearEnv();
  let c = loadApprovalBridgeConfig();
  assert(!c.approvalEnabled, "pi-only: approval off");
  console.log("PASS: Pi-only leaves approval bridge off");

  process.env.AIPLAT_ENTERPRISE = "1";
  process.env.AIPLAT_PLATFORM_URL = "http://127.0.0.1:8003/api";
  process.env.AIPLAT_TENANT_TOKEN = "tok";
  c = loadApprovalBridgeConfig();
  assert(!c.approvalEnabled, "enterprise without APPROVAL flag: off");
  console.log("PASS: APPROVAL flag required");

  process.env.AIPLAT_ENTERPRISE_APPROVAL = "1";
  c = loadApprovalBridgeConfig();
  assert(c.approvalEnabled, "APPROVAL=1 enables");
  assert(
    approvalsBaseUrl(c.baseUrl) === "http://127.0.0.1:8003/api/platform/approvals",
    "approvals URL",
  );
  console.log("PASS: APPROVAL=1 enables + URL");

  const id = extractApprovalRequestId({
    status: "approval_required",
    error: { detail: { approval_request_id: "apr-1" } },
  });
  assert(id === "apr-1", "extract id");
  assert(formatApprovalRequiredHint(id).includes("apr-1"), "hint");
  console.log("PASS: extract + hint");

  console.log("AIPLAT_ENTERPRISE_APPROVAL_SMOKE_OK");
}

main();
