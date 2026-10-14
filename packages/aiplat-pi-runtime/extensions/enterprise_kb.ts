/**
 * Factory-out hybrid (enterprise): read-only KB retrieve via aiPlat platform HTTP.
 *
 * Gated by AIPLAT_ENTERPRISE=1 + AIPLAT_PLATFORM_URL (+ token).
 * Off by default → Pi-only. Soft-fails if platform unreachable.
 * PolicyGate stays on the platform (kb:read scope); this client only forwards identity.
 */
import { Type } from "@earendil-works/pi-ai";
import { defineTool, type ExtensionAPI } from "@earendil-works/pi-coding-agent";
import {
  citationSystemPromptLines,
  envCitationEnabled,
  formatKbCitationResponse,
} from "./enterprise_kb_citation";

export type EnterpriseConfig = {
  enabled: boolean;
  baseUrl: string;
  token: string;
  collectionId: string;
  reasonOff: string;
};

function envTruthy(name: string): boolean {
  const v = (process.env[name] || "").trim().toLowerCase();
  return v === "1" || v === "true" || v === "yes" || v === "on";
}

/**
 * Normalize AIPLAT_PLATFORM_URL so joining `/platform/*` hits the real mount.
 *
 * Verified local layout:
 * - Platform (:8003) serves `/platform/...` (NOT `/api/platform/...`)
 * - Management GW (:8000) serves `/api/platform/...` → proxies to platform
 * - Footgun: `http://host:8003/api` + `/platform/...` → `/api/platform/...` → 404
 */
export function normalizePlatformBaseUrl(raw: string): string {
  const b = String(raw || "").trim().replace(/\/+$/, "");
  if (!b) return "";
  try {
    const u = new URL(b);
    const path = (u.pathname || "/").replace(/\/+$/, "") || "/";
    // Direct platform with mistaken /api prefix → strip so /platform/* joins cleanly
    if (u.port === "8003" && (path === "/api" || path.startsWith("/api/"))) {
      if (path === "/api") {
        u.pathname = "/";
      } else if (path.startsWith("/api/platform")) {
        u.pathname = path.slice("/api".length) || "/";
      } else {
        u.pathname = path.slice("/api".length) || "/";
      }
      return u.toString().replace(/\/+$/, "");
    }
    // Management origin without /api → add gateway prefix
    if (u.port === "8000" && path === "/") {
      u.pathname = "/api";
      return u.toString().replace(/\/+$/, "");
    }
  } catch {
    /* keep raw */
  }
  return b;
}

export function loadEnterpriseConfig(): EnterpriseConfig {
  const baseUrl = normalizePlatformBaseUrl(
    (process.env.AIPLAT_PLATFORM_URL || "").trim(),
  );
  const token = (
    process.env.AIPLAT_TENANT_TOKEN ||
    process.env.AIPLAT_API_KEY ||
    ""
  ).trim();
  const collectionId = (process.env.AIPLAT_KB_COLLECTION_ID || "default").trim() || "default";
  if (!envTruthy("AIPLAT_ENTERPRISE")) {
    return {
      enabled: false,
      baseUrl,
      token,
      collectionId,
      reasonOff: "AIPLAT_ENTERPRISE unset",
    };
  }
  if (!baseUrl) {
    return {
      enabled: false,
      baseUrl,
      token,
      collectionId,
      reasonOff: "AIPLAT_PLATFORM_URL unset",
    };
  }
  if (!token) {
    return {
      enabled: false,
      baseUrl,
      token,
      collectionId,
      reasonOff: "AIPLAT_TENANT_TOKEN / AIPLAT_API_KEY unset",
    };
  }
  return {
    enabled: true,
    baseUrl,
    token,
    collectionId,
    reasonOff: "",
  };
}

export type KbRetrieveResult = {
  ok: boolean;
  status?: number;
  text: string;
  error?: string;
  raw?: unknown;
};

