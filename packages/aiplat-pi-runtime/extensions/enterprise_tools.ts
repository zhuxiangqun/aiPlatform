/**
 * Factory-out hybrid (enterprise): allowlisted tool execute via aiPlat core HTTP.
 *
 * Requires AIPLAT_ENTERPRISE=1 + URL/token (same gate as KB) **and**
 * AIPLAT_ENTERPRISE_TOOLS=comma-separated allowlist (empty → tools off).
 * Soft-fails if platform unreachable. RBAC / PolicyGate stay on the server.
 */
import { Type } from "@earendil-works/pi-ai";
import { defineTool, type ExtensionAPI } from "@earendil-works/pi-coding-agent";

import {
  extractApprovalRequestId,
  formatApprovalRequiredHint,
} from "./enterprise_approval";
import { CircuitOpenError, platformFetch } from "./enterprise_http";
import {
  loadEnterpriseConfig,
  type EnterpriseConfig,
} from "./enterprise_kb";

export type ToolProxyConfig = EnterpriseConfig & {
  toolsEnabled: boolean;
  allowlist: string[];
  coreBaseUrl: string;
  reasonToolsOff: string;
};

function parseAllowlist(): string[] {
  const raw = (process.env.AIPLAT_ENTERPRISE_TOOLS || "").trim();
  if (!raw) return [];
  return raw
    .split(/[,;\s]+/)
    .map((s) => s.trim())
    .filter(Boolean);
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
  const allowlist = parseAllowlist();
  const coreBaseUrl = resolveCoreBaseUrl(c.baseUrl);
  if (!c.enabled) {
    return {
      ...c,
      toolsEnabled: false,
      allowlist,
      coreBaseUrl,
      reasonToolsOff: c.reasonOff || "enterprise off",
    };
  }
  if (!allowlist.length) {
    return {
      ...c,
      toolsEnabled: false,
      allowlist,
      coreBaseUrl,
      reasonToolsOff: "AIPLAT_ENTERPRISE_TOOLS empty (allowlist required)",
    };
  }
  if (!coreBaseUrl) {
    return {
      ...c,
      toolsEnabled: false,
      allowlist,
      coreBaseUrl,
      reasonToolsOff: "AIPLAT_CORE_URL / core base unresolved",
    };
  }
  return {
    ...c,
    toolsEnabled: true,
    allowlist,
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
    return {
      ok: false,
      text: "",
      error: `tool_not_allowlisted: ${name} (allowed=${c.allowlist.join(",")})`,
    };
  }
  const url = toolExecuteUrl(c.coreBaseUrl, name);
  const body: Record<string, unknown> = {
    ...(params && typeof params === "object" ? params : {}),
  };
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
  const st = String(o.status || o.legacy_status || "").toLowerCase();
  if (approvalId || st === "approval_required" || st === "waiting_approval") {
    parts[0] = `AIPLAT_TOOL_EXECUTE_APPROVAL_REQUIRED tool=${toolName}`;
    const hint = formatApprovalRequiredHint(approvalId);
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
  return [
    "aiPlat enterprise tool proxy",
    `tools_enabled=${c.toolsEnabled}`,
    `reason_tools_off=${c.reasonToolsOff || "-"}`,
    `core_base=${c.coreBaseUrl || "(none)"}`,
    `allowlist=${c.allowlist.join(",") || "(empty)"}`,
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
      "Execute an allowlisted aiPlat platform tool via HTTP (hybrid). Only tools in AIPLAT_ENTERPRISE_TOOLS. Soft-fails if platform down.",
    parameters: Type.Object({
      tool_name: Type.String({ description: "Registered tool name (must be allowlisted)" }),
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
  return [
    "",
    "## aiPlat Enterprise Tool Proxy",
    "Hybrid mode: use tool aiplat_tool_execute for allowlisted platform tools only.",
    `allowlist=${c.allowlist.join(", ")}`,
    "If the tool fails, continue with package skills/handler — do not invent tool results.",
  ].join("\n");
}
