/**
 * HTTP JSON object bodies for Pi enterprise calls.
 * Non-JSON (HTML gateway, truncated body) is a failure, not an empty payload.
 */

export function parseJsonObject(bodyText) {
  let parsed;
  try {
    parsed = JSON.parse(String(bodyText ?? ""));
  } catch {
    return { ok: false, error: "json_parse", value: null };
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    return { ok: false, error: "json_parse", value: null };
  }
  return { ok: true, error: "", value: parsed };
}

/** 2xx requires a JSON object. Other statuses stay HTTP failures. */
export function httpJsonObject(status, bodyText) {
  const code = Number(status) || 0;
  const parsed = parseJsonObject(bodyText);
  if (code < 200 || code >= 300) {
    return {
      ok: false,
      error: `http_${code}`,
      value: parsed.ok ? parsed.value : null,
    };
  }
  if (!parsed.ok) return { ok: false, error: "json_parse", value: null };
  return { ok: true, error: "", value: parsed.value };
}
