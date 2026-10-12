#!/usr/bin/env node
/**
 * Phase 0 hard gate (offline + optional live).
 * Does not require LLM keys for structural checks 1–5 (API surface).
 *
 * Usage: node packages/aiplat-pi-runtime/scripts/phase0_verify.mjs
 */
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PKG = path.resolve(__dirname, "..");
const require = createRequire(import.meta.url);

const results = [];

function pass(id, detail) {
  results.push({ id, ok: true, detail });
  console.log(`PASS [${id}] ${detail}`);
}
function fail(id, detail) {
  results.push({ id, ok: false, detail });
  console.error(`FAIL [${id}] ${detail}`);
}

// 1. Skills directory present for auto-discover (Scheme A)
{
  const skill = path.join(PKG, "skills", "fixture-skill", "SKILL.md");
  if (fs.existsSync(skill) && fs.readFileSync(skill, "utf8").includes("fixture-skill")) {
    pass("skills-layout", `skills/fixture-skill/SKILL.md present (${skill})`);
  } else {
    fail("skills-layout", "missing skills/fixture-skill/SKILL.md");
  }
}

// 2. Extension source declares before_agent_start systemPrompt injection
{
  const ext = fs.readFileSync(path.join(PKG, "extensions", "aiplat-app.ts"), "utf8");
  if (
    ext.includes('pi.on("before_agent_start"') &&
    ext.includes("systemPrompt") &&
    ext.includes("forceSystemPrompt")
  ) {
    pass(
      "systemPrompt-inject",
      "extension uses before_agent_start → systemPrompt + forceSystemPrompt (Pi docs contract)",
    );
  } else {
    fail("systemPrompt-inject", "extension missing before_agent_start systemPrompt return");
  }
}

// 3. registerCommand present
{
  const ext = fs.readFileSync(path.join(PKG, "extensions", "aiplat-app.ts"), "utf8");
  if (ext.includes('registerCommand("skill-test"') && ext.includes('registerCommand("aiplat-status"')) {
    pass("registerCommand", "skill-test + aiplat-status registered");
  } else {
    fail("registerCommand", "missing registerCommand registrations");
  }
}

// 4. registerTool + Python subprocess bridge
{
  const echo = path.join(PKG, "fixtures", "handler_echo.py");
  const r = spawnSync("python3", [echo], {
    input: JSON.stringify({ skill: "fixture", params: { a: 1 } }),
    encoding: "utf8",
  });
  let parsed = null;
  try {
    parsed = JSON.parse((r.stdout || "").trim());
  } catch {
    parsed = null;
  }
  if (
    r.status === 0 &&
    parsed?.ok &&
    parsed?.result?.marker === "AIPLAT_HANDLER_ECHO_OK"
  ) {
    pass("handler-bridge", "handler_echo.py JSON protocol OK");
  } else {
    fail(
      "handler-bridge",
      `echo failed status=${r.status} stdout=${r.stdout} stderr=${r.stderr}`,
    );
  }
  const ext = fs.readFileSync(path.join(PKG, "extensions", "aiplat-app.ts"), "utf8");
  if (ext.includes('name: "aiplat_handler"') && ext.includes("registerTool")) {
    pass("registerTool", "aiplat_handler tool registered in extension");
  } else {
    fail("registerTool", "aiplat_handler missing");
  }
}

// 5. package.json pi manifest + installable layout
{
  const pkg = JSON.parse(fs.readFileSync(path.join(PKG, "package.json"), "utf8"));
  if (
    pkg.pi?.extensions?.length &&
    pkg.pi?.skills?.length &&
    (pkg.keywords || []).includes("pi-package")
  ) {
    pass("pi-package-manifest", `pi.extensions=${JSON.stringify(pkg.pi.extensions)}`);
  } else {
    fail("pi-package-manifest", "package.json missing pi.extensions/skills or pi-package keyword");
  }
}

// Optional: resolve peer modules if installed
{
  const peers = [
    "@earendil-works/pi-coding-agent",
    "@earendil-works/pi-agent-core",
    "@earendil-works/pi-ai",
  ];
  let found = 0;
  for (const p of peers) {
    try {
      require.resolve(p);
      found += 1;
    } catch {
      try {
        require.resolve(p, { paths: [PKG, process.cwd()] });
        found += 1;
      } catch {
        /* not installed */
      }
    }
  }
  if (found === peers.length) {
    pass("peers-installed", "all pi peer packages resolvable");
  } else {
    pass(
      "peers-installed",
      `optional: ${found}/${peers.length} peers resolvable (install pi CLI to complete live install test)`,
    );
  }
}

// Sample app + export script smoke
{
  const sample = path.join(PKG, "fixtures", "sample-app", "agent_manifest.json");
  if (fs.existsSync(sample)) {
    pass("sample-app", "fixtures/sample-app present");
  } else {
    fail("sample-app", "missing sample-app");
  }
  const exp = path.join(PKG, "..", "..", "scripts", "export_pi_bundle.py");
  // PKG is packages/aiplat-pi-runtime → workspace scripts
  const exp2 = path.resolve(PKG, "../../scripts/export_pi_bundle.py");
  if (fs.existsSync(exp2)) {
    const out = path.join(PKG, "..", "..", "dist", "aiplat-app-phase0-verify");
    const r = spawnSync(
      "python3",
      [exp2, "--app-home", path.join(PKG, "fixtures", "sample-app"), "--out", out],
      { encoding: "utf8" },
    );
    if (r.status === 0 && fs.existsSync(path.join(out, "package.json"))) {
      pass("export-script", `export_pi_bundle → ${out}`);
    } else {
      fail("export-script", r.stderr || r.stdout || `status ${r.status}`);
    }
  } else {
    fail("export-script", `missing ${exp2}`);
  }
}

const failed = results.filter((r) => !r.ok);
const report = {
  generated_at: new Date().toISOString(),
  conclusions: {
    skills_scheme: "A",
    systemPrompt_inject: "before_agent_start.systemPrompt + forceSystemPrompt",
    registerCommand: true,
    registerTool: true,
    note:
      "Live `pi install` + model round-trip requires Node 22.19+ and installed @earendil-works/pi-coding-agent; structural gate above is mandatory.",
  },
  results,
};
fs.writeFileSync(
  path.join(PKG, "PHASE0_RESULTS.md"),
  `# Phase 0 results\n\n\`\`\`json\n${JSON.stringify(report, null, 2)}\n\`\`\`\n`,
  "utf8",
);

console.log(`\nSummary: ${results.length - failed.length}/${results.length} passed`);
process.exit(failed.length ? 1 : 0);
