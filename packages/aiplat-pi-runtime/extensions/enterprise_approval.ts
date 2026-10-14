/**
 * Factory-out hybrid: ApprovalGate wait/status bridge (read + poll only).
 *
 * Opt-in: AIPLAT_ENTERPRISE=1 + URL/token + AIPLAT_ENTERPRISE_APPROVAL=1.
 * Soft-fails if platform down. Does NOT reimplement ApprovalGate / approve|reject
 * (those stay on platform UI / PolicyGate). Pi waits and surfaces request_id.
 *
 * Tools: aiplat_approval_status | aiplat_approval_pending | aiplat_approval_wait
 * Command: /aiplat-approval
 */
import { Type } from "@earendil-works/pi-ai";
import { defineTool, type ExtensionAPI } from "@earendil-works/pi-coding-agent";

import { CircuitOpenError, platformFetch } from "./enterprise_http";
import {
  loadEnterpriseConfig,
  type EnterpriseConfig,
} from "./enterprise_kb";

export type ApprovalBridgeConfig = EnterpriseConfig & {
  approvalEnabled: boolean;
  reasonApprovalOff: string;
  pollMs: number;
  waitTimeoutMs: number;
};

function envTruthy(name: string): boolean {
  const v = (process.env[name] || "").trim().toLowerCase();
  return v === "1" || v === "true" || v === "yes" || v === "on";
}

function envInt(name: string, fallback: number): number {
  const raw = (process.env[name] || "").trim();
  if (!raw) return fallback;
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : fallback;
}

/** Build …/platform/approvals base from AIPLAT_PLATFORM_URL. */
export function approvalsBaseUrl(baseUrl: string): string {
  const b = String(baseUrl || "").trim().replace(/\/+$/, "");
  if (!b) return "";
  if (b.endsWith("/platform/approvals")) return b;
  if (b.endsWith("/platform")) return `${b}/approvals`;
  return `${b}/platform/approvals`;
}

/** Resolve core /api/core base for approvals fallback (avoid import cycle with tools). */
function resolveCoreApprovalsBase(platformBase: string): string {
  const override = (process.env.AIPLAT_CORE_URL || "").trim().replace(/\/+$/, "");
  let core = override;
  if (!core) {
    const b = String(platformBase || "").trim().replace(/\/+$/, "");
    if (b.endsWith("/api") || b.endsWith("/api/core")) {
      core = b.endsWith("/api/core") ? b : `${b}/core`;
    } else {
      try {
        const u = new URL(b);
        if (u.port === "8003") {
          u.port = "8002";
          u.pathname = "/api/core";
          core = u.toString().replace(/\/+$/, "");
        } else if (u.port === "8000") {
          u.port = "8002";
          u.pathname = "/api/core";
          core = u.toString().replace(/\/+$/, "");
        }
      } catch {
        /* keep */
      }
    }
  }
  if (!core) return "";
  if (!core.endsWith("/api/core") && !core.includes("/api/core")) {
    try {
      const u = new URL(core);
      if ((u.pathname || "/") === "/" || u.pathname === "") {
        u.pathname = "/api/core";
        core = u.toString().replace(/\/+$/, "");
      }
    } catch {
      /* keep */
    }
  }
  return `${core.replace(/\/+$/, "")}/approvals`;
}

/** Candidate approval API roots: platform first, then core (…/api/core/approvals). */
export function approvalsCandidateBases(platformBase: string): string[] {
  const primary = approvalsBaseUrl(platformBase);
  const out: string[] = [];
  if (primary) out.push(primary);
  const coreAppr = resolveCoreApprovalsBase(platformBase);
  if (coreAppr && !out.includes(coreAppr)) out.push(coreAppr);
  return out;
}

