#!/usr/bin/env node
/**
 * Phase 2 thin HTTP (sync first):
 *   GET  /health
 *   POST /v1/chat            { session_id?, message }
 *   POST /v1/skills/:name    { session_id?, message?, params? }
 *
 * Without pi-ai credentials → stub mode (still injects SOP for offline smoke).
 * With AIPLAT_PI_MODEL=provider/model + API keys → real Agent via pi-agent-core.
 *
 * Auth: AIPLAT_HTTP_API_KEY → Authorization: Bearer <key>
 * Env: AIPLAT_HTTP_PORT (8787), AIPLAT_APP_HOME, AIPLAT_PI_MODEL, AIPLAT_HTTP_STUB=1|0
 */
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PKG = path.resolve(__dirname, "..");
const PORT = Number(process.env.AIPLAT_HTTP_PORT || 8787);
const API_KEY = (process.env.AIPLAT_HTTP_API_KEY || "").trim();
const FORCE_STUB = process.env.AIPLAT_HTTP_STUB === "1";

/** @type {Map<string, any>} */
const sessions = new Map();

function readJson(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => {
      try {
        resolve(JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}"));
      } catch (e) {
        reject(e);
      }
    });
    req.on("error", reject);
  });
}

function send(res, code, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(code, {
    "content-type": "application/json; charset=utf-8",
    "content-length": Buffer.byteLength(body),
  });
  res.end(body);
}

function checkAuth(req) {
  if (!API_KEY) return true;
  return (req.headers.authorization || "") === `Bearer ${API_KEY}`;
}

function appHome() {
  const env = (process.env.AIPLAT_APP_HOME || "").trim();
  if (env && fs.existsSync(path.join(env, "agent_manifest.json"))) return path.resolve(env);
  const sample = path.join(PKG, "fixtures", "sample-app");
  if (fs.existsSync(path.join(sample, "agent_manifest.json"))) return sample;
  return PKG;
}

function loadSop(home) {
  const manifestPath = path.join(home, "agent_manifest.json");
  if (!fs.existsSync(manifestPath)) {
    return {
      appHome: home,
      systemPrompt: "You are a helpful assistant (aiPlat thin HTTP).",
      manifest: null,
      marker: "AIPLAT_SOP_INJECT_OK",
    };
  }
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  const agentName =
    (manifest.agents && manifest.agents[0] && manifest.agents[0].name) || "agent";
  const agentMd = path.join(home, "agents", agentName, "AGENT.md");
  let sop = "";
  if (fs.existsSync(agentMd)) {
    const text = fs.readFileSync(agentMd, "utf8");
    const end = text.startsWith("---") ? text.indexOf("\n---", 3) : -1;
    sop = end > 0 ? text.slice(end + 4).trim() : text.trim();
  }
  return {
    appHome: home,
    manifest,
    marker: "AIPLAT_SOP_INJECT_OK",
    systemPrompt: [
      "## aiPlat App Runtime (HTTP)",
      `app_home: ${home}`,
      `primary_agent: ${agentName}`,
      "",
      sop || "(no SOP)",
      "",
      "Injection marker: AIPLAT_SOP_INJECT_OK",
    ].join("\n"),
  };
}

function loadSkillMd(home, skill) {
  const p = path.join(home, "skills", skill, "SKILL.md");
  if (!fs.existsSync(p)) return null;
  const text = fs.readFileSync(p, "utf8");
  return text.length > 6000 ? `${text.slice(0, 6000)}\n…` : text;
}