/** Build POST …/platform/kb/query from AIPLAT_PLATFORM_URL (with or without /api). */
export function kbQueryUrl(baseUrl: string): string {
  const b = String(baseUrl || "").trim().replace(/\/+$/, "");
  if (!b) return "";
  if (b.endsWith("/platform/kb/query")) return b;
  if (b.endsWith("/platform")) return `${b}/kb/query`;
  return `${b}/platform/kb/query`;
}

/** POST /platform/kb/query (base may already include /api for management gateway). */
export async function retrieveKb(
  question: string,
  cfg?: EnterpriseConfig,
): Promise<KbRetrieveResult> {
  const c = cfg || loadEnterpriseConfig();
  if (!c.enabled) {
    return { ok: false, text: "", error: `enterprise_off: ${c.reasonOff}` };
  }
  const q = String(question || "").trim();
  if (!q) return { ok: false, text: "", error: "question required" };

  const url = kbQueryUrl(c.baseUrl);
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${c.token}`,
      },
      body: JSON.stringify({
        question: q,
        collection_id: c.collectionId,
        limit: 8,
      }),
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
    const summary = formatKbCitationResponse(parsed, {
      citation: envCitationEnabled(true),
    });
    return { ok: true, status: res.status, text: summary, raw: parsed };
  } catch (e) {
    return {
      ok: false,
      text: `知识库暂不可用（${e && (e as Error).message ? (e as Error).message : e}）。请勿编造引用；可改用包内 skills/SOP。`,
      error: `network: ${e && (e as Error).message ? (e as Error).message : e}`,
    };
  }
}

export function enterpriseStatusLines(cfg?: EnterpriseConfig): string[] {
  const c = cfg || loadEnterpriseConfig();
  return [
    "aiPlat enterprise reconnect (hybrid)",
    `enabled=${c.enabled}`,
    `reason_off=${c.reasonOff || "-"}`,
    `platform_url=${c.baseUrl || "(none)"}`,
    `token=${c.token ? "set" : "missing"}`,
    `collection_id=${c.collectionId}`,
    "capability=kb_retrieve_readonly",
    c.enabled ? "AIPLAT_ENTERPRISE_ON" : "AIPLAT_ENTERPRISE_OFF",
  ];
}

export function registerEnterpriseKb(pi: ExtensionAPI): boolean {
  const cfg = loadEnterpriseConfig();
  if (!cfg.enabled) return false;

  const tool = defineTool({
    name: "aiplat_kb_retrieve",
    label: "aiPlat KB Retrieve",
    description:
      "Read-only retrieve from aiPlat platform knowledge base (hybrid reconnect). Use for tenant docs; fails soft if platform down.",
    parameters: Type.Object({
      question: Type.String({ description: "Natural-language question for KB retrieve" }),
    }),
    async execute(_toolCallId, params) {
      const r = await retrieveKb(String(params.question || ""), cfg);
      if (!r.ok) {
        return {
          content: [
            {
              type: "text" as const,
              text: `AIPLAT_KB_RETRIEVE_FAILED: ${r.error || "unknown"}\n${r.text || ""}`,
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

  pi.registerCommand("aiplat-enterprise", {
    description: "Show hybrid enterprise reconnect status (KB readonly)",
    handler: async (_args, ctx) => {
      const lines = enterpriseStatusLines(loadEnterpriseConfig());
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

export function enterpriseSystemPromptAddon(cfg?: EnterpriseConfig): string {
  const c = cfg || loadEnterpriseConfig();
  if (!c.enabled) return "";
  const lines = [
    "",
    "## aiPlat Enterprise Reconnect",
    "Hybrid mode: use tool aiplat_kb_retrieve for platform knowledge (read-only).",
    "If the tool fails or marks 知识库暂不可用, continue with package skills/SOP only — do not invent citations.",
    `platform=${c.baseUrl} collection=${c.collectionId}`,
  ];
  if (envCitationEnabled(true)) {
    lines.push(...citationSystemPromptLines());
  }
  return lines.join("\n");
}
