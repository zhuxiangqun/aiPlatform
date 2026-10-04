/**
 * Convert Python-ish dict/list literals (LLM / skill often return str(dict)) into JSON text.
 * Tokenizes quotes so None/True inside strings are preserved.
 *
 * Critical: Python repr uses ``\n`` (backslash + n) inside quotes for newlines.
 * Must decode those escapes into real newlines before re-emitting JSON, otherwise
 * code becomes ``reports.pynn```pythonnfrom`` (run-34307006ab2a UI mangling).
 */
export function pythonLiteralToJsonText(src: string): string | null {
  const s = String(src || '').trim();
  if (!s.startsWith('{') && !s.startsWith('[')) return null;
  let out = '';
  let i = 0;
  const n = s.length;
  const isIdentEnd = (idx: number) => idx >= n || !/[A-Za-z0-9_]/.test(s[idx]);

  const decodeEscaped = (ch: string): string => {
    if (ch === 'n') return '\n';
    if (ch === 'r') return '\r';
    if (ch === 't') return '\t';
    if (ch === '\\') return '\\';
    if (ch === "'" || ch === '"') return ch;
    // Unknown escape: keep both chars so data is not silently dropped
    return `\\${ch}`;
  };

  while (i < n) {
    const c = s[i];
    if (c === "'" || c === '"') {
      const quote = c;
      let j = i + 1;
      let esc = false;
      let buf = '';
      while (j < n) {
        const ch = s[j];
        if (esc) {
          buf += decodeEscaped(ch);
          esc = false;
          j += 1;
          continue;
        }
        if (ch === '\\') {
          esc = true;
          j += 1;
          continue;
        }
        if (ch === quote) break;
        buf += ch;
        j += 1;
      }
      out += `"${buf
        .replace(/\\/g, '\\\\')
        .replace(/"/g, '\\"')
        .replace(/\n/g, '\\n')
        .replace(/\r/g, '\\r')
        .replace(/\t/g, '\\t')}"`;
      i = j + 1;
      continue;
    }
    if (s.startsWith('None', i) && isIdentEnd(i + 4)) {
      out += 'null';
      i += 4;
      continue;
    }
    if (s.startsWith('True', i) && isIdentEnd(i + 4)) {
      out += 'true';
      i += 4;
      continue;
    }
    if (s.startsWith('False', i) && isIdentEnd(i + 5)) {
      out += 'false';
      i += 5;
      continue;
    }
    out += c;
    i += 1;
  }
  return out;
}

/** Parse JSON, or Python dict/list repr into an object. */
export function tryParseJsonOrPythonLiteral(text: string): unknown | null {
  const s = String(text || '').trim();
  if (!s) return null;
  // ```python / ```ts bodies often contain a tiny dict (e.g. FastAPI /health).
  // Only treat a fence as JSON when the fenced body itself starts with { or [.
  const fence = s.match(/```(?:json)?[^\n]*\n\s*([{\[][\s\S]*?)```/i);
  const looksLikeEnvelope = s.startsWith('{') || s.startsWith('[');
  const candidate = (fence?.[1] || (looksLikeEnvelope ? s : '')).trim();
  if (!candidate.startsWith('{') && !candidate.startsWith('[')) return null;
  // Markdown ## FILE deliveries: do not scrape inner JSON unless the whole
  // string is an envelope ({code}/{text} wrapping the files).
  if (!looksLikeEnvelope && /##\s*FILE:\s*\S/.test(s) && !fence) return null;
  try {
    return JSON.parse(candidate);
  } catch {
    /* try python-ish below */
  }
  const py = pythonLiteralToJsonText(candidate);
  if (py) {
    try {
      return JSON.parse(py);
    } catch {
      /* fall through */
    }
  }
  // Truncated / trailing junk: parse from first brace
  const start = candidate.search(/[\[{]/);
  if (start > 0) {
    const slice = candidate.slice(start);
    try {
      return JSON.parse(slice);
    } catch {
      const py2 = pythonLiteralToJsonText(slice);
      if (py2) {
        try {
          return JSON.parse(py2);
        } catch {
          return null;
        }
      }
    }
  }
  return null;
}
