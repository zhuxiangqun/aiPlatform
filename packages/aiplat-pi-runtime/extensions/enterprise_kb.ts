/**
 * Factory-out hybrid (enterprise): read-only KB retrieve via aiPlat platform HTTP.
 *
 * Gated by AIPLAT_ENTERPRISE=1 + AIPLAT_PLATFORM_URL (+ token).
 * Off by default → Pi-only. Soft-fails if platform unreachable.
 * PolicyGate stays on the platform (kb:read scope); this client only forwards identity.
 */
import { Type } from "@earendil-works/pi-ai";
import { defineTool, type ExtensionAPI } from "@earendil-works/pi-coding-agent";

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

export function loadEnterpriseConfig(): EnterpriseConfig {
  const baseUrl = (process.env.AIPLAT_PLATFORM_URL || "").trim().replace(/\/+$/, "");
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
    const summary = summarizeKbResponse(parsed);
    return { ok: true, status: res.status, text: summary, raw: parsed };
  } catch (e) {
    return {
      ok: false,
      text: "",
      error: `network: ${e && (e as Error).message ? (e as Error).message : e}`,
    };
  }
}

function summarizeKbResponse(parsed: unknown): string {
  if (!parsed || typeof parsed !== "object") return String(parsed || "");
  const o = parsed as Record<string, unknown>;
  const kb = o.kb && typeof o.kb === "object" ? (o.kb as Record<string, unknown>) : null;
  const parts: string[] = ["AIPLAT_KB_RETRIEVE_OK"];
  if (typeof o.answer === "string" && o.answer.trim()) {
    parts.push(o.answer.trim().slice(0, 4000));
  }
  const items = (kb && Array.isArray(kb.items) ? kb.items : null) ||
    (Array.isArray(o.items) ? o.items : null) ||
    (Array.isArray(o.citations) ? o.citations : null);
  if (items) {
    for (const it of items.slice(0, 5)) {
      if (!it || typeof it !== "object") continue;
      const row = it as Record<string, unknown>;
      const t = String(row.text || row.content || row.snippet || "").trim();
      const src = String(row.doc_id || row.source || "").trim();
      if (t) parts.push(src ? `[${src}] ${t.slice(0, 500)}` : t.slice(0, 500));
    }
  }
  if (parts.length === 1) {
    parts.push(JSON.stringify(parsed).slice(0, 3000));
  }
  return parts.join("\n\n");
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
  return [
    "",
    "## aiPlat Enterprise Reconnect",
    "Hybrid mode: use tool aiplat_kb_retrieve for platform knowledge (read-only).",
    "If the tool fails, continue with package skills/SOP only — do not invent citations.",
    `platform=${c.baseUrl} collection=${c.collectionId}`,
  ].join("\n");
}
