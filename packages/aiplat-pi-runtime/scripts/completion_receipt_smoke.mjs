import assert from "node:assert/strict";
import {
  bindCompletionToReceipts,
  receiptsFromMessages,
} from "../extensions/completion_receipt.mjs";

const none = bindCompletionToReceipts("已经修好了", []);
assert.equal(none.status, "unverified");
assert.ok(none.text.startsWith("[未核验]"));

const failed = bindCompletionToReceipts("已经修好了", [
  { status: "failed", detail: "Error: column missing" },
]);
assert.equal(failed.status, "failed");
assert.ok(failed.text.includes("column missing"));

const ok = bindCompletionToReceipts("已经修好了", [
  { status: "ok", detail: "tests passed" },
]);
assert.equal(ok.status, "ok");

const fromMsgs = receiptsFromMessages([
  { role: "toolResult", isError: true, content: "AIPLAT_TOOL_EXECUTE_FAILED: boom" },
  { role: "toolResult", content: [{ type: "text", text: "404 not found" }] },
  { role: "toolResult", content: "read /tmp/ok.py" },
]);
assert.equal(fromMsgs[0].status, "failed");
assert.equal(fromMsgs[1].status, "failed");
assert.equal(fromMsgs[2].status, "ok");

const benign = receiptsFromMessages([
  { role: "toolResult", content: "Pattern not found in src/" },
]);
assert.equal(benign[0].status, "ok");
console.log("completion_receipt_smoke ok");
