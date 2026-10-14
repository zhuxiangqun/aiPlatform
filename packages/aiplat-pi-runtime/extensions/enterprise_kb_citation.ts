/**
 * KB citation formatting for hybrid enterprise (HYBRID_ENTERPRISE_DELIVERY §3).
 * Pure helpers — no Pi SDK imports (smoke can load via --experimental-strip-types).
 *
 * P0: V2 empty prefix, V3a Markdown references, V6 max 5 sources.
 * P1 enhancements: low-confidence threshold (§3.4), source deduplication.
 */

export const KB_EMPTY_PREFIX = "未在知识库中找到相关内容";
export const MAX_KB_SOURCES = 5;
export const MAX_SNIPPET_CHARS = 200;
export const LOW_CONFIDENCE_THRESHOLD = 0.5;

export type KbSourceItem = {
  source: string;
  text: string;
  score: number;
};

export function envCitationEnabled(defaultOn = true): boolean {
  const raw = (process.env.AIPLAT_ENTERPRISE_KB_CITATION || "").trim().toLowerCase();
  if (!raw) return defaultOn;
  if (raw === "0" || raw === "false" || raw === "off" || raw === "no") return false;
  return raw === "1" || raw === "true" || raw === "yes" || raw === "on";
}

function asRecord(v: unknown): Record<string, unknown> | null {
  return v && typeof v === "object" ? (v as Record<string, unknown>) : null;
}

/** Pull citation/source rows from platform kb/query JSON. */
export function extractKbSourceItems(parsed: unknown): KbSourceItem[] {
  const o = asRecord(parsed);
  if (!o) return [];
  const kb = asRecord(o.kb);
  const raw =
    (kb && Array.isArray(kb.items) ? kb.items : null) ||
    (Array.isArray(o.items) ? o.items : null) ||
    (Array.isArray(o.citations) ? o.citations : null) ||
    [];
  const out: KbSourceItem[] = [];
  for (const it of raw) {
    const row = asRecord(it);
    if (!row) continue;
    const text = String(row.text || row.content || row.snippet || "").trim();
    if (!text) continue;
    const source = String(
      row.title || row.doc_id || row.source || row.name || "unknown",
    ).trim() || "unknown";
    let score = 0;
    if (typeof row.score === "number") score = row.score;
    else if (typeof row.score === "string" && row.score.trim()) {
      const n = Number(row.score);
      if (!Number.isNaN(n)) score = n;
    }
    out.push({ source, text, score });
  }
  // B: deduplicate by source, keeping highest-score snippet per document
  const deduped = dedupeBySource(out);
  deduped.sort((a, b) => b.score - a.score);
  return deduped;
}

/**
 * Deduplicate items by source name.
 * When the same document appears multiple times, keep the highest-score snippet.
 */
function dedupeBySource(items: KbSourceItem[]): KbSourceItem[] {
  const map = new Map<string, KbSourceItem>();
  for (const it of items) {
    const existing = map.get(it.source);
    if (!existing || it.score > existing.score) {
      map.set(it.source, it);
    }
  }
  return Array.from(map.values());
}

function clipSnippet(text: string, max = MAX_SNIPPET_CHARS): string {
  const t = text.replace(/\s+/g, " ").trim();
  if (t.length <= max) return t;
  return `${t.slice(0, max)}…`;
}

/**
 * Format tool result text for the model (and user-visible transcript).
 * When citation=false, keep legacy dump (items as [src] text).
 */
export function formatKbCitationResponse(
  parsed: unknown,
  opts?: { citation?: boolean },
): string {
  const citation = opts?.citation !== false;
  const items = extractKbSourceItems(parsed);
  const o = asRecord(parsed);
  const answer =
    o && typeof o.answer === "string" && o.answer.trim()
      ? o.answer.trim().slice(0, 4000)
      : "";

  if (!citation) {
    return formatLegacy(parsed, items, answer);
  }

  // V2: no usable sources → fixed opening (tool layer, not model-dependent)
  if (items.length === 0) {
    const parts = [
      "AIPLAT_KB_RETRIEVE_OK",
      KB_EMPTY_PREFIX,
      "请勿编造引用或文档名。可改用包内 skills/SOP 继续，或请用户补充资料后入库。",
    ];
    if (answer) {
      parts.push("(平台返回了无来源 answer，已忽略，避免无溯源陈述。)");
    }
    return parts.join("\n\n");
  }

  const total = items.length;
  const top = items.slice(0, MAX_KB_SOURCES);
  const parts: string[] = ["AIPLAT_KB_RETRIEVE_OK"];

  parts.push(
    [
      "以下仅含知识库检索命中。回答事实时必须使用文末来源，格式 `[来源: 文档名]`；",
      "禁止编造未列出的文档或内容。",
    ].join(""),
  );

  // A: low-confidence warning (§3.4 spec)
  // Only trigger when scores are actually provided (non-zero) and all below threshold
  const scoresProvided = top.some((it) => it.score > 0);
  const allLowConfidence =
    scoresProvided && top.every((it) => it.score < LOW_CONFIDENCE_THRESHOLD);
  if (allLowConfidence) {
    parts.push(
      "⚠️ 以下检索结果置信度较低，仅供参考。回答时请向用户说明置信度情况，建议补充更多资料或联系管理员确认。",
    );
  }

  if (answer) {
    parts.push(answer);
  }

  // V3a + V6
  const refLines: string[] = ["── 参考文献 ──"];
  if (total > MAX_KB_SOURCES) {
    refLines.push(`（共 ${total} 条来源，展示前 ${MAX_KB_SOURCES} 条）`);
  }
  const circ = ["①", "②", "③", "④", "⑤"];
  top.forEach((it, i) => {
    const mark = circ[i] || `${i + 1}.`;
    refLines.push(`${mark} ${it.source} — "${clipSnippet(it.text)}"`);
    refLines.push(`   可用标记: [来源: ${it.source}]`);
  });
  parts.push(refLines.join("\n"));

  return parts.join("\n\n");
}

function formatLegacy(
  parsed: unknown,
  items: KbSourceItem[],
  answer: string,
): string {
  const parts: string[] = ["AIPLAT_KB_RETRIEVE_OK"];
  if (answer) parts.push(answer);
  for (const it of items.slice(0, MAX_KB_SOURCES)) {
    parts.push(`[${it.source}] ${it.text.slice(0, 500)}`);
  }
  if (parts.length === 1) {
    parts.push(JSON.stringify(parsed).slice(0, 3000));
  }
  return parts.join("\n\n");
}

/** System-prompt lines when citation contract is on (enterprise default). */
export function citationSystemPromptLines(): string[] {
  return [
    "KB citation contract (enterprise):",
    `- If tool text starts with 「${KB_EMPTY_PREFIX}」, say so to the user; do not invent sources.`,
    "- If 参考文献 is present: ground every factual claim in those sources using [来源: 文档名]; end with the reference list when answering from KB.",
    "- Never invent citations, doc names, or quotes not in the tool result.",
    "- If tool text contains ⚠️ 置信度较低 warning, relay this to the user before presenting the information.",
  ];
}
