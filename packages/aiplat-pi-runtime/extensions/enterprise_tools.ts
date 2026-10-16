/**
 * Factory-out hybrid (enterprise): allowlisted tool execute via aiPlat core HTTP.
 *
 * Requires AIPLAT_ENTERPRISE=1 + URL/token (same gate as KB) **and** an allowlist:
 * - Flat: ``AIPLAT_ENTERPRISE_TOOLS=a,b`` (legacy; all treated as L2)
 * - Tiered: ``AIPLAT_ENTERPRISE_TOOLS_L1|L2|L3`` (L1 read / L2 compute / L3 write)
 *   + optional ``AIPLAT_ENTERPRISE_TOOL_CEILING=L1|L2|L3`` (default L3)
 * L3 execute requires ``AIPLAT_ENTERPRISE_APPROVAL=1`` (fail closed).
 * Soft-fails if platform unreachable. RBAC / PolicyGate stay on the server.
 */
import { Type } from "@earendil-works/pi-ai";
import { defineTool, type ExtensionAPI } from "@earendil-works/pi-coding-agent";

import {
  attendanceInjectFields,
  extractApprovalRequestId,
  extractInboxItemId,
  formatApprovalRequiredHint,
} from "./enterprise_approval";
import { CircuitOpenError, platformFetch } from "./enterprise_http";
import {
  loadEnterpriseConfig,
  type EnterpriseConfig,
} from "./enterprise_kb";

/** Risk tier: 1=read-only, 2=compute, 3=write / high-risk (needs approval bridge). */
export type ToolTier = 1 | 2 | 3;

export type ToolProxyConfig = EnterpriseConfig & {
  toolsEnabled: boolean;
  allowlist: string[];
  /** tool_name → tier (only present for allowlisted names) */
  tiers: Record<string, ToolTier>;
  /** Max tier allowed in this session */
  ceiling: ToolTier;
  /** flat = only AIPLAT_ENTERPRISE_TOOLS; tiered = L1/L2/L3 envs present */
  tierMode: "flat" | "tiered";
  coreBaseUrl: string;
  reasonToolsOff: string;
};

function parseNameList(raw: string): string[] {
  const s = String(raw || "").trim();
  if (!s) return [];
  return s
    .split(/[,;\s]+/)
    .map((x) => x.trim())
    .filter(Boolean);
}

function parseAllowlist(): string[] {
  return parseNameList(process.env.AIPLAT_ENTERPRISE_TOOLS || "");
}

function parseCeiling(): ToolTier {
  const raw = (process.env.AIPLAT_ENTERPRISE_TOOL_CEILING || "L3").trim().toUpperCase();
  if (raw === "1" || raw === "L1") return 1;
  if (raw === "2" || raw === "L2") return 2;
  return 3;
}

function approvalBridgeEnabled(): boolean {
  const v = (process.env.AIPLAT_ENTERPRISE_APPROVAL || "").trim().toLowerCase();
  return v === "1" || v === "true" || v === "yes" || v === "on";
}

/**
 * Build allowlist + tier map. Tiered mode when any L1/L2/L3 env is non-empty;
 * flat ``AIPLAT_ENTERPRISE_TOOLS`` still merges as L2 when tiered.
 */
export function resolveToolAllowlist(): {
  allowlist: string[];
  tiers: Record<string, ToolTier>;
  ceiling: ToolTier;
  tierMode: "flat" | "tiered";
} {
  const l1 = parseNameList(process.env.AIPLAT_ENTERPRISE_TOOLS_L1 || "");
  const l2 = parseNameList(process.env.AIPLAT_ENTERPRISE_TOOLS_L2 || "");
  const l3 = parseNameList(process.env.AIPLAT_ENTERPRISE_TOOLS_L3 || "");
  const flat = parseAllowlist();
  const ceiling = parseCeiling();
  const tiered = l1.length + l2.length + l3.length > 0;
  const tiers: Record<string, ToolTier> = {};
  if (!tiered) {
    for (const n of flat) tiers[n] = 2;
    const allowlist = Object.keys(tiers).filter((n) => (tiers[n] as number) <= ceiling);
    return { allowlist, tiers, ceiling, tierMode: "flat" };
  }
  for (const n of l1) tiers[n] = 1;
  for (const n of l2) tiers[n] = 2;
  for (const n of l3) tiers[n] = 3;
  for (const n of flat) {
    if (!(n in tiers)) tiers[n] = 2;
  }
  const allowlist = Object.keys(tiers).filter((n) => (tiers[n] as number) <= ceiling);
  return { allowlist, tiers, ceiling, tierMode: "tiered" };
}

