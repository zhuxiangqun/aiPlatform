/**
 * Factory-out enterprise native-tool gate.
 *
 * When AIPLAT_ENTERPRISE=1 (intent), block Pi built-in host-mutating tools
 * (bash/write/edit/…) unless explicitly allowlisted. Side effects must go through
 * aiplat_tool_execute (server PolicyGate). Pi-only (enterprise unset) is unchanged.
 *
 * Escape: AIPLAT_ENTERPRISE_ALLOW_NATIVE=1 → gate off (trusted operator).
 * Opt-out: AIPLAT_ENTERPRISE_TOOL_GATE=0 → gate off while keeping KB/tools hybrid.
 * Allowlist: AIPLAT_ENTERPRISE_NATIVE_ALLOWLIST=bash (overrides default block).
 * Blocklist: AIPLAT_ENTERPRISE_NATIVE_BLOCKLIST=read (extra blocks).
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

/** Built-ins that can mutate host / run shell — blocked by default in enterprise. */
export const DEFAULT_NATIVE_BLOCK = Object.freeze([
  "bash",
  "powershell",
  "write",
  "edit",
]);

/** Built-ins treated as read-only — allowed by default in enterprise. */
export const DEFAULT_NATIVE_ALLOW = Object.freeze([
  "read",
  "grep",
  "find",
  "ls",
]);

/** Always allowed (aiPlat extension tools + handler bridge). */
export const ALWAYS_ALLOW_PREFIXES = Object.freeze(["aiplat_"]);

export type ToolGateConfig = {
  enterpriseOn: boolean;
  gateOn: boolean;
  allowNativeAll: boolean;
  allowlist: string[];
  blocklist: string[];
  reasonOff: string;
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

function parseList(name: string): string[] {
  const raw = (process.env[name] || "").trim();
  if (!raw) return [];
  return raw
    .split(/[,;\s]+/)
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);
}

function uniq(xs: string[]): string[] {
  return [...new Set(xs)];
}

export function loadToolGateConfig(): ToolGateConfig {
  // Gate on enterprise *intent* (AIPLAT_ENTERPRISE=1), even if URL/token missing —
  // so misconfig cannot silently leave bash ungated.
  const enterpriseOn = envTruthy("AIPLAT_ENTERPRISE");
  if (!enterpriseOn) {
    return {
      enterpriseOn: false,
      gateOn: false,
      allowNativeAll: false,
      allowlist: [],
      blocklist: [],
      reasonOff: "AIPLAT_ENTERPRISE unset",
    };
  }
  if (envTruthy("AIPLAT_ENTERPRISE_ALLOW_NATIVE")) {
    return {
      enterpriseOn: true,
      gateOn: false,
      allowNativeAll: true,
      allowlist: [],
      blocklist: [],
      reasonOff: "AIPLAT_ENTERPRISE_ALLOW_NATIVE=1",
    };
  }
  if (envExplicitlyOff("AIPLAT_ENTERPRISE_TOOL_GATE")) {
    return {
      enterpriseOn: true,
      gateOn: false,
      allowNativeAll: false,
      allowlist: [],
      blocklist: [],
      reasonOff: "AIPLAT_ENTERPRISE_TOOL_GATE=0",
    };
  }

  const extraAllow = parseList("AIPLAT_ENTERPRISE_NATIVE_ALLOWLIST");
  const extraBlock = parseList("AIPLAT_ENTERPRISE_NATIVE_BLOCKLIST");
  // Explicit allowlist entries override default/extra block; explicit block overrides default allow.
  const blocklist = uniq([...DEFAULT_NATIVE_BLOCK, ...extraBlock]).filter(
    (t) => !extraAllow.includes(t),
  );
  const allowlist = uniq([...DEFAULT_NATIVE_ALLOW, ...extraAllow]).filter(
    (t) => !extraBlock.includes(t),
  );

  return {
    enterpriseOn: true,
    gateOn: true,
    allowNativeAll: false,
    allowlist,
    blocklist,
    reasonOff: "",
  };
}

