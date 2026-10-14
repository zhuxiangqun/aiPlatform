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
    formatKbCitationResponse,
    extractKbSourceItems,
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

  console.log("PASS: enterprise_kb_citation V2/V3a/V6");
  console.log("AIPLAT_ENTERPRISE_KB_CITATION_SMOKE_OK");
}

main().catch((e) => {
  console.error("FAIL:", e);
  process.exit(1);
});
