/**
 * Five-products MB-05: emit slice evidence events to JSONL (opt-in).
 *
 * Enable with AIPLAT_SLICE_EVIDENCE=1 (or set AIPLAT_SLICE_EVIDENCE_PATH).
 * Default path: $AIPLAT_HOME/five_products_slice/evidence_emit/<run_id>.jsonl
 * Does nothing when disabled — no change to production default thin path.
 */
import { appendFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { homedir } from "node:os";
import { randomBytes } from "node:crypto";

function enabled() {
  const flag = String(process.env.AIPLAT_SLICE_EVIDENCE || "").trim();
  if (flag === "1" || flag.toLowerCase() === "true" || flag.toLowerCase() === "yes") {
    return true;
  }
  return Boolean(String(process.env.AIPLAT_SLICE_EVIDENCE_PATH || "").trim());
}

function aiplatHome() {
  const env = String(process.env.AIPLAT_HOME || "").trim();
  return env || join(homedir(), ".aiplat");
}

function newRunId() {
  const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d+Z$/, "Z");
  return `pi-emit-${stamp}-${randomBytes(3).toString("hex")}`;
}

function resolvePath(runId) {
  const explicit = String(process.env.AIPLAT_SLICE_EVIDENCE_PATH || "").trim();
  if (explicit) return explicit;
  return join(aiplatHome(), "five_products_slice", "evidence_emit", `${runId}.jsonl`);
}

function append(path, obj) {
  mkdirSync(dirname(path), { recursive: true });
  appendFileSync(path, `${JSON.stringify(obj)}\n`, "utf8");
}

/**
 * @param {import("@earendil-works/pi-coding-agent").ExtensionAPI} pi
 * @returns {boolean} whether emitter registered
 */
export function registerSliceEvidenceEmit(pi) {
  if (!enabled()) return false;

  const runId = String(process.env.AIPLAT_SLICE_RUN_ID || "").trim() || newRunId();
  const path = resolvePath(runId);
  const bundleVersion = String(process.env.AIPLAT_SLICE_BUNDLE_VERSION || "").trim();
  const scenarioId = String(process.env.AIPLAT_SLICE_SCENARIO_ID || "").trim();
  const runtimeVersion = String(process.env.AIPLAT_SLICE_RUNTIME_VERSION || "pi-thin-emit").trim();

  const base = {
    v: 1,
    run_id: runId,
    scenario_id: scenarioId || undefined,
    bundle_version: bundleVersion || undefined,
    runtime_version: runtimeVersion,
  };

  append(path, {
    ...base,
    type: "emit_open",
    ts: new Date().toISOString(),
    source: "slice_evidence_emit",
  });
  console.log(`AIPLAT_SLICE_EVIDENCE_EMIT path=${path} run_id=${runId}`);

  const on = (type) => async () => {
    append(path, { ...base, type, ts: new Date().toISOString() });
  };

  pi.on("session_start", on("session_start"));
  pi.on("before_agent_start", on("before_agent_start"));
  try {
    pi.on("agent_end", on("agent_end"));
  } catch {
    /* optional event */
  }
  try {
    pi.on("session_shutdown", on("session_shutdown"));
  } catch {
    /* optional event */
  }

  return true;
}

export default registerSliceEvidenceEmit;
