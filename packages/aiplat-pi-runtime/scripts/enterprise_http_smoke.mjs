/**
 * Smoke: AIPLAT_PLATFORM_BASE_PATH + platform circuit breaker (enterprise_http.ts).
 * Prefers --experimental-strip-types import; falls back to inlined mirror if unavailable.
 */
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const HTTP_TS = path.join(__dirname, "../extensions/enterprise_http.ts");

function assert(cond, msg) {
  if (!cond) {
    console.error("FAIL:", msg);
    process.exit(1);
  }
}

function runWithStripTypes() {
  const code = `
import {
  normalizePlatformBaseUrl,
  getPlatformCircuit,
  resetPlatformCircuits,
  platformFetch,
  CircuitOpenError,
} from ${JSON.stringify(HTTP_TS)};

function assert(c, m) { if (!c) throw new Error(m); }

delete process.env.AIPLAT_PLATFORM_BASE_PATH;
assert(normalizePlatformBaseUrl("http://127.0.0.1:8003") === "http://127.0.0.1:8003", "bare 8003");
assert(normalizePlatformBaseUrl("http://127.0.0.1:8003/api") === "http://127.0.0.1:8003", "8003/api strip");
assert(normalizePlatformBaseUrl("http://127.0.0.1:8000") === "http://127.0.0.1:8000/api", "8000 → /api");

process.env.AIPLAT_PLATFORM_BASE_PATH = "/api";
assert(
  normalizePlatformBaseUrl("http://custom.example:9000") === "http://custom.example:9000/api",
  "BASE_PATH stamps bare host",
);
assert(
  normalizePlatformBaseUrl("http://custom.example:9000/api") === "http://custom.example:9000/api",
  "BASE_PATH keeps existing path",
);
delete process.env.AIPLAT_PLATFORM_BASE_PATH;

resetPlatformCircuits();
process.env.AIPLAT_PLATFORM_CIRCUIT_FAILURES = "2";
process.env.AIPLAT_PLATFORM_CIRCUIT_COOLDOWN_MS = "60000";
delete process.env.AIPLAT_PLATFORM_CIRCUIT;

const url = "http://127.0.0.1:9/platform/kb/query"; // refused connection
for (let i = 0; i < 2; i++) {
  try {
    await platformFetch(url, { method: "GET", signal: AbortSignal.timeout(200) });
    throw new Error("expected network failure");
  } catch (e) {
    if (e instanceof CircuitOpenError) throw e;
  }
}
let opened = false;
try {
  await platformFetch(url, { method: "GET", signal: AbortSignal.timeout(200) });
} catch (e) {
  opened = e instanceof CircuitOpenError;
}
assert(opened, "circuit opens after threshold failures");
const snap = getPlatformCircuit(url).snapshot();
assert(snap.state === "open", "state open");

process.env.AIPLAT_PLATFORM_CIRCUIT = "0";
resetPlatformCircuits();
// with circuit off, allow() always true even after failures
const c = getPlatformCircuit(url);
c.recordFailure();
c.recordFailure();
c.recordFailure();
assert(c.allow() === true, "circuit disabled → allow");
delete process.env.AIPLAT_PLATFORM_CIRCUIT;
delete process.env.AIPLAT_PLATFORM_CIRCUIT_FAILURES;
delete process.env.AIPLAT_PLATFORM_CIRCUIT_COOLDOWN_MS;
resetPlatformCircuits();

console.log("PASS: enterprise_http BASE_PATH + circuit (strip-types)");
console.log("AIPLAT_ENTERPRISE_HTTP_SMOKE_OK");
`;
  const r = spawnSync(
    process.execPath,
    ["--experimental-strip-types", "--input-type=module", "-e", code],
    { encoding: "utf8" },
  );
  return r;
}

const r = runWithStripTypes();
if (r.status === 0) {
  process.stdout.write(r.stdout || "");
  process.exit(0);
}

console.error("strip-types path failed; stderr:", r.stderr || r.stdout || "");
console.error("FAIL: enterprise_http_smoke requires Node --experimental-strip-types");
process.exit(r.status || 1);
