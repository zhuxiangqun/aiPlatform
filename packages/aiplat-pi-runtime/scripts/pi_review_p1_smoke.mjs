/**
 * Smoke for Pi review P1: skill path, approval outcomes, receipt markers.
 */
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { isNegativeApprovalOutcome } from "../extensions/approval_outcome.mjs";
import {
  allowHandlerEcho,
  handlerPyUnderRoot,
  safeSkillDirName,
} from "../extensions/skill_path.mjs";
import { receiptsFromMessages } from "../extensions/completion_receipt.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PKG = path.resolve(__dirname, "..");

assert.equal(safeSkillDirName("../etc"), "");
assert.equal(safeSkillDirName("/tmp/x"), "");
assert.equal(safeSkillDirName("fixture-skill"), "fixture-skill");
assert.equal(allowHandlerEcho("missing-skill"), false);
assert.equal(allowHandlerEcho("fixture-skill"), true);

const escaped = handlerPyUnderRoot(path.join(PKG, "skills"), "../fixtures");
assert.equal(escaped, "");

assert.equal(isNegativeApprovalOutcome("rejected", ""), true);
assert.equal(isNegativeApprovalOutcome("pending", "approved"), false);
assert.equal(isNegativeApprovalOutcome("resolved", "deny"), true);

const parked = receiptsFromMessages([
  {
    role: "toolResult",
    content: "AIPLAT_TOOL_EXECUTE_APPROVAL_REQUIRED tool=bash\nwaiting",
  },
]);
assert.equal(parked[0].status, "failed");

const denied = receiptsFromMessages([
  { role: "toolResult", content: "AIPLAT_APPROVAL_WAIT_DENIED\nstatus=rejected" },
]);
assert.equal(denied[0].status, "failed");

console.log("PASS: pi review P1 skill path / approval / receipt markers");
console.log("AIPLAT_PI_REVIEW_P1_SMOKE_OK");