export function loadApprovalBridgeConfig(cfg?: EnterpriseConfig): ApprovalBridgeConfig {
  const c = cfg || loadEnterpriseConfig();
  const pollMs = envInt("AIPLAT_ENTERPRISE_APPROVAL_POLL_MS", 2000);
  const waitTimeoutMs = envInt("AIPLAT_ENTERPRISE_APPROVAL_WAIT_MS", 120000);
  if (!c.enabled) {
    return {
      ...c,
      approvalEnabled: false,
      reasonApprovalOff: c.reasonOff || "enterprise off",
      pollMs,
      waitTimeoutMs,
    };
  }
  if (!envTruthy("AIPLAT_ENTERPRISE_APPROVAL")) {
    return {
      ...c,
      approvalEnabled: false,
      reasonApprovalOff: "AIPLAT_ENTERPRISE_APPROVAL unset",
      pollMs,
      waitTimeoutMs,
    };
  }
  return {
    ...c,
    approvalEnabled: true,
    reasonApprovalOff: "",
    pollMs,
    waitTimeoutMs,
  };
}

export type ApprovalHttpResult = {
  ok: boolean;
  status?: number;
  text: string;
  error?: string;
  raw?: unknown;
  decision?: string;
  requestStatus?: string;
  requestId?: string;
};

