/**
 * Same contract as core/harness/execution/completion_receipt.py:
 * a fix/path claim without a successful tool receipt is prefixed, not trusted.
 */

const FIX_CLAIM =
  /(已经修好|已修好|已修复|修复完成|已经修复|bug\s*已修|fixed the bug|bug is fixed|successfully fixed)/i;
const PATH_CLAIM =
  /(?:文件(?:路径)?(?:是|在|位于)|path is|located at)\s*[`'"]?([/~][\w./-]{3,})/gi;

export function bindCompletionToReceipts(text, receipts) {
  const raw = String(text || "");
  const rows = Array.isArray(receipts) ? receipts : [];
  const okBlob = rows
    .filter((r) => r && r.status === "ok")
    .map((r) => String(r.detail || ""))
    .join("\n");
  const lastFailed = rows.length > 0 && rows[rows.length - 1].status !== "ok";
  if (FIX_CLAIM.test(raw) && (!rows.length || lastFailed || !okBlob)) {
    if (lastFailed) {
      const detail = String(rows[rows.length - 1].detail || "").trim();
      const head = detail
        ? `[失败] 最近一次工具回执失败，不能声明已修好。 回执：${detail.slice(0, 300)}`
        : "[失败] 最近一次工具回执失败，不能声明已修好。";
      return { text: `${head}\n${raw}`, status: "failed" };
    }
    return { text: `[未核验] 完成声明没有成功的工具回执。\n${raw}`, status: "unverified" };
  }
  const unsupported = [];
  PATH_CLAIM.lastIndex = 0;
  let m;
  while ((m = PATH_CLAIM.exec(raw))) {
    if (!okBlob.includes(m[1])) unsupported.push(m[1]);
  }
  if (unsupported.length) {
    return {
      text: `[未核验] 路径未经成功工具回执确认：${unsupported.slice(0, 3).join(", ")}\n${raw}`,
      status: "unverified",
    };
  }
  return { text: raw, status: "ok" };
}

/** Pull tool success/failure lines out of a Pi message list. */
export function receiptsFromMessages(messages) {
  const out = [];
  const arr = Array.isArray(messages) ? messages : [];
  for (const m of arr) {
    if (!m || typeof m !== "object") continue;
    const row = m;
    const chunks = [];
    if (typeof row.content === "string") chunks.push(row.content);
    if (Array.isArray(row.content)) {
      for (const p of row.content) {
        if (typeof p === "string") chunks.push(p);
        else if (p && typeof p.text === "string") chunks.push(p.text);
      }
    }
    if (typeof row.text === "string") chunks.push(row.text);
    const text = chunks.join("\n");
    if (!text.trim()) continue;
    const role = String(row.role || row.type || "").toLowerCase();
    if (!role.includes("tool")) continue;
    // Match Python infer_receipt_status: prefix / explicit markers only.
    // Do not treat grep-style "Pattern not found" as fail. Non-tool roles
    // never become receipts (role gate above). Explicit ok===false / status
    // failed count as fail even without isError.
    const head = text.trim().slice(0, 240).toLowerCase();
    const failed =
      row.isError === true ||
      row.ok === false ||
      String(row.status || "").toLowerCase() === "failed" ||
      head.startsWith("skill error:") ||
      head.startsWith("denied:") ||
      head.startsWith("error:") ||
      head.startsWith("traceback") ||
      head.startsWith("404") ||
      head.startsWith("file not found") ||
      head.startsWith("tool not found:") ||
      head.includes("policy_denied") ||
      head.includes("aiplat_tool_execute_failed");
    out.push({
      status: failed ? "failed" : "ok",
      detail: text.slice(0, 500),
    });
  }
  return out;
}
