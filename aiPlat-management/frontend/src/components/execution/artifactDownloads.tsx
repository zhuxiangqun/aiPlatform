import React, { useMemo } from 'react';
import { Button } from '../ui';
import { extractCodingDeliveryText } from './fileDelivery';
import { tryParseJsonOrPythonLiteral } from './pythonLiteral';

const PATH_RE =
  /(?:\/(?:Users|home|var|tmp|opt)[^\s`"')\]}>]+?\.(?:pptx|potx|docx|xlsx|pdf)|~\/\.aiplat\/[^\s`"')\]}>]+?\.(?:pptx|potx|docx|xlsx|pdf))/gi;

/** Parse JSON-string envelopes so {markdown,result,...} renders as human text. */
export function coerceSkillEnvelope(raw: unknown): unknown {
  let cur: unknown = raw;
  for (let i = 0; i < 4; i++) {
    if (typeof cur === 'string') {
      const s = cur.trim();
      if (!s.startsWith('{') && !s.startsWith('[')) return cur;
      try {
        cur = JSON.parse(s);
        continue;
      } catch {
        const py = tryParseJsonOrPythonLiteral(s);
        if (py && typeof py === 'object') {
          cur = py;
          continue;
        }
        return cur;
      }
    }
    if (cur && typeof cur === 'object' && !Array.isArray(cur)) {
      const o = cur as Record<string, unknown>;
      // unwrap one more layer of { output: {...} } / { result: {...object...} }
      if (o.output && typeof o.output === 'object') {
        cur = o.output;
        continue;
      }
      // code_generation observe: { code, language } — peel to inner for display helpers
      if (typeof o.code === 'string' && o.code.trim() && ('language' in o || '_language_locked' in o)) {
        cur = o.code;
        continue;
      }
      if (
        o.result &&
        typeof o.result === 'object' &&
        (typeof (o.result as any).markdown === 'string' || typeof (o.result as any).result === 'string')
      ) {
        cur = o.result;
        continue;
      }
    }
    return cur;
  }
  return cur;
}

/** Collect absolute artifact paths from free text or structured skill/tool output. */
export function extractArtifactPaths(raw: unknown): string[] {
  const found = new Set<string>();
  const push = (p: string) => {
    const s = String(p || '').trim().replace(/^`+|`+$/g, '');
    if (!s) return;
    if (!/\.(pptx|potx|docx|xlsx|pdf)$/i.test(s)) return;
    found.add(s);
  };

  const walk = (v: unknown, depth = 0) => {
    if (v == null || depth > 6) return;
    v = depth === 0 ? coerceSkillEnvelope(v) : v;
    if (typeof v === 'string') {
      if (/\.(pptx|potx|docx|xlsx|pdf)$/i.test(v.trim()) && (v.includes('/') || v.startsWith('~'))) {
        push(v.trim());
      }
      const m = v.match(PATH_RE);
      if (m) m.forEach(push);
      return;
    }
    if (typeof v === 'object') {
      const o = v as Record<string, unknown>;
      for (const k of ['result', 'pptx_path', 'path', 'file_path', 'output_path', 'docx_path', 'xlsx_path']) {
        if (typeof o[k] === 'string') push(String(o[k]));
      }
      for (const val of Object.values(o)) walk(val, depth + 1);
    }
  };
  walk(raw);
  return Array.from(found).slice(0, 5);
}

export function downloadArtifactPath(path: string) {
  window.open(
    `/api/platform/apps/browser/test/download?path=${encodeURIComponent(path)}`,
    '_blank',
    'noopener,noreferrer',
  );
}

/** Prefer human markdown from skill envelopes; fall back to structured summary. */
export function skillOutputDisplayText(raw: unknown): string {
  // Coding double-envelope: { text: "{'code': '...\\n## FILE...'}" } → clean body
  const coding = extractCodingDeliveryText(
    typeof raw === 'string' ? raw : '',
    raw,
  );
  if (coding.trim() && /##\s*FILE:\s*\S/.test(coding)) {
    return coding;
  }

  const cur = coerceSkillEnvelope(raw);
  if (cur == null) return '';
  if (typeof cur === 'string') {
    // still a plain path?
    if (/\.(pptx|potx|docx|xlsx|pdf)$/i.test(cur.trim())) {
      return `# 已生成\n- 路径: \`${cur.trim()}\``;
    }
    // Python-repr / JSON skill blob still as string
    const unwrapped = extractCodingDeliveryText(cur, null);
    if (unwrapped.trim() && unwrapped.trim() !== cur.trim()) return unwrapped;
    return cur;
  }
  if (typeof cur === 'object') {
    const o = cur as Record<string, unknown>;
    if (typeof o.markdown === 'string' && o.markdown.trim()) return o.markdown;
    // code_generation / language-locked envelopes
    if (typeof o.code === 'string' && o.code.trim()) return o.code;
    if (typeof o.generated_code === 'string' && String(o.generated_code).trim()) {
      return String(o.generated_code);
    }
    if (typeof o.output === 'string' && o.output.trim()) {
      // nested string may itself be JSON
      const nested = skillOutputDisplayText(o.output);
      if (nested && nested !== o.output) return nested;
      return o.output;
    }
    if (typeof o.text === 'string' && o.text.trim()) {
      const nested = extractCodingDeliveryText(o.text, o);
      if (nested.trim()) return nested;
      return o.text;
    }
    const path = o.result || o.pptx_path || o.path || o.file_path;
    if (typeof path === 'string' && path) {
      const pages = o.page_count != null ? `\n- 页数: ${o.page_count}` : '';
      const tmpl = o.template_used ? `\n- 模版: \`${o.template_used}\`` : '';
      const when = o.generated_at ? `\n- 时间: ${o.generated_at}` : '';
      return `# PPT 已生成\n- 路径: \`${path}\`${pages}${tmpl}${when}`;
    }
  }
  try {
    return JSON.stringify(cur, null, 2);
  } catch {
    return String(cur);
  }
}

export const ArtifactDownloadBar: React.FC<{ raw: unknown; className?: string }> = ({ raw, className }) => {
  const paths = useMemo(() => extractArtifactPaths(raw), [raw]);
  if (paths.length === 0) return null;
  return (
    <div className={`mb-3 flex flex-wrap gap-2 items-center ${className || ''}`}>
      {paths.map((p) => (
        <Button key={p} variant="primary" size="sm" onClick={() => downloadArtifactPath(p)}>
          ⬇ 下载 {p.split('/').pop()}
        </Button>
      ))}
      <span className="text-[10px] text-gray-500 font-mono break-all">{paths[0]}</span>
    </div>
  );
};