/** Ensure base ends at the FastAPI prefix that mounts tools (`/api/core`). */
function withApiCorePrefix(base: string): string {
  const b = String(base || "").trim().replace(/\/+$/, "");
  if (!b) return "";
  if (b.endsWith("/api/core")) return b;
  if (b.endsWith("/api")) return `${b}/core`;
  try {
    const u = new URL(b);
    const path = (u.pathname || "/").replace(/\/+$/, "") || "/";
    // Bare origin (http://host:8002) → http://host:8002/api/core
    if (path === "/") {
      u.pathname = "/api/core";
      return u.toString().replace(/\/+$/, "");
    }
  } catch {
    /* keep */
  }
  return b;
}

/** Resolve core API base for /tools/{name}/execute (mgmt GW or direct core). */
export function resolveCoreBaseUrl(platformBase: string): string {
  const override = (process.env.AIPLAT_CORE_URL || "").trim().replace(/\/+$/, "");
  if (override) return withApiCorePrefix(override);
  const b = String(platformBase || "").trim().replace(/\/+$/, "");
  if (!b) return "";
  // Management / unified gateway: …/api → …/api/core
  if (b.endsWith("/api") || b.endsWith("/api/core")) return withApiCorePrefix(b);
  // Direct platform :8003 → sibling core :8002/api/core (common local layout)
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
  // PLATFORM_URL already pointed at core host → append /api/core when bare
  return withApiCorePrefix(b);
}

export function toolExecuteUrl(coreBase: string, toolName: string): string {
  const b = String(coreBase || "").trim().replace(/\/+$/, "");
  const name = encodeURIComponent(String(toolName || "").trim());
  if (!b || !name) return "";
  if (b.includes("/tools/") && b.endsWith("/execute")) {
    return b.replace(/\/tools\/[^/]+\/execute$/, `/tools/${name}/execute`);
  }
  return `${b}/tools/${name}/execute`;
}

export function loadToolProxyConfig(cfg?: EnterpriseConfig): ToolProxyConfig {
  const c = cfg || loadEnterpriseConfig();
  const resolved = resolveToolAllowlist();
  const { allowlist, tiers, ceiling, tierMode } = resolved;
  const coreBaseUrl = resolveCoreBaseUrl(c.baseUrl);
  const baseOff = {
    ...c,
    toolsEnabled: false as const,
    allowlist,
    tiers,
    ceiling,
    tierMode,
    coreBaseUrl,
  };
  if (!c.enabled) {
    return { ...baseOff, reasonToolsOff: c.reasonOff || "enterprise off" };
  }
  if (!allowlist.length) {
    return {
      ...baseOff,
      reasonToolsOff:
        tierMode === "tiered"
          ? "no tools at or below AIPLAT_ENTERPRISE_TOOL_CEILING (set L1/L2/L3 and/or raise ceiling)"
          : "AIPLAT_ENTERPRISE_TOOLS empty (allowlist required)",
    };
  }
  if (!coreBaseUrl) {
    return {
      ...baseOff,
      reasonToolsOff: "AIPLAT_CORE_URL / core base unresolved",
    };
  }
  return {
    ...c,
    toolsEnabled: true,
    allowlist,
    tiers,
    ceiling,
    tierMode,
    coreBaseUrl,
    reasonToolsOff: "",
  };
}

export type ToolExecuteResult = {
  ok: boolean;
  status?: number;
  text: string;
  error?: string;
  raw?: unknown;
};

