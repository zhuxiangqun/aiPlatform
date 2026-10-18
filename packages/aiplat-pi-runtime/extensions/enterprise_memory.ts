/**
 * Factory-out hybrid: session summary writeback → aiPlat Memory (IDE capture API).
 *
 * Opt-in: AIPLAT_ENTERPRISE=1 + URL/token + AIPLAT_ENTERPRISE_MEMORY=1.
 * Soft-fails if platform down — never blocks the local Pi session.
 * Does not reimplement MemoryManager/SECI; posts to POST /platform/memory/capture.
 *
 * Auto: on session_shutdown flush last turn (disable with AIPLAT_ENTERPRISE_MEMORY_AUTO=0).
 * Explicit: tool aiplat_memory_capture + /aiplat-memory.
 */
import { Type } from "@earendil-works/pi-ai";
import { defineTool, type ExtensionAPI } from "@earendil-works/pi-coding-agent";

import { parseArchiveHits } from "./archive_hits.mjs";
import { bindCompletionToReceipts, receiptsFromMessages } from "./completion_receipt.mjs";
import { CircuitOpenError, platformFetch } from "./enterprise_http";
import {
  loadEnterpriseConfig,
  type EnterpriseConfig,
} from "./enterprise_kb";

export type MemoryBridgeConfig = EnterpriseConfig & {
  memoryEnabled: boolean;
  autoCapture: boolean;
  reasonMemoryOff: string;
  sessionId: string;
};

function envTruthy(name: string): boolean {
  const v = (process.env[name] || "").trim().toLowerCase();
  return v === "1" || v === "true" || v === "yes" || v === "on";
}

function envExplicitlyOff(name: string): boolean {
  const raw = (process.env[name] || "").trim();
  if (!raw) return false;
  const v = raw.toLowerCase();
  return v === "0" || v === "false" || v === "no" || v === "off";
}

/** Build POST …/platform/memory/capture from AIPLAT_PLATFORM_URL. */
export function memoryCaptureUrl(baseUrl: string): string {
  const b = String(baseUrl || "").trim().replace(/\/+$/, "");
  if (!b) return "";
  if (b.endsWith("/platform/memory/capture")) return b;
  if (b.endsWith("/platform")) return `${b}/memory/capture`;
  return `${b}/platform/memory/capture`;
}

/** GET …/platform/memory/archive — past turns, on demand. */
export function memoryArchiveUrl(baseUrl: string): string {
  const sticky = memoryStickyUrl(baseUrl);
  if (!sticky) return "";
  if (sticky.endsWith("/sticky")) return `${sticky.slice(0, -"/sticky".length)}/archive`;
  return `${sticky}/archive`;
}

/** GET …/platform/memory/sticky — pinned facts for the next session. */
export function memoryStickyUrl(baseUrl: string): string {
  const capture = memoryCaptureUrl(baseUrl);
  if (!capture) return "";
  if (capture.endsWith("/capture")) return `${capture.slice(0, -"/capture".length)}/sticky`;
  return `${capture}/sticky`;
}

let stickyCache = "";
let stickyLoaded = false;

export function resetStickyMemoryCache(): void {
  stickyCache = "";
  stickyLoaded = false;
}

/** Fetch sticky facts. Cached until the next session_start. Soft-fails to empty. */
export async function ensureStickyMemory(cfg?: MemoryBridgeConfig): Promise<string> {
  if (stickyLoaded) return stickyCache;
  const c = cfg || loadMemoryBridgeConfig();
  if (!c.memoryEnabled) {
    stickyLoaded = true;
    stickyCache = "";
    return "";
  }
  const url = memoryStickyUrl(c.baseUrl);
  if (!url) {
    stickyLoaded = true;
    return "";
  }
  try {
    const res = await platformFetch(url, {
      method: "GET",
      headers: { authorization: `Bearer ${c.token}` },
    });
    const bodyText = await res.text();
    if (!res.ok) {
      stickyLoaded = true;
      stickyCache = "";
      return "";
    }
    let text = "";
    try {
      const parsed = JSON.parse(bodyText) as { text?: string; available?: boolean };
      if (parsed && parsed.available !== false) text = String(parsed.text || "").trim();
    } catch {
      text = "";
    }
    stickyCache = text.slice(0, 2000);
  } catch {
    stickyCache = "";
  }
  stickyLoaded = true;
  return stickyCache;
}

