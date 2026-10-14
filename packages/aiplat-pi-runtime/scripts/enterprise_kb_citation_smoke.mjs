#!/usr/bin/env node
/**
 * Citation contract smoke (V2 / V3a / V6) — loads pure TS helper via strip-types.
 */
import { pathToFileURL } from "node:url";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const MOD = path.join(__dirname, "..", "extensions", "enterprise_kb_citation.ts");

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

async function main() {
  const m = await import(pathToFileURL(MOD).href);
  const {
    KB_EMPTY_PREFIX,
    MAX_KB_SOURCES,
    MAX_SNIPPET_CHARS,
    LOW_CONFIDENCE_THRESHOLD,
    formatKbCitationResponse,
    extractKbSourceItems,
    citationSystemPromptLines,
    envCitationExpandable,
  } = m;

  // V2 empty
  const empty = formatKbCitationResponse({ ok: true, kb: { items: [] } });
  assert(empty.includes(KB_EMPTY_PREFIX), "V2: empty prefix");
  assert(empty.includes("AIPLAT_KB_RETRIEVE_OK"), "V2: ok marker");
  assert(!empty.includes("── 参考文献 ──"), "V2: no ref list");

  // answer without items → still V2 (ignore uncited answer)
  const ansOnly = formatKbCitationResponse({
    answer: "should not surface as grounded fact",
    kb: { items: [] },
  });
  assert(ansOnly.includes(KB_EMPTY_PREFIX), "V2: answer-only still empty");
  assert(!ansOnly.includes("should not surface"), "V2: drop uncited answer body");

  // V3a + V6
  const long = "字".repeat(MAX_SNIPPET_CHARS + 40);
  const items = [];
  for (let i = 0; i < 7; i++) {
    items.push({
      text: i === 0 ? long : `snippet-${i}`,
      doc_id: `doc-${i}.pdf`,
      score: 1 - i * 0.1,
    });
  }
  const hit = formatKbCitationResponse({ kb: { items } });
  assert(hit.includes("── 参考文献 ──"), "V3a: ref header");
  assert(hit.includes("[来源: doc-0.pdf]"), "V3a: source tag hint");
  assert(hit.includes("共 7 条来源，展示前 5"), "V6: overflow note");
  assert(extractKbSourceItems({ kb: { items } }).length === 7, "extract all");
  const shown = (hit.match(/可用标记:/g) || []).length;
  assert(shown === MAX_KB_SOURCES, `V6: show ${MAX_KB_SOURCES} tags, got ${shown}`);
  const snipLine = hit.split("\n").find((l) => l.includes("doc-0.pdf") && l.includes("—"));
  assert(snipLine && snipLine.includes("…"), "V3a: long snippet clipped");
  assert(
    !snipLine || snipLine.replace(/.*—\s*"/, "").replace(/"\s*$/, "").length <= MAX_SNIPPET_CHARS + 1,
    "V3a: snippet ≤200+ellipsis",
  );

  // citation=false legacy
  const legacy = formatKbCitationResponse(
    { kb: { items: [{ text: "AIPLAT_MOCK_KB_OK", doc_id: "doc1" }] } },
    { citation: false },
  );
  assert(legacy.includes("AIPLAT_MOCK_KB_OK"), "legacy keeps text");
  assert(!legacy.includes("── 参考文献 ──"), "legacy no ref block");

  // B: source deduplication — same doc_id, keep highest-score snippet
  const dupItems = [
    { text: "snippet-a-high", doc_id: "doc-A.pdf", score: 0.9 },
    { text: "snippet-a-low", doc_id: "doc-A.pdf", score: 0.5 },
    { text: "snippet-b", doc_id: "doc-B.pdf", score: 0.7 },
  ];
  const dupExtracted = extractKbSourceItems({ kb: { items: dupItems } });
  assert(dupExtracted.length === 2, `B: dedup to 2 sources, got ${dupExtracted.length}`);
  assert(dupExtracted[0].source === "doc-A.pdf", "B: highest score first");
  assert(dupExtracted[0].text === "snippet-a-high", "B: kept highest-score snippet");
  const dupResult = formatKbCitationResponse({ kb: { items: dupItems } });
  assert(!dupResult.includes("snippet-a-low"), "B: dropped lower-score duplicate in output");
  assert(dupResult.includes("doc-B.pdf"), "B: distinct source still present");

  // A: low-confidence warning — all scores below threshold
  const lowConfItems = [
    { text: "low-1", doc_id: "doc-low-1.pdf", score: 0.3 },
    { text: "low-2", doc_id: "doc-low-2.pdf", score: 0.2 },
  ];
  const lowConfResult = formatKbCitationResponse({ kb: { items: lowConfItems } });
  assert(lowConfResult.includes("置信度较低"), "A: low-confidence warning present");
  assert(lowConfResult.includes("── 参考文献 ──"), "A: ref block still present with low confidence");

  // A: high-confidence — no warning
  const highConfItems = [
    { text: "high-1", doc_id: "doc-high-1.pdf", score: 0.8 },
    { text: "high-2", doc_id: "doc-high-2.pdf", score: 0.7 },
  ];
  const highConfResult = formatKbCitationResponse({ kb: { items: highConfItems } });
  assert(!highConfResult.includes("置信度较低"), "A: no warning when scores are high");

  // A: no scores provided — no warning (can't determine confidence)
  const noScoreItems = [
    { text: "no-score-1", doc_id: "doc-ns-1.pdf" },
    { text: "no-score-2", doc_id: "doc-ns-2.pdf" },
  ];
  const noScoreResult = formatKbCitationResponse({ kb: { items: noScoreItems } });
  assert(!noScoreResult.includes("置信度较低"), "A: no warning when scores not provided");

  // A: mixed scores (some high, some low) — no warning
  const mixedItems = [
    { text: "mixed-high", doc_id: "doc-mh.pdf", score: 0.9 },
    { text: "mixed-low", doc_id: "doc-ml.pdf", score: 0.2 },
  ];
  const mixedResult = formatKbCitationResponse({ kb: { items: mixedItems } });
  assert(!mixedResult.includes("置信度较低"), "A: no warning when some scores are high");

  // V1 / V5 prompt + tool-result contract lines
  assert(hit.includes("V1："), "V1: tool-result instructs source tags");
  assert(hit.includes("V5："), "V5: tool-result instructs unverified tag");
  const prompt = citationSystemPromptLines().join("\n");
  assert(prompt.includes("V1:"), "V1: system prompt line");
  assert(prompt.includes("V5:"), "V5: system prompt line");
  assert(prompt.includes("（未验证）") || prompt.includes("未验证"), "V5: unverified marker");

  // V3b expandable <details> (opt-in)
  const expandHit = formatKbCitationResponse(
    { kb: { items } },
    { expandable: true },
  );
  assert(expandHit.includes("<details>"), "V3b: details open");
  assert(expandHit.includes("</details>"), "V3b: details close");
  assert(expandHit.includes("<summary>"), "V3b: summary");
  assert(expandHit.includes("点击展开"), "V3b: expand hint");
  assert(!expandHit.includes("── 参考文献 ──"), "V3b: no plain header when expandable");
  const plainHit = formatKbCitationResponse(
    { kb: { items } },
    { expandable: false },
  );
  assert(plainHit.includes("── 参考文献 ──"), "V3a: plain header when expandable=false");
  assert(!plainHit.includes("<details>"), "V3a: no details when expandable=false");
  const prevExpand = process.env.AIPLAT_ENTERPRISE_KB_CITATION_EXPAND;
  process.env.AIPLAT_ENTERPRISE_KB_CITATION_EXPAND = "1";
  assert(envCitationExpandable() === true, "V3b: env on");
  const envExpandHit = formatKbCitationResponse({ kb: { items } });
  assert(envExpandHit.includes("<details>"), "V3b: env drives details");
  process.env.AIPLAT_ENTERPRISE_KB_CITATION_EXPAND = "0";
  assert(envCitationExpandable() === false, "V3b: env off");
  if (prevExpand === undefined) delete process.env.AIPLAT_ENTERPRISE_KB_CITATION_EXPAND;
  else process.env.AIPLAT_ENTERPRISE_KB_CITATION_EXPAND = prevExpand;

  console.log("PASS: enterprise_kb_citation V2/V3a/V3b/V6 + V1/V5 + dedup + low-confidence");
  console.log("AIPLAT_ENTERPRISE_KB_CITATION_SMOKE_OK");
}

main().catch((e) => {
  console.error("FAIL:", e);
  process.exit(1);
});