export function isToolAllowedByGate(
  toolName: string,
  cfg?: ToolGateConfig,
): { allowed: boolean; reason: string } {
  const c = cfg || loadToolGateConfig();
  const name = String(toolName || "").trim();
  if (!name) return { allowed: false, reason: "empty tool name" };
  if (!c.gateOn) return { allowed: true, reason: c.reasonOff || "gate off" };

  const lower = name.toLowerCase();
  for (const p of ALWAYS_ALLOW_PREFIXES) {
    if (lower.startsWith(p)) {
      return { allowed: true, reason: "aiplat extension tool" };
    }
  }
  if (c.blocklist.includes(lower)) {
    return {
      allowed: false,
      reason:
        `native tool '${name}' blocked in enterprise mode; ` +
        `use aiplat_tool_execute (allowlisted) or set AIPLAT_ENTERPRISE_NATIVE_ALLOWLIST / ` +
        `AIPLAT_ENTERPRISE_ALLOW_NATIVE=1`,
    };
  }
  if (c.allowlist.includes(lower)) {
    return { allowed: true, reason: "native allowlist" };
  }
  // Unknown custom/MCP tools: block in enterprise (fail closed)
  return {
    allowed: false,
    reason:
      `tool '${name}' not on enterprise native allowlist; ` +
      `use aiplat_tool_execute or AIPLAT_ENTERPRISE_NATIVE_ALLOWLIST`,
  };
}

export function toolGateStatusLines(cfg?: ToolGateConfig): string[] {
  const c = cfg || loadToolGateConfig();
  return [
    "aiPlat enterprise native tool gate",
    `enterprise=${c.enterpriseOn ? "on" : "off"}`,
    `gate=${c.gateOn ? "on" : "off"}`,
    `reason_off=${c.reasonOff || "-"}`,
    `native_allow=${c.allowlist.join(",") || "-"}`,
    `native_block=${c.blocklist.join(",") || "-"}`,
    c.gateOn ? "AIPLAT_ENTERPRISE_TOOL_GATE_ON" : "AIPLAT_ENTERPRISE_TOOL_GATE_OFF",
  ];
}

export function toolGateSystemPromptAddon(cfg?: ToolGateConfig): string {
  const c = cfg || loadToolGateConfig();
  if (!c.gateOn) return "";
  return [
    "",
    "## aiPlat Enterprise Native Tool Gate",
    "Enterprise hybrid: host-mutating Pi tools (bash/write/edit/powershell) are BLOCKED.",
    "Use aiplat_tool_execute for allowlisted platform tools (PolicyGate on server).",
    `Allowed native (read-only by default): ${c.allowlist.join(", ") || "(none)"}`,
    `Blocked native: ${c.blocklist.join(", ") || "(none)"}`,
  ].join("\n");
}

/**
 * Register tool_call + user_bash blockers and shrink active tools when gate is on.
 * Returns true if gate is active.
 */
export function registerEnterpriseToolGate(pi: ExtensionAPI): boolean {
  const cfg = loadToolGateConfig();
  if (!cfg.gateOn) return false;

  pi.on("tool_call", async (event) => {
    const decision = isToolAllowedByGate(event.toolName, cfg);
    if (decision.allowed) return;
    console.warn(`AIPLAT_TOOL_GATE_BLOCK tool=${event.toolName} reason=${decision.reason}`);
    return {
      block: true,
      reason: decision.reason,
      terminate: false,
    };
  });

  // Interactive / user bash path (separate from model tool_call)
  pi.on("user_bash", async () => {
    const decision = isToolAllowedByGate("bash", cfg);
    if (decision.allowed) return;
    console.warn(`AIPLAT_TOOL_GATE_BLOCK user_bash reason=${decision.reason}`);
    return {
      result: {
        output: `AIPLAT_TOOL_GATE_BLOCKED: ${decision.reason}`,
        exitCode: 1,
      },
    };
  });

  const applyActiveSet = () => {
    try {
      const all = pi.getAllTools().map((t) => t.name);
      const next = all.filter((n) => isToolAllowedByGate(n, cfg).allowed);
      if (next.length) pi.setActiveTools(next);
      console.log(
        `AIPLAT_TOOL_GATE_ACTIVE tools=${next.join(",") || "(none)"} (from ${all.length} registered)`,
      );
    } catch (e) {
      console.warn(
        "AIPLAT_TOOL_GATE_SET_ACTIVE_FAILED",
        e && (e as Error).message ? (e as Error).message : e,
      );
    }
  };

  pi.on("session_start", async () => {
    applyActiveSet();
  });

  // Also apply after registration settles (session may already be live)
  queueMicrotask(applyActiveSet);

  return true;
}