/** POST a durable fact onto MEMORY.md. Commands and one-shot notes are refused by the platform. */
export async function pinStickyFact(
  content: string,
  cfg?: MemoryBridgeConfig,
  opts?: { key?: string; oldText?: string },
): Promise<MemoryCaptureResult> {
  const c = cfg || loadMemoryBridgeConfig();
  if (!c.memoryEnabled) {
    return { ok: false, text: "", error: `memory_off: ${c.reasonMemoryOff}` };
  }
  const body = String(content || "").trim();
  if (!body) return { ok: false, text: "", error: "content_required" };
  const url = memoryStickyUrl(c.baseUrl);
  if (!url) return { ok: false, text: "", error: "sticky_url_missing" };
  try {
    const res = await platformFetch(url, {
      method: "POST",
      headers: {
        authorization: `Bearer ${c.token}`,
        "content-type": "application/json",
      },
      body: JSON.stringify({
        content: body,
        key: String(opts?.key || "preference"),
        source: "pi",
        old_text: String(opts?.oldText || ""),
      }),
    });
    const bodyText = await res.text();
    if (!res.ok) {
      return { ok: false, status: res.status, text: bodyText.slice(0, 500), error: "sticky_http" };
    }
    let ok = true;
    try {
      const parsed = JSON.parse(bodyText) as { ok?: boolean; status?: string };
      if (parsed.ok === false || parsed.status === "error") ok = false;
    } catch {
      ok = false;
    }
    if (!ok) return { ok: false, status: res.status, text: bodyText.slice(0, 500), error: "sticky_refused" };
    resetStickyMemoryCache();
    return { ok: true, status: res.status, text: "Pinned fact saved." };
  } catch (err) {
    const message = err instanceof Error ? err.message : "sticky_failed";
    return { ok: false, text: "", error: message };
  }
}

/** On-demand past-turn search. Does not write memory and does not cache. */
export async function searchSessionArchive(
  query: string,
  cfg?: MemoryBridgeConfig,
  limit = 3,
): Promise<MemoryCaptureResult> {
  const c = cfg || loadMemoryBridgeConfig();
  if (!c.memoryEnabled) {
    return { ok: false, text: "", error: `memory_off: ${c.reasonMemoryOff}` };
  }
  const q = String(query || "").trim();
  if (!q) return { ok: false, text: "", error: "query_required" };
  const base = memoryArchiveUrl(c.baseUrl);
  if (!base) return { ok: false, text: "", error: "archive_url_missing" };
  const url = `${base}?q=${encodeURIComponent(q)}&limit=${Math.max(1, Math.min(limit, 8))}`;
  try {
    const res = await platformFetch(url, {
      method: "GET",
      headers: { authorization: `Bearer ${c.token}` },
    });
    const bodyText = await res.text();
    if (!res.ok) {
      return { ok: false, status: res.status, text: bodyText.slice(0, 500), error: "archive_http" };
    }
    const parsedHits = parseArchiveHits(bodyText);
    if (!parsedHits.ok) {
      return {
        ok: false,
        status: res.status,
        text: bodyText.slice(0, 500),
        error: parsedHits.error || "archive_parse",
      };
    }
    const hits = parsedHits.hits as Array<{ at?: string; role?: string; text?: string }>;
    if (!hits.length) return { ok: true, status: res.status, text: "No archived turns matched." };
    const lines = hits.map((h) => `- [${h.at || ""}] ${h.role || ""}: ${h.text || ""}`);
    return { ok: true, status: res.status, text: lines.join("\n") };
  } catch (err) {
    const message = err instanceof Error ? err.message : "archive_failed";
    return { ok: false, text: "", error: message };
  }
}

export function loadMemoryBridgeConfig(cfg?: EnterpriseConfig): MemoryBridgeConfig {
  const c = cfg || loadEnterpriseConfig();
  const sessionId = (
    process.env.AIPLAT_ENTERPRISE_SESSION_ID ||
    process.env.AIPLAT_SESSION_ID ||
    ""
  ).trim();
  if (!c.enabled) {
    return {
      ...c,
      memoryEnabled: false,
      autoCapture: false,
      reasonMemoryOff: c.reasonOff || "enterprise off",
      sessionId,
    };
  }
  if (!envTruthy("AIPLAT_ENTERPRISE_MEMORY")) {
    return {
      ...c,
      memoryEnabled: false,
      autoCapture: false,
      reasonMemoryOff: "AIPLAT_ENTERPRISE_MEMORY unset",
      sessionId,
    };
  }
  const autoCapture = !envExplicitlyOff("AIPLAT_ENTERPRISE_MEMORY_AUTO");
  return {
    ...c,
    memoryEnabled: true,
    autoCapture,
    reasonMemoryOff: "",
    sessionId,
  };
}

export type MemoryCaptureResult = {
  ok: boolean;
  status?: number;
  text: string;
  error?: string;
  raw?: unknown;
};

export type MemoryCapturePayload = {
  prompt: string;
  result?: string;
  tools?: string[];
  success?: boolean;
  tags?: string[];
  session_id?: string;
  write_wiki?: boolean;
};