async function fetchJson(
  url: string,
  token: string,
  init?: RequestInit,
): Promise<ApprovalHttpResult> {
  try {
    const res = await platformFetch(url, {
      ...init,
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${token}`,
        ...(init?.headers || {}),
      },
    });
    const bodyText = await res.text();
    let parsed: unknown = bodyText;
    try {
      parsed = JSON.parse(bodyText);
    } catch {
      /* keep text */
    }
    if (!res.ok) {
      return {
        ok: false,
        status: res.status,
        text: bodyText.slice(0, 2000),
        error: `http_${res.status}`,
        raw: parsed,
      };
    }
    return { ok: true, status: res.status, text: bodyText.slice(0, 4000), raw: parsed };
  } catch (e) {
    if (e instanceof CircuitOpenError) {
      return { ok: false, text: "", error: `circuit: ${e.message}` };
    }
    return {
      ok: false,
      text: "",
      error: `network: ${e && (e as Error).message ? (e as Error).message : e}`,
    };
  }
}

function pickStatus(parsed: unknown): { requestStatus?: string; decision?: string; requestId?: string } {
  if (!parsed || typeof parsed !== "object") return {};
  const o = parsed as Record<string, unknown>;
  const requestStatus = typeof o.status === "string" ? o.status : undefined;
  const requestId = typeof o.request_id === "string" ? o.request_id : undefined;
  let decision: string | undefined;
  const result = o.result;
  if (result && typeof result === "object") {
    const d = (result as Record<string, unknown>).decision;
    if (typeof d === "string") decision = d;
  }
  return { requestStatus, decision, requestId };
}

/** Detect approval_required payloads from tool/execute or other hybrid calls. */
export function extractApprovalRequestId(parsed: unknown): string {
  if (!parsed || typeof parsed !== "object") return "";
  const o = parsed as Record<string, unknown>;
  const direct = o.approval_request_id || o.approval_id;
  if (typeof direct === "string" && direct.trim()) return direct.trim();
  const err = o.error;
  if (err && typeof err === "object") {
    const detail = (err as Record<string, unknown>).detail;
    if (detail && typeof detail === "object") {
      const aid = (detail as Record<string, unknown>).approval_request_id;
      if (typeof aid === "string" && aid.trim()) return aid.trim();
    }
  }
  const status = String(o.status || o.legacy_status || "").toLowerCase();
  if (status === "approval_required" || status === "waiting_approval") {
    const nested = o.detail;
    if (nested && typeof nested === "object") {
      const aid = (nested as Record<string, unknown>).approval_request_id;
      if (typeof aid === "string") return aid.trim();
    }
  }
  return "";
}

export function formatApprovalRequiredHint(requestId: string): string {
  const id = String(requestId || "").trim();
  if (!id) return "";
  return [
    "AIPLAT_APPROVAL_REQUIRED",
    `approval_request_id=${id}`,
    "Wait for a human on the platform Approvals UI, then call aiplat_approval_status or aiplat_approval_wait.",
    "Do not invent approval; do not bypass via native bash/write.",
  ].join("\n");
}

export async function getApprovalStatus(
  requestId: string,
  cfg?: ApprovalBridgeConfig,
): Promise<ApprovalHttpResult> {
  const c = cfg || loadApprovalBridgeConfig();
  if (!c.approvalEnabled) {
    return { ok: false, text: "", error: `approval_off: ${c.reasonApprovalOff}` };
  }
  const id = String(requestId || "").trim();
  if (!id) return { ok: false, text: "", error: "request_id required" };
  let last: ApprovalHttpResult = { ok: false, text: "", error: "no_candidate" };
  for (const base of approvalsCandidateBases(c.baseUrl)) {
    const url = `${base}/${encodeURIComponent(id)}`;
    const r = await fetchJson(url, c.token);
    last = r;
    if (!r.ok && (r.status === 503 || r.status === 404)) continue;
    if (!r.ok) return r;
    const meta = pickStatus(r.raw);
    const lines = [
      "AIPLAT_APPROVAL_STATUS_OK",
      `request_id=${meta.requestId || id}`,
      `status=${meta.requestStatus || "-"}`,
      `decision=${meta.decision || "-"}`,
      `via=${base}`,
    ];
    return {
      ...r,
      text: lines.join("\n"),
      requestStatus: meta.requestStatus,
      decision: meta.decision,
      requestId: meta.requestId || id,
    };
  }
  return last;
}

export async function listPendingApprovals(
  cfg?: ApprovalBridgeConfig,
): Promise<ApprovalHttpResult> {
  const c = cfg || loadApprovalBridgeConfig();
  if (!c.approvalEnabled) {
    return { ok: false, text: "", error: `approval_off: ${c.reasonApprovalOff}` };
  }
  let last: ApprovalHttpResult = { ok: false, text: "", error: "no_candidate" };
  for (const base of approvalsCandidateBases(c.baseUrl)) {
    const url = `${base}/pending?limit=50`;
    const r = await fetchJson(url, c.token);
    last = r;
    if (!r.ok && (r.status === 503 || r.status === 404)) continue;
    if (!r.ok) return r;
    const items =
      r.raw && typeof r.raw === "object" && Array.isArray((r.raw as Record<string, unknown>).items)
        ? ((r.raw as Record<string, unknown>).items as unknown[])
        : [];
    const lines = [`AIPLAT_APPROVAL_PENDING_OK count=${items.length}`, `via=${base}`];
    for (const it of items.slice(0, 20)) {
      if (!it || typeof it !== "object") continue;
      const row = it as Record<string, unknown>;
      lines.push(
        `- ${row.request_id || "?"} status=${row.status || "?"} op=${row.operation || "-"}`,
      );
    }
    return { ...r, text: lines.join("\n") };
  }
  return last;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Poll until approved/rejected/expired/timeout. Soft-fails on network. */
export async function waitForApproval(
  requestId: string,
  cfg?: ApprovalBridgeConfig,
): Promise<ApprovalHttpResult> {
  const c = cfg || loadApprovalBridgeConfig();
  if (!c.approvalEnabled) {
    return { ok: false, text: "", error: `approval_off: ${c.reasonApprovalOff}` };
  }
  const id = String(requestId || "").trim();
  if (!id) return { ok: false, text: "", error: "request_id required" };

  const deadline = Date.now() + c.waitTimeoutMs;
  let last: ApprovalHttpResult = { ok: false, text: "", error: "not_started" };
  while (Date.now() < deadline) {
    last = await getApprovalStatus(id, c);
    if (!last.ok) {
      // soft: keep polling on transient network; stop on 404
      if (last.status === 404) return last;
      await sleep(c.pollMs);
      continue;
    }
    const st = String(last.requestStatus || "").toLowerCase();
    const dec = String(last.decision || "").toLowerCase();
    if (
      st === "approved" ||
      st === "rejected" ||
      st === "denied" ||
      st === "expired" ||
      st === "cancelled" ||
      dec === "approved" ||
      dec === "rejected" ||
      dec === "denied"
    ) {
      return {
        ...last,
        text: `AIPLAT_APPROVAL_WAIT_DONE\n${last.text}`,
      };
    }
    await sleep(c.pollMs);
  }
  return {
    ok: false,
    text: last.text || "",
    error: `wait_timeout_ms=${c.waitTimeoutMs}`,
    requestId: id,
    requestStatus: last.requestStatus,
    decision: last.decision,
    raw: last.raw,
  };
}

export function approvalStatusLines(cfg?: ApprovalBridgeConfig): string[] {
  const c = cfg || loadApprovalBridgeConfig();
  return [
    "aiPlat enterprise approval wait bridge (hybrid)",
    `approval_enabled=${c.approvalEnabled}`,
    `reason_off=${c.reasonApprovalOff || "-"}`,
    `approvals_url=${approvalsBaseUrl(c.baseUrl) || "(none)"}`,
    `poll_ms=${c.pollMs}`,
    `wait_timeout_ms=${c.waitTimeoutMs}`,
    "note=no approve/reject from Pi (platform UI only)",
    c.approvalEnabled ? "AIPLAT_ENTERPRISE_APPROVAL_ON" : "AIPLAT_ENTERPRISE_APPROVAL_OFF",
  ];
}

export function approvalSystemPromptAddon(cfg?: ApprovalBridgeConfig): string {
  const c = cfg || loadApprovalBridgeConfig();
  if (!c.approvalEnabled) return "";
  return [
    "",
    "## aiPlat Enterprise Approval",
    "If a tool returns approval_required / AIPLAT_APPROVAL_REQUIRED, use aiplat_approval_wait or aiplat_approval_status.",
    "Humans approve in the platform Approvals UI — do not invent approvals or bypass with native shell.",
  ].join("\n");
}

export function registerEnterpriseApproval(pi: ExtensionAPI): boolean {
  const cfg = loadApprovalBridgeConfig();
  if (!cfg.approvalEnabled) return false;

  pi.registerTool(
    defineTool({
      name: "aiplat_approval_status",
      label: "aiPlat Approval Status",
      description:
        "Get status of a platform approval request by id (hybrid). Soft-fails if platform down.",
      parameters: Type.Object({
        request_id: Type.String({ description: "approval_request_id from tool execute" }),
      }),
      async execute(_toolCallId, params) {
        const r = await getApprovalStatus(String(params.request_id || ""), cfg);
        if (!r.ok) {
          return {
            content: [
              {
                type: "text" as const,
                text: `AIPLAT_APPROVAL_STATUS_FAILED: ${r.error || "unknown"}\n${r.text || ""}`,
              },
            ],
            details: r,
            isError: true,
          };
        }
        return {
          content: [{ type: "text" as const, text: r.text }],
          details: { status: r.status, requestStatus: r.requestStatus, decision: r.decision },
        };
      },
    }),
  );

  pi.registerTool(
    defineTool({
      name: "aiplat_approval_pending",
      label: "aiPlat Approval Pending",
      description: "List pending platform approval requests (hybrid, read-only).",
      parameters: Type.Object({}),
      async execute() {
        const r = await listPendingApprovals(cfg);
        if (!r.ok) {
          return {
            content: [
              {
                type: "text" as const,
                text: `AIPLAT_APPROVAL_PENDING_FAILED: ${r.error || "unknown"}\n${r.text || ""}`,
              },
            ],
            details: r,
            isError: true,
          };
        }
        return {
          content: [{ type: "text" as const, text: r.text }],
          details: { status: r.status },
        };
      },
    }),
  );

  pi.registerTool(
    defineTool({
      name: "aiplat_approval_wait",
      label: "aiPlat Approval Wait",
      description:
        "Poll platform until approval request is decided or timeout (hybrid). Does not approve.",
      parameters: Type.Object({
        request_id: Type.String({ description: "approval_request_id to wait on" }),
      }),
      async execute(_toolCallId, params) {
        const r = await waitForApproval(String(params.request_id || ""), cfg);
        if (!r.ok) {
          return {
            content: [
              {
                type: "text" as const,
                text: `AIPLAT_APPROVAL_WAIT_FAILED: ${r.error || "unknown"}\n${r.text || ""}`,
              },
            ],
            details: r,
            isError: true,
          };
        }
        return {
          content: [{ type: "text" as const, text: r.text }],
          details: { status: r.status, requestStatus: r.requestStatus, decision: r.decision },
        };
      },
    }),
  );

  pi.registerCommand("aiplat-approval", {
    description: "Show approval wait-bridge status (hybrid)",
    handler: async (_args, ctx) => {
      const lines = approvalStatusLines(loadApprovalBridgeConfig());
      const text = lines.join("\n");
      console.log(text);
      try {
        ctx.ui.notify(text, "info");
      } catch {
        /* no UI */
      }
    },
  });

  return true;
}
