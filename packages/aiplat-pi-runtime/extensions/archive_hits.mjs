/**
 * Parse GET /platform/memory/archive body.
 * Invalid JSON is a failure. A JSON object with no hits is an empty result.
 */

export function parseArchiveHits(bodyText) {
  let parsed;
  try {
    parsed = JSON.parse(String(bodyText || ""));
  } catch {
    return { ok: false, error: "archive_parse", hits: [] };
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    return { ok: false, error: "archive_parse", hits: [] };
  }
  const hits = Array.isArray(parsed.hits) ? parsed.hits : [];
  return { ok: true, error: "", hits };
}
