/** Terminal approval outcomes that must not be reported as a successful wait. */
const NEGATIVE = new Set([
  "rejected",
  "denied",
  "deny",
  "expired",
  "cancelled",
  "canceled",
]);

export function isNegativeApprovalOutcome(status, decision) {
  const st = String(status || "").trim().toLowerCase();
  const dec = String(decision || "").trim().toLowerCase();
  return NEGATIVE.has(st) || NEGATIVE.has(dec);
}