export async function captureMemory(
  payload: MemoryCapturePayload,
  cfg?: MemoryBridgeConfig,
): Promise<MemoryCaptureResult> {
  const c = cfg || loadMemoryBridgeConfig();
  if (!c.memoryEnabled) {
    return { ok: false, text: "", error: `memory_off: ${c.reasonMemoryOff}` };
  }
  const prompt = String(payload.prompt || "").trim();
  const result = String(payload.result || "").trim();
  if (!prompt && !result) {
    return { ok: false, text: "", error: "prompt_or_result_required" };
  }

  const url = memoryCaptureUrl(c.baseUrl);
  const body = {
    prompt: prompt || result.slice(0, 200),
    result,
    tools: Array.isArray(payload.tools) ? payload.tools : undefined,
    success: payload.success !== false,
    tags: Array.isArray(payload.tags) ? payload.tags : ["pi_runtime", "hybrid"],
    source: "pi_runtime",
    session_id: String(payload.session_id || c.sessionId || "").trim(),
    write_wiki: Boolean(payload.write_wiki),
  };

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
    return {
      ok: true,
      status: res.status,
      text: `AIPLAT_MEMORY_CAPTURE_OK\n${bodyText.slice(0, 1500)}`,
      raw: parsed,
    };
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

function extractTextFromMessage(m: Record<string, unknown>): string {
  if (typeof m.content === "string") return m.content;
  if (Array.isArray(m.content)) {
    const parts: string[] = [];
    for (const p of m.content) {
      if (typeof p === "string") parts.push(p);
      else if (p && typeof p === "object") {
        const row = p as Record<string, unknown>;
        if (typeof row.text === "string") parts.push(row.text);
        else if (typeof row.content === "string") parts.push(row.content);
      }
    }
    return parts.join("\n");
  }
  if (typeof m.text === "string") return m.text;
  return "";
}

/** Best-effort last user + assistant text from agent_end messages. */
export function extractTurnSummary(messages: unknown[]): { prompt: string; result: string } {
  let prompt = "";
  let result = "";
  const arr = Array.isArray(messages) ? messages : [];
  for (const m of arr) {
    if (!m || typeof m !== "object") continue;
    const row = m as Record<string, unknown>;
    const role = String(row.role || row.type || "").toLowerCase();
    const text = extractTextFromMessage(row).trim();
    if (!text) continue;
    if (role.includes("user")) prompt = text;
    if (role.includes("assistant")) result = text;
  }
  return {
    prompt: prompt.slice(0, 4000),
    result: result.slice(0, 8000),
  };
}

export function memoryStatusLines(cfg?: MemoryBridgeConfig): string[] {
  const c = cfg || loadMemoryBridgeConfig();
  return [
    "aiPlat enterprise memory writeback (hybrid)",
    `memory_enabled=${c.memoryEnabled}`,
    `auto_capture=${c.autoCapture}`,
    `reason_off=${c.reasonMemoryOff || "-"}`,
    `session_id=${c.sessionId || "(none)"}`,
    `capture_url=${memoryCaptureUrl(c.baseUrl) || "(none)"}`,
    c.memoryEnabled ? "AIPLAT_ENTERPRISE_MEMORY_ON" : "AIPLAT_ENTERPRISE_MEMORY_OFF",
  ];
}

export function memorySystemPromptAddon(cfg?: MemoryBridgeConfig): string {
  const c = cfg || loadMemoryBridgeConfig();
  if (!c.memoryEnabled) return "";
  const lines = [
    "",
    "## aiPlat Enterprise Memory",
    "Durable facts that should hold next session: tool aiplat_memory_pin (a statement, not a command).",
    "This session's summary: tool aiplat_memory_capture. Do not pin one-shot steps, TODOs, or shell commands.",
    "Before the session ends: pin each stable preference/env fact; capture the episode summary; leave reusable procedures for skills.",
    "Pinned lines below (if any) are durable facts for every session.",
    "Past process is not in this prompt. Call aiplat_session_search when the user asks how something was done before.",
    "Failures are soft — continue local work; do not invent confirmations of platform storage.",
  ];
  if (stickyCache) {
    lines.push("", stickyCache);
  }
  return lines.join("\n");
}

type BufferedTurn = { prompt: string; result: string; success: boolean; seal: string };

export function registerEnterpriseMemory(pi: ExtensionAPI): boolean {
  const cfg = loadMemoryBridgeConfig();
  if (!cfg.memoryEnabled) return false;

  let buffered: BufferedTurn = { prompt: "", result: "", success: true, seal: "ok" };
  let flushed = false;

  const tool = defineTool({
    name: "aiplat_memory_capture",
    label: "aiPlat Memory Capture",
    description:
      "Write a session/turn summary to aiPlat platform Memory (hybrid). Soft-fails if platform down.",
    parameters: Type.Object({
      prompt: Type.String({ description: "User ask / title for the episode" }),
      result: Type.Optional(Type.String({ description: "Assistant summary or outcome" })),
      tags: Type.Optional(Type.Array(Type.String())),
      write_wiki: Type.Optional(Type.Boolean()),
    }),
    async execute(_toolCallId, params) {
      const r = await captureMemory(
        {
          prompt: String(params.prompt || ""),
          result: String(params.result || ""),
          tags: Array.isArray(params.tags) ? params.tags.map(String) : undefined,
          write_wiki: Boolean(params.write_wiki),
        },
        cfg,
      );
      if (!r.ok) {
        return {
          content: [
            {
              type: "text" as const,
              text: `AIPLAT_MEMORY_CAPTURE_FAILED: ${r.error || "unknown"}\n${r.text || ""}`,
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

  pi.registerTool(
    defineTool({
      name: "aiplat_memory_pin",
      label: "aiPlat Pin Fact",
      description:
        "Save a durable fact for every future session (preference or stable environment). Refuses commands and one-shot notes.",
      parameters: Type.Object({
        content: Type.String({ description: "Full fact statement, e.g. 用户偏好简洁回复" }),
        key: Type.Optional(Type.String({ description: "preference or env" })),
        old_text: Type.Optional(Type.String({ description: "Substring of the fact to replace" })),
      }),
      async execute(_toolCallId, params) {
        const r = await pinStickyFact(String(params.content || ""), cfg, {
          key: params.key ? String(params.key) : undefined,
          oldText: params.old_text ? String(params.old_text) : undefined,
        });
        if (!r.ok) {
          return {
            content: [
              {
                type: "text" as const,
                text: `AIPLAT_MEMORY_PIN_FAILED: ${r.error || "unknown"}`,
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
      name: "aiplat_session_search",
      label: "aiPlat Session Search",
      description:
        "Search archived past turns on aiPlat (how something was done before). Not for durable preferences.",
      parameters: Type.Object({
        query: Type.String({ description: "What past process to look up" }),
        limit: Type.Optional(Type.Number({ description: "Max hits, 1-8" })),
      }),
      async execute(_toolCallId, params) {
        const r = await searchSessionArchive(
          String(params.query || ""),
          cfg,
          Number(params.limit || 3),
        );
        if (!r.ok) {
          return {
            content: [
              {
                type: "text" as const,
                text: `AIPLAT_SESSION_SEARCH_FAILED: ${r.error || "unknown"}`,
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

  pi.on("session_start", async () => {
    try {
      resetStickyMemoryCache();
      await ensureStickyMemory(loadMemoryBridgeConfig());
    } catch {
      /* soft */
    }
  });

  pi.registerCommand("aiplat-memory", {
    description: "Show memory writeback status (hybrid)",
    handler: async (_args, ctx) => {
      const lines = memoryStatusLines(loadMemoryBridgeConfig());
      const text = lines.join("\n");
      console.log(text);
      try {
        ctx.ui.notify(text, "info");
      } catch {
        /* no UI */
      }
    },
  });

  pi.on("agent_end", async (event: { messages?: unknown[] }) => {
    try {
      const messages = event?.messages || [];
      const turn = extractTurnSummary(messages);
      const bound = bindCompletionToReceipts(turn.result, receiptsFromMessages(messages));
      turn.result = bound.text;
      if (turn.prompt || turn.result) {
        buffered = {
          prompt: turn.prompt,
          result: turn.result,
          success: bound.status === "ok",
          seal: bound.status,
        };
      }
    } catch {
      /* never block */
    }
  });

  pi.on("session_shutdown", async () => {
    const live = loadMemoryBridgeConfig();
    if (!live.memoryEnabled || !live.autoCapture || flushed) return;
    if (!buffered.prompt && !buffered.result) return;
    flushed = true;
    try {
      const r = await captureMemory(
        {
          prompt: buffered.prompt || "pi_session",
          result: buffered.result,
          success: buffered.success,
          tags: ["pi_runtime", "hybrid", "session_shutdown", `completion_${buffered.seal}`],
        },
        live,
      );
      if (r.ok) console.log("AIPLAT_MEMORY_AUTO_FLUSH_OK");
      else console.log(`AIPLAT_MEMORY_AUTO_FLUSH_SOFT_FAIL ${r.error || ""}`);
    } catch (e) {
      console.log(
        `AIPLAT_MEMORY_AUTO_FLUSH_SOFT_FAIL ${e && (e as Error).message ? (e as Error).message : e}`,
      );
    }
  });

  return true;
}
