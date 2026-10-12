/**
 * aiPlat thin Runtime extension for Pi (Scheme A).
 *
 * - Skills: package / export `skills/` auto-discovered by Pi (no registerSkill)
 * - SOP: before_agent_start → systemPrompt + forceSystemPrompt
 * - Slash: /aiplat-status, /aiplat-sop-check, /skill-<name> from manifest or skills/
 * - Tool: aiplat_handler → Python JSON bridge (echo or skill handler.py via runner)
 */
import { spawn } from "node:child_process";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { Type } from "@earendil-works/pi-ai";
import { defineTool, type ExtensionAPI } from "@earendil-works/pi-coding-agent";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PKG_ROOT = resolve(__dirname, "..");
const HANDLER_ECHO = join(PKG_ROOT, "fixtures", "handler_echo.py");
const HANDLER_RUNNER = join(PKG_ROOT, "fixtures", "handler_runner.py");

const SOP_MARKER = "AIPLAT_SOP_INJECT_OK";
const DEFAULT_SOP = [
  "## aiPlat Runtime SOP (Phase 0)",
  "You are running inside the aiPlat thin Pi Runtime.",
  `When asked to confirm SOP injection, include the marker ${SOP_MARKER} in your reply.`,
  "Prefer package skills under skills/ and /skill-<name> commands.",
].join("\n");

type Manifest = {
  mode?: string;
  agents?: Array<{ name?: string; skills?: string[] }>;
  skill_routing?: Record<string, string>;
  ui_bindings?: Record<string, string>;
};

function findAppHome(): string | null {
  const env = (process.env.AIPLAT_APP_HOME || "").trim();
  if (env && existsSync(join(env, "agent_manifest.json"))) return resolve(env);
  const cwd = process.cwd();
  if (existsSync(join(cwd, "agent_manifest.json"))) return cwd;
  // Exported package itself may be AIPLAT_APP_HOME (manifest at package root)
  if (existsSync(join(PKG_ROOT, "agent_manifest.json"))) return PKG_ROOT;
  return null;
}

function loadManifest(appHome: string): Manifest | null {
  try {
    const raw = readFileSync(join(appHome, "agent_manifest.json"), "utf8");
    return JSON.parse(raw) as Manifest;
  } catch {
    return null;
  }
}

