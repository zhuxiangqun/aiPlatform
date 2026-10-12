#!/usr/bin/env node
/**
 * Load aiplat-app.ts via jiti with a mock ExtensionAPI (no LLM).
 * Proves registerCommand / registerTool / before_agent_start wiring.
 */
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PKG = join(__dirname, "..");
const require = createRequire(import.meta.url);
const home = process.env.HOME || "";
const jitiRoot = join(
  home,
  ".npm-global/lib/node_modules/@earendil-works/pi-coding-agent/node_modules/jiti",
);

let createJiti;
try {
  const mod = require(jitiRoot);
  createJiti = mod.createJiti || mod;
} catch {
  try {
    const url = pathToFileURL(join(jitiRoot, "lib/jiti.mjs")).href;
    const mod = await import(url);
    createJiti = mod.createJiti;
  } catch (exc) {
    console.error("FAIL: cannot load jiti:", exc.message);
    process.exit(1);
  }
}

// Alias host packages for TypeScript imports inside the extension
const jiti = createJiti(import.meta.url, {
  interopDefault: true,
  alias: {
    "@earendil-works/pi-ai": join(
      home,
      ".npm-global/lib/node_modules/@earendil-works/pi-coding-agent/node_modules/@earendil-works/pi-ai",
    ),
    "@earendil-works/pi-coding-agent": join(
      home,
      ".npm-global/lib/node_modules/@earendil-works/pi-coding-agent",
    ),
  },
});

const factory = await jiti.import(join(PKG, "extensions/aiplat-app.ts"));

const cmds = new Map();
const tools = new Map();
const events = new Map();

const pi = {
  registerCommand(name, def) {
    cmds.set(name, def);
  },
  registerTool(tool) {
    const name = tool?.name || tool;
    tools.set(typeof name === "string" ? name : String(name), tool);
  },
  on(event, handler) {
    if (!events.has(event)) events.set(event, []);
    events.get(event).push(handler);
    return () => {};
  },
  sendUserMessage: async () => {},
  sendMessage: async () => {},
};

const fn = factory.default || factory;
await Promise.resolve(fn(pi));

const needCmds = ["aiplat-status", "aiplat-sop-check", "skill-test"];
const missingCmds = needCmds.filter((c) => !cmds.has(c));
if (missingCmds.length) {
  console.error("FAIL: missing commands", missingCmds);
  process.exit(1);
}
if (!tools.has("aiplat_handler")) {
  console.error("FAIL: missing tool aiplat_handler", [...tools.keys()]);
  process.exit(1);
}
if (!events.has("before_agent_start")) {
  console.error("FAIL: missing before_agent_start", [...events.keys()]);
  process.exit(1);
}

const handlers = events.get("before_agent_start");
const result = await handlers[0]();
if (!result?.systemPrompt || !result?.forceSystemPrompt) {
  console.error("FAIL: before_agent_start did not return forceSystemPrompt", result);
  process.exit(1);
}
if (!String(result.systemPrompt).includes("AIPLAT_SOP_INJECT_OK")) {
  console.error("FAIL: SOP marker missing in systemPrompt");
  process.exit(1);
}

const tool = tools.get("aiplat_handler");
const out = await tool.execute("tc1", { skill: "fixture", params_json: "{}" });
const blob = JSON.stringify(out);
if (!blob.includes("AIPLAT_HANDLER_ECHO_OK")) {
  console.error("FAIL: handler tool did not echo marker", out);
  process.exit(1);
}

console.log("PASS: Phase 0 mock ExtensionAPI");
console.log("  commands:", [...cmds.keys()].join(", "));
console.log("  tools:", [...tools.keys()].join(", "));
console.log("  events:", [...events.keys()].join(", "));
console.log("  systemPrompt force + SOP marker OK");
console.log("  aiplat_handler → AIPLAT_HANDLER_ECHO_OK");