export async function executeEnterpriseTool(
  toolName: string,
  params: Record<string, unknown>,
  cfg?: ToolProxyConfig,
): Promise<ToolExecuteResult> {
  const c = cfg || loadToolProxyConfig();
  if (!c.toolsEnabled) {
    return { ok: false, text: "", error: `tools_off: ${c.reasonToolsOff}` };
  }
  const name = String(toolName || "").trim();
  if (!name) return { ok: false, text: "", error: "tool_name required" };
  if (!c.allowlist.includes(name)) {
    const tier = c.tiers[name];
    if (tier && tier > c.ceiling) {
      return {
        ok: false,
        text: "",
        error: `tool_above_ceiling: ${name} is L${tier} but ceiling=L${c.ceiling}`,
      };
    }
    return {
      ok: false,
      text: "",
      error: `tool_not_allowlisted: ${name} (allowed=${c.allowlist.join(",")})`,
    };
  }
  const tier = c.tiers[name] ?? 2;
  if (tier >= 3 && !approvalBridgeEnabled()) {
    return {
      ok: false,
      text: "",
      error:
        "l3_requires_approval: set AIPLAT_ENTERPRISE_APPROVAL=1 before L3 (write) tools",
    };
  }
  const url = toolExecuteUrl(c.coreBaseUrl, name);
  const body: Record<string, unknown> = {
    ...(params && typeof params === "object" ? params : {}),
  };
  // OpenWorker P1: inject attendance/session so PolicyGate can park Unattended Inbox.
  const att = attendanceInjectFields();
  const task = (
    process.env.AIPLAT_ENTERPRISE_TASK ||
    process.env.AIPLAT_USER_GOAL ||
    ""
  ).trim();
  if (task && (body._user_goal === undefined || body._user_goal === "")) {
    body._user_goal = task.slice(0, 400);
  }
  for (const [k, v] of Object.entries(att)) {
    if (body[k] === undefined || body[k] === null || body[k] === "") {
      body[k] = v;
    }
  }
  if (!body.user_id) {
    body.user_id = (process.env.AIPLAT_ACTOR_ID || "pi-enterprise").trim() || "pi-enterprise";
  }
  try {
    const res = await platformFetch(url, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${c.token}`,
      },
      body: JSON.stringify(body),
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
    const summary = summarizeToolResponse(name, parsed);
    const softFail =
      parsed &&
      typeof parsed === "object" &&
      (parsed as Record<string, unknown>).ok === false;
    return {
      ok: !softFail,
      status: res.status,
      text: summary,
      error: softFail ? "tool_ok_false" : undefined,
      raw: parsed,
    };
  } catch (e) {
    if (e instanceof CircuitOpenError) {
      return {
        ok: false,
        text: "",
        error: `circuit: ${e.message}`,
      };
    }
    return {
      ok: false,
      text: "",
      error: `network: ${e && (e as Error).message ? (e as Error).message : e}`,
    };
  }
}

function summarizeToolResponse(toolName: string, parsed: unknown): string {
  const parts = [`AIPLAT_TOOL_EXECUTE_OK tool=${toolName}`];
  if (!parsed || typeof parsed !== "object") {
    parts.push(String(parsed || "").slice(0, 3000));
    return parts.join("\n\n");
  }
  const o = parsed as Record<string, unknown>;
  if (o.ok === false) {
    parts[0] = `AIPLAT_TOOL_EXECUTE_FAILED tool=${toolName}`;
  }
  const approvalId = extractApprovalRequestId(parsed);
  const inboxId = extractInboxItemId(parsed);
  const st = String(o.status || o.legacy_status || "").toLowerCase();
  if (
    approvalId ||
    inboxId ||
    st === "approval_required" ||
    st === "waiting_approval"
  ) {
    parts[0] = `AIPLAT_TOOL_EXECUTE_APPROVAL_REQUIRED tool=${toolName}`;
    const hint = formatApprovalRequiredHint(approvalId, inboxId);
    if (hint) parts.push(hint);
  }
  if (typeof o.run_id === "string") parts.push(`run_id=${o.run_id}`);
  if (typeof o.status === "string") parts.push(`status=${o.status}`);
  const out = o.output !== undefined ? o.output : o.result !== undefined ? o.result : o;
  try {
    parts.push(JSON.stringify(out).slice(0, 4000));
  } catch {
    parts.push(String(out).slice(0, 4000));
  }
  return parts.join("\n\n");
}

export function toolProxyStatusLines(cfg?: ToolProxyConfig): string[] {
  const c = cfg || loadToolProxyConfig();
  const tierSummary = Object.entries(c.tiers || {})
    .map(([n, t]) => `${n}=L${t}`)
    .join(",") || "(empty)";
  return [
    "aiPlat enterprise tool proxy",
    `tools_enabled=${c.toolsEnabled}`,
    `reason_tools_off=${c.reasonToolsOff || "-"}`,
    `core_base=${c.coreBaseUrl || "(none)"}`,
    `tier_mode=${c.tierMode}`,
    `ceiling=L${c.ceiling}`,
    `allowlist=${c.allowlist.join(",") || "(empty)"}`,
    `tiers=${tierSummary}`,
    c.toolsEnabled ? "AIPLAT_ENTERPRISE_TOOLS_ON" : "AIPLAT_ENTERPRISE_TOOLS_OFF",
  ];
}

export function registerEnterpriseTools(pi: ExtensionAPI): boolean {
  const cfg = loadToolProxyConfig();
  if (!cfg.toolsEnabled) return false;

  const tool = defineTool({
    name: "aiplat_tool_execute",
    label: "aiPlat Tool Execute",
    description:
      "Execute an allowlisted aiPlat platform tool via HTTP (hybrid). Flat AIPLAT_ENTERPRISE_TOOLS or tiered L1/L2/L3 (ceiling). L3 needs approval bridge. Soft-fails if platform down.",
    parameters: Type.Object({
      tool_name: Type.String({
        description: "Registered tool name (must be allowlisted at or below TOOL_CEILING)",
      }),
      params_json: Type.Optional(
        Type.String({
          description: 'Tool input as JSON object string, e.g. {"operation":"read","path":"..."}',
        }),
      ),
    }),
    async execute(_toolCallId, params) {
      const name = String(params.tool_name || "");
      let p: Record<string, unknown> = {};
      const raw = String(params.params_json || "").trim();
      if (raw) {
        try {
          const parsed = JSON.parse(raw);
          if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
            p = parsed as Record<string, unknown>;
          } else {
            return {
              content: [
                {
                  type: "text" as const,
                  text: "AIPLAT_TOOL_EXECUTE_FAILED: params_json must be a JSON object",
                },
              ],
              isError: true,
            };
          }
        } catch (e) {
          return {
            content: [
              {
                type: "text" as const,
                text: `AIPLAT_TOOL_EXECUTE_FAILED: params_json parse error: ${
                  e && (e as Error).message ? (e as Error).message : e
                }`,
              },
            ],
            isError: true,
          };
        }
      }
      const r = await executeEnterpriseTool(name, p, cfg);
      if (!r.ok) {
        return {
          content: [
            {
              type: "text" as const,
              text: `AIPLAT_TOOL_EXECUTE_FAILED: ${r.error || "unknown"}\n${r.text || ""}`,
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
  });

  pi.registerTool(tool);
  return true;
}

export function toolProxySystemPromptAddon(cfg?: ToolProxyConfig): string {
  const c = cfg || loadToolProxyConfig();
  if (!c.toolsEnabled) return "";
  const tierHint =
    c.tierMode === "tiered"
      ? `tiers=L1(read)/L2(compute)/L3(write); ceiling=L${c.ceiling}; L3 requires approval bridge.`
      : "flat allowlist (legacy; treated as L2).";
  return [
    "",
    "## aiPlat Enterprise Tool Proxy",
    "Hybrid mode: use tool aiplat_tool_execute for allowlisted platform tools only.",
    `allowlist=${c.allowlist.join(", ")}`,
    tierHint,
    "If the tool fails, continue with package skills/handler — do not invent tool results.",
  ].join("\n");
}
