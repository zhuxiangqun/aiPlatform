/**
 * Offline smoke: scan_pi_bundle_delivery + export embeds citation + checklist.
 */
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "../../..");
const SCAN = path.join(ROOT, "scripts/scan_pi_bundle_delivery.py");
const EXPORT = path.join(ROOT, "scripts/export_pi_bundle.py");
const SAMPLE = path.join(ROOT, "packages/aiplat-pi-runtime/fixtures/sample-app");

function assert(cond, msg) {
  if (!cond) {
    console.error("FAIL:", msg);
    process.exit(1);
  }
}

function run(cmd, args, opts = {}) {
  const r = spawnSync(cmd, args, {
    encoding: "utf8",
    cwd: ROOT,
    ...opts,
  });
  if (r.status !== 0) {
    console.error(r.stdout || "");
    console.error(r.stderr || "");
    process.exit(r.status || 1);
  }
  return r;
}

// 1) Scan sample-app (expect ok; may have warnings)
const scanJson = run("python3", [SCAN, "--root", SAMPLE]);
const summary = JSON.parse((scanJson.stdout || "").trim().split("\n").pop());
assert(typeof summary.ok === "boolean", "scan summary ok field");
assert(summary.scanned_files > 0, "scanned files > 0");
console.log("PASS: scan_pi_bundle_delivery on sample-app", summary);

// 2) Export must include citation module + checklist artifacts
const out = fs.mkdtempSync(path.join(os.tmpdir(), "aiplat-pi-export-"));
try {
  run("python3", [
    EXPORT,
    "--app-home",
    SAMPLE,
    "--out",
    out,
    "--project-id",
    "sample",
  ]);
  assert(
    fs.existsSync(path.join(out, "extensions/enterprise_kb_citation.ts")),
    "export includes enterprise_kb_citation.ts",
  );
  assert(
    fs.existsSync(path.join(out, "extensions/enterprise_http.ts")),
    "export includes enterprise_http.ts",
  );
  assert(
    fs.existsSync(path.join(out, "extensions/enterprise_kb.ts")),
    "export includes enterprise_kb.ts",
  );
  assert(fs.existsSync(path.join(out, "DELIVERY_CHECKLIST.md")), "DELIVERY_CHECKLIST.md");
  assert(fs.existsSync(path.join(out, "delivery_scan.json")), "delivery_scan.json");
  assert(fs.existsSync(path.join(out, "USAGE_BOUNDARY.md")), "USAGE_BOUNDARY.md");
  assert(fs.existsSync(path.join(out, "COST_REPORT.md")), "COST_REPORT.md");
  const costMd = fs.readFileSync(path.join(out, "COST_REPORT.md"), "utf8");
  assert(costMd.includes("成本页"), "cost report has 成本页 title");
  assert(
    costMd.includes("未配置单价") || costMd.includes("缓存"),
    "cost report mentions cache or pricing caveat",
  );
  assert(costMd.includes("流量占比"), "cost report has purpose traffic share section");
  assert(
    costMd.includes("完成调用") || costMd.includes("选择次数"),
    "cost report labels share as completion or selection counts",
  );
  assert(fs.existsSync(path.join(out, "KB_HEALTH.md")), "KB_HEALTH.md");
  const kbMd = fs.readFileSync(path.join(out, "KB_HEALTH.md"), "utf8");
  assert(kbMd.includes("知识库健康分"), "kb health title");
  assert(
    fs.existsSync(path.join(out, "extensions/enterprise_kb_health.ts")),
    "export includes enterprise_kb_health.ts",
  );
  assert(fs.existsSync(path.join(out, "MONTHLY_OPS_REPORT.md")), "MONTHLY_OPS_REPORT.md");
  const opsMd = fs.readFileSync(path.join(out, "MONTHLY_OPS_REPORT.md"), "utf8");
  assert(opsMd.includes("月度运行报告"), "monthly ops title");
  assert(opsMd.includes("存活") || opsMd.includes("托管"), "monthly ops has daemon section");
  assert(
    fs.existsSync(path.join(out, "extensions/enterprise_l3_duty.ts")),
    "export includes enterprise_l3_duty.ts",
  );
  assert(fs.existsSync(path.join(out, "L3_DUTY_DESK.md")), "L3_DUTY_DESK.md");
  const dutyMd = fs.readFileSync(path.join(out, "L3_DUTY_DESK.md"), "utf8");
  assert(dutyMd.includes("L3 专属值班台"), "l3 duty title");
  assert(dutyMd.includes("季度建议"), "l3 duty has quarterly tips");
  const checklist = fs.readFileSync(path.join(out, "DELIVERY_CHECKLIST.md"), "utf8");
  assert(checklist.includes("FDE / 交付负责人签收"), "checklist has FDE sign-off");
  const meta = JSON.parse(fs.readFileSync(path.join(out, "aiplat-export.json"), "utf8"));
  assert(meta.delivery_scan && typeof meta.delivery_scan.ok === "boolean", "meta.delivery_scan");
  assert(fs.existsSync(path.join(out, "BUNDLE_VERSION")), "BUNDLE_VERSION file");
  const bv = fs.readFileSync(path.join(out, "BUNDLE_VERSION"), "utf8").trim();
  assert(bv.length > 0, "BUNDLE_VERSION non-empty");
  assert(meta.bundle_version === bv, "meta.bundle_version matches BUNDLE_VERSION");
  assert(meta.build && meta.build.build_time, "meta.build.build_time");
  assert(
    typeof meta.build.git_sha === "string" || meta.build.git_sha === null,
    "meta.build.git_sha string|null",
  );
  console.log("PASS: export embeds citation + checklist + cost + kb-health + BUNDLE_VERSION");
} finally {
  fs.rmSync(out, { recursive: true, force: true });
}

console.log("AIPLAT_ENTERPRISE_DELIVERY_SCAN_SMOKE_OK");