function loadAgentSop(appHome: string, agentName: string): string {
  const candidates = [
    join(appHome, "agents", agentName, "AGENT.md"),
    join(appHome, agentName, "AGENT.md"),
    join(appHome, "AGENT.md"),
  ];
  for (const p of candidates) {
    if (!existsSync(p)) continue;
    const text = readFileSync(p, "utf8");
    const sopIdx = text.search(/^##\s*(SOP|系统提示|System)\b/im);
    if (sopIdx >= 0) return text.slice(sopIdx).trim();
    if (text.startsWith("---")) {
      const end = text.indexOf("\n---", 3);
      if (end >= 0) return text.slice(end + 4).trim();
    }
    return text.trim();
  }
  return "";
}

function buildSystemPromptOverlay(appHome: string | null): string {
  if (!appHome) return DEFAULT_SOP;
  const manifest = loadManifest(appHome);
  const agentNames =
    manifest?.agents
      ?.map((a) => String(a.name || "").trim())
      .filter(Boolean) ?? [];
  const primary = agentNames[0] || "default";
  const sop = loadAgentSop(appHome, primary) || DEFAULT_SOP;
  const routing = manifest?.skill_routing
    ? Object.entries(manifest.skill_routing)
        .map(([sk, ag]) => `- ${sk} → ${ag}`)
        .join("\n")
    : "(none)";
  return [
    `## aiPlat App Runtime`,
    `app_home: ${appHome}`,
    `primary_agent: ${primary}`,
    `skill_routing:\n${routing}`,
    "",
    sop,
    "",
    `Injection marker: ${SOP_MARKER}`,
  ].join("\n");
}

function listSkillNames(appHome: string | null): string[] {
  const names = new Set<string>();
  const roots = [
    appHome ? join(appHome, "skills") : "",
    join(PKG_ROOT, "skills"),
  ].filter(Boolean);
  for (const root of roots) {
    if (!existsSync(root)) continue;
    for (const ent of readdirSync(root, { withFileTypes: true })) {
      if (!ent.isDirectory()) continue;
      if (existsSync(join(root, ent.name, "SKILL.md"))) names.add(ent.name);
    }
  }
  const manifest = appHome ? loadManifest(appHome) : null;
  if (manifest?.skill_routing) {
    for (const k of Object.keys(manifest.skill_routing)) names.add(k);
  }
  return [...names].sort();
}

function resolveHandlerPy(skill: string, appHome: string | null): string | null {
  const candidates = [
    appHome ? join(appHome, "skills", skill, "handler.py") : "",
    join(PKG_ROOT, "skills", skill, "handler.py"),
  ].filter(Boolean);
  for (const p of candidates) {
    if (existsSync(p)) return p;
  }
  return null;
}

function runPythonJson(
  args: string[],
  payload: Record<string, unknown>,
): Promise<{ ok: boolean; result?: unknown; error?: string; exitCode: number }> {
  return new Promise((resolvePromise) => {
    const child = spawn("python3", args, { stdio: ["pipe", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (b) => {
      stdout += String(b);
    });
    child.stderr.on("data", (b) => {
      stderr += String(b);
    });
    child.on("close", (code) => {
      try {
        const parsed = JSON.parse(stdout || "{}") as {
          ok?: boolean;
          result?: unknown;
          error?: string;
        };
        resolvePromise({
          ok: Boolean(parsed.ok) && code === 0,
          result: parsed.result,
          error: parsed.error || (code === 0 ? undefined : stderr || `exit ${code}`),
          exitCode: code ?? 1,
        });
      } catch (exc) {
        resolvePromise({
          ok: false,
          error: `bad_stdout: ${exc}; stderr=${stderr}`,
          exitCode: code ?? 1,
        });
      }
    });
    child.stdin.write(JSON.stringify(payload));
    child.stdin.end();
  });
}

async function runHandlerBridge(
  skill: string,
  params: Record<string, unknown>,
  appHome: string | null,
) {
  const handlerPy = resolveHandlerPy(skill, appHome);
  if (handlerPy && existsSync(HANDLER_RUNNER)) {
    return runPythonJson([HANDLER_RUNNER, handlerPy], { skill, params });
  }
  // Fallback: Phase 0 echo fixture
  return runPythonJson([HANDLER_ECHO], { skill, params });
}

const handlerTool = defineTool({
  name: "aiplat_handler",
  label: "aiPlat Handler",
  description:
    "Run aiPlat skill handler.py via JSON stdin/stdout bridge. Hard-fails on error (no LLM theater).",
  parameters: Type.Object({
    skill: Type.String({ description: "Skill name (directory under skills/)" }),
    params_json: Type.Optional(
      Type.String({ description: "JSON object string for params (default {})" }),
    ),
  }),
  async execute(_toolCallId, params) {
    let parsedParams: Record<string, unknown> = {};
    if (params.params_json) {
      try {
        const v = JSON.parse(params.params_json);
        if (v && typeof v === "object" && !Array.isArray(v)) {
          parsedParams = v as Record<string, unknown>;
        }
      } catch {
        return {
          content: [{ type: "text" as const, text: "invalid params_json" }],
          details: undefined,
          isError: true,
        };
      }
    }
    const appHome = findAppHome();
    const r = await runHandlerBridge(String(params.skill || ""), parsedParams, appHome);
    if (!r.ok) {
      return {
        content: [
          {
            type: "text" as const,
            text: `HANDLER_FAILED: ${r.error || "unknown"}`,
          },
        ],
        details: r,
        isError: true,
      };
    }
    return {
      content: [{ type: "text" as const, text: JSON.stringify(r.result, null, 2) }],
      details: r,
    };
  },
});

function safeCmdName(skill: string): string {
  return `skill-${skill.replace(/[^a-zA-Z0-9_-]/g, "-")}`;
}

export default function (pi: ExtensionAPI) {
  let appHome = findAppHome();
  let overlay = buildSystemPromptOverlay(appHome);

  pi.registerTool(handlerTool);

  pi.registerCommand("aiplat-status", {
    description: "Show aiPlat Pi Runtime status (app home, routing, markers)",
    handler: async (_args, ctx) => {
      appHome = findAppHome();
      overlay = buildSystemPromptOverlay(appHome);
      const manifest = appHome ? loadManifest(appHome) : null;
      const skills = listSkillNames(appHome);
      const lines = [
        "aiPlat Pi Runtime status",
        `PKG_ROOT=${PKG_ROOT}`,
        `AIPLAT_APP_HOME=${appHome || "(not set — using Phase 0 default SOP)"}`,
        `HANDLER_ECHO=${existsSync(HANDLER_ECHO) ? "ok" : "missing"}`,
        `HANDLER_RUNNER=${existsSync(HANDLER_RUNNER) ? "ok" : "missing"}`,
        `SOP_MARKER=${SOP_MARKER}`,
        `skills=${skills.join(",") || "-"}`,
        `skill_routing_keys=${manifest?.skill_routing ? Object.keys(manifest.skill_routing).join(",") : "-"}`,
        "Scheme A: package skills/ + /skill-<name> (no registerSkill)",
        "AIPLAT_STATUS_OK",
      ];
      const text = lines.join("\n");
      // print/json modes have no UI — console so `pi -p '/aiplat-status'` is visible
      console.log(text);
      try {
        ctx.ui.notify(text, "info");
      } catch {
        /* no UI in print mode */
      }
    },
  });

  pi.registerCommand("aiplat-sop-check", {
    description: "Ask the agent to confirm SOP injection marker",
    handler: async (_args, ctx) => {
      // In print mode, slash handlers that only queue may exit before the turn.
      // Prefer a direct user turn; also log for smoke greps.
      const prompt = `Confirm that the aiPlat Runtime SOP is active. Reply with the marker ${SOP_MARKER}.`;
      console.log(`AIPLAT_SOP_CHECK_QUEUED ${SOP_MARKER}`);
      await pi.sendUserMessage(prompt);
      try {
        ctx.ui.notify("Sent SOP check prompt", "info");
      } catch {
        /* no UI */
      }
    },
  });

  pi.registerCommand("skill-test", {
    description: "Phase 0: force-load fixture-skill",
    handler: async (_args, ctx) => {
      console.log("AIPLAT_SKILL_TEST_QUEUED fixture-skill");
      await pi.sendUserMessage(
        "Use skill fixture-skill now. Follow its instructions and include AIPLAT_FIXTURE_SKILL_OK.",
      );
      try {
        ctx.ui.notify("Queued fixture-skill prompt (also try /skill:fixture-skill)", "info");
      } catch {
        /* no UI */
      }
    },
  });

  // Dynamic /skill-<name> from manifest + skills dirs (Scheme A companion)
  for (const skill of listSkillNames(appHome)) {
    const cmd = safeCmdName(skill);
    pi.registerCommand(cmd, {
      description: `Trigger aiPlat skill '${skill}' (SOP/context nudge)`,
      handler: async (_args, ctx) => {
        const home = findAppHome();
        const skillMd = [
          home ? join(home, "skills", skill, "SKILL.md") : "",
          join(PKG_ROOT, "skills", skill, "SKILL.md"),
        ]
          .filter(Boolean)
          .find((p) => existsSync(p));
        let body = "";
        if (skillMd) {
          const text = readFileSync(skillMd, "utf8");
          body = text.length > 4000 ? `${text.slice(0, 4000)}\n…` : text;
        }
        const msg = [
          `Activate skill: ${skill}`,
          body ? `\n--- SKILL.md ---\n${body}\n---` : "",
          "Follow the skill instructions for this turn.",
        ].join("\n");
        console.log(`AIPLAT_SKILL_QUEUED ${skill}`);
        await pi.sendUserMessage(msg);
        try {
          ctx.ui.notify(`Queued skill ${skill}`, "info");
        } catch {
          /* no UI */
        }
      },
    });
  }

  pi.on("session_start", async () => {
    appHome = findAppHome();
    overlay = buildSystemPromptOverlay(appHome);
  });

  pi.on("before_agent_start", async () => {
    appHome = findAppHome();
    overlay = buildSystemPromptOverlay(appHome);
    return {
      systemPrompt: overlay,
      forceSystemPrompt: true,
    };
  });
}