function runHandler(home, skill, params) {
  return new Promise((resolvePromise) => {
    const handlerPy = path.join(home, "skills", skill, "handler.py");
    const runner = path.join(PKG, "fixtures", "handler_runner.py");
    const echo = path.join(PKG, "fixtures", "handler_echo.py");
    const args =
      fs.existsSync(handlerPy) && fs.existsSync(runner)
        ? [runner, handlerPy]
        : [echo];
    const child = spawn("python3", args, { stdio: ["pipe", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (b) => (stdout += String(b)));
    child.stderr.on("data", (b) => (stderr += String(b)));
    child.on("close", (code) => {
      try {
        const parsed = JSON.parse(stdout || "{}");
        resolvePromise({
          ok: Boolean(parsed.ok) && code === 0,
          result: parsed.result,
          error: parsed.error || (code === 0 ? undefined : stderr || `exit ${code}`),
          via: fs.existsSync(handlerPy) ? "handler.py" : "echo",
        });
      } catch (e) {
        resolvePromise({ ok: false, error: `bad_stdout: ${e}; ${stderr}` });
      }
    });
    child.stdin.write(JSON.stringify({ skill, params: params || {} }));
    child.stdin.end();
  });
}

async function ensureAgent(sessionId, meta) {
  if (sessions.has(sessionId)) return sessions.get(sessionId);

  if (!FORCE_STUB) {
    try {
      const { Agent } = await import("@earendil-works/pi-agent-core");
      const ai = await import("@earendil-works/pi-ai");
      const models = typeof ai.createModels === "function" ? ai.createModels() : null;
      const modelId = process.env.AIPLAT_PI_MODEL || "";
      let model = null;
      if (models && modelId && typeof models.getModel === "function") {
        const [provider, name] = modelId.includes("/")
          ? modelId.split("/", 2)
          : ["openai", modelId];
        try {
          model = models.getModel(provider, name);
        } catch {
          model = null;
        }
      }
      if (model && Agent && models?.streamSimple) {
        const agent = new Agent({
          initialState: { systemPrompt: meta.systemPrompt, model },
          streamFn: models.streamSimple.bind(models),
        });
        const entry = { kind: "agent", agent, systemPrompt: meta.systemPrompt };
        sessions.set(sessionId, entry);
        return entry;
      }
    } catch {
      // fall through to stub
    }
  }

  const stub = {
    kind: "stub",
    systemPrompt: meta.systemPrompt,
    async prompt(text) {
      return {
        text: [
          "[stub-mode] no LLM credentials / AIPLAT_HTTP_STUB=1",
          `marker=${meta.marker}`,
          `prompt=${text.slice(0, 200)}`,
          meta.systemPrompt.includes(meta.marker)
            ? "sop_injected=true"
            : "sop_injected=false",
        ].join("\n"),
        mode: "stub",
      };
    },
  };
  sessions.set(sessionId, stub);
  return stub;
}

async function runPrompt(session, text) {
  if (session.kind === "stub") return session.prompt(text);
  const agent = session.agent;
  let out = "";
  const unsub = agent.subscribe((event) => {
    if (
      event.type === "message_update" &&
      event.assistantMessageEvent?.type === "text_delta"
    ) {
      out += event.assistantMessageEvent.delta || "";
    }
  });
  await agent.prompt(text);
  if (typeof unsub === "function") unsub();
  return { text: out || "(empty)", mode: "agent" };
}

const home = appHome();
const meta = loadSop(home);

const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url || "/", `http://127.0.0.1:${PORT}`);

    // Health is unauthenticated for probes / smoke
    if (req.method === "GET" && url.pathname === "/health") {
      return send(res, 200, {
        ok: true,
        appHome: meta.appHome,
        sessions: sessions.size,
        auth: Boolean(API_KEY),
        stub: FORCE_STUB || !process.env.AIPLAT_PI_MODEL,
      });
    }

    if (!checkAuth(req)) return send(res, 401, { ok: false, error: "unauthorized" });

    if (req.method === "POST" && url.pathname === "/v1/chat") {
      const body = await readJson(req);
      const sessionId = String(body.session_id || randomUUID());
      const message = String(body.message || body.prompt || "").trim();
      if (!message) return send(res, 400, { ok: false, error: "message required" });
      const session = await ensureAgent(sessionId, meta);
      const result = await runPrompt(session, message);
      return send(res, 200, { ok: true, session_id: sessionId, ...result });
    }

    const skillMatch = url.pathname.match(/^\/v1\/skills\/([^/]+)$/);
    if (req.method === "POST" && skillMatch) {
      const skill = decodeURIComponent(skillMatch[1]);
      const body = await readJson(req);
      const sessionId = String(body.session_id || randomUUID());
      const params =
        body.params && typeof body.params === "object" && !Array.isArray(body.params)
          ? body.params
          : {};

      // Deterministic path: if handler.py exists, call bridge (no LLM theater)
      const handlerPy = path.join(meta.appHome, "skills", skill, "handler.py");
      if (fs.existsSync(handlerPy) || body.force_handler) {
        const hr = await runHandler(meta.appHome, skill, params);
        if (!hr.ok) {
          return send(res, 500, {
            ok: false,
            error: `HANDLER_FAILED: ${hr.error || "unknown"}`,
            skill,
          });
        }
        return send(res, 200, {
          ok: true,
          session_id: sessionId,
          skill,
          mode: "handler",
          result: hr.result,
          via: hr.via,
        });
      }

      const skillBody = loadSkillMd(meta.appHome, skill);
      const message = [
        `Activate skill: ${skill}`,
        skillBody ? `\n--- SKILL.md ---\n${skillBody}\n---` : "",
        String(body.message || "Follow the skill instructions.").trim(),
      ].join("\n");
      const session = await ensureAgent(sessionId, meta);
      const result = await runPrompt(session, message);
      return send(res, 200, { ok: true, session_id: sessionId, skill, ...result });
    }

    send(res, 404, { ok: false, error: "not found" });
  } catch (e) {
    send(res, 500, { ok: false, error: String(e && e.stack ? e.stack : e) });
  }
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(
    `[aiplat-http] http://127.0.0.1:${PORT} appHome=${meta.appHome} auth=${API_KEY ? "on" : "off"} stub=${FORCE_STUB ? "force" : "auto"}`,
  );
});
