#!/usr/bin/env node
/**
 * Enterprise approval wait-bridge + Unattended attendance smoke (no Pi / no platform).
 * Mirrors packages/aiplat-pi-runtime/extensions/enterprise_approval.ts gating + extract.
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

function normalizeAttendance(value) {
  if (typeof value === "boolean") return value ? "inbox" : "attended";
  const text = String(value || "")
    .trim()
    .toLowerCase();
  if (text === "true" || text === "on" || text === "unattended") return "inbox";
  if (text === "inbox" || text === "auto" || text === "attended") return text;
  return "attended";
}

function resolveAttendance() {
  return normalizeAttendance(
    process.env.AIPLAT_ENTERPRISE_ATTENDANCE ||
      process.env.AIPLAT_TOOL_ATTENDANCE ||
      "",
  );
}

function resolveApprovalSessionId() {
  const sid = (
    process.env.AIPLAT_ENTERPRISE_SESSION_ID ||
    process.env.AIPLAT_SESSION_ID ||
    ""
  ).trim();
  return sid || "pi-hybrid";
}

function attendanceInjectFields() {
  return {
    _attendance: resolveAttendance(),
    _session_id: resolveApprovalSessionId(),
    attendance: resolveAttendance(),
    session_id: resolveApprovalSessionId(),
  };
}

function loadApprovalBridgeConfig() {
  const baseUrl = (process.env.AIPLAT_PLATFORM_URL || "").trim().replace(/\/+$/, "");
  const token = (
    process.env.AIPLAT_TENANT_TOKEN ||
    process.env.AIPLAT_API_KEY ||
    ""
  ).trim();
  const attendance = resolveAttendance();
  const sessionId = resolveApprovalSessionId();
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
      attendance,
      sessionId,
    };
  }
  if (!envTruthy("AIPLAT_ENTERPRISE_APPROVAL")) {
    return {
      approvalEnabled: false,
      reasonApprovalOff: "AIPLAT_ENTERPRISE_APPROVAL unset",
      baseUrl,
      attendance,
      sessionId,
    };
  }
  return {
    approvalEnabled: true,
    reasonApprovalOff: "",
    baseUrl,
    attendance,
    sessionId,
  };
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

function extractInboxItemId(parsed) {
  if (!parsed || typeof parsed !== "object") return "";
  if (typeof parsed.inbox_item_id === "string") return parsed.inbox_item_id.trim();
  if (parsed.detail && typeof parsed.detail === "object") {
    const id = parsed.detail.inbox_item_id;
    if (typeof id === "string") return id.trim();
  }
  return "";
}

function formatApprovalRequiredHint(requestId, inboxItemId) {
  const id = String(requestId || "").trim();
  const inbox = String(inboxItemId || "").trim();
  if (!id && !inbox) return "";
  const lines = ["AIPLAT_APPROVAL_REQUIRED"];
  if (id) lines.push(`approval_request_id=${id}`);
  if (inbox) {
    lines.push(`inbox_item_id=${inbox}`);
    lines.push("Item parked in Unattended Inbox");
  }
  return lines.join("\n");
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
    "AIPLAT_ENTERPRISE_ATTENDANCE",
    "AIPLAT_TOOL_ATTENDANCE",
    "AIPLAT_ENTERPRISE_SESSION_ID",
    "AIPLAT_SESSION_ID",
  ]) {
    delete process.env[k];
  }
}

function main() {
  clearEnv();
  let c = loadApprovalBridgeConfig();
  assert(!c.approvalEnabled, "pi-only: approval off");
  assert(c.attendance === "attended", "default attendance attended");
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

  process.env.AIPLAT_ENTERPRISE_ATTENDANCE = "inbox";
  process.env.AIPLAT_ENTERPRISE_SESSION_ID = "pi-sess-1";
  c = loadApprovalBridgeConfig();
  assert(c.attendance === "inbox", "attendance inbox");
  assert(c.sessionId === "pi-sess-1", "session id");
  const inj = attendanceInjectFields();
  assert(inj._attendance === "inbox", "inject _attendance");
  assert(inj._session_id === "pi-sess-1", "inject _session_id");
  console.log("PASS: attendance + inject fields");

  process.env.AIPLAT_ENTERPRISE_ATTENDANCE = "auto";
  assert(resolveAttendance() === "auto", "auto mode");
  process.env.AIPLAT_ENTERPRISE_ATTENDANCE = "weird";
  assert(resolveAttendance() === "attended", "unknown → attended");
  console.log("PASS: attendance normalize");

  const id = extractApprovalRequestId({
    status: "approval_required",
    error: { detail: { approval_request_id: "apr-1" } },
  });
  assert(id === "apr-1", "extract id");
  const inbox = extractInboxItemId({
    status: "approval_required",
    inbox_item_id: "inbox-9",
    detail: { approval_request_id: "apr-1" },
  });
  assert(inbox === "inbox-9", "extract inbox");
  const hint = formatApprovalRequiredHint(id, inbox);
  assert(hint.includes("apr-1") && hint.includes("inbox-9"), "hint");
  console.log("PASS: extract + hint with inbox");

  console.log("AIPLAT_ENTERPRISE_APPROVAL_SMOKE_OK");
}

main();
