import { tryParseJsonOrPythonLiteral } from './pythonLiteral';

const PRODUCT_LIST_KEYS = [
  'test_questions',
  'test_cases',
  'cases',
  'questions',
  'functional_requirements',
  'user_stories',
  'components',
  'files',
  'api_contracts',
] as const;

function parseFirstJsonValue(s: string, start: number): { value: unknown; end: number } | null {
  const slice = s.slice(start);
  const open = slice.search(/[\[{]/);
  if (open < 0) return null;
  const abs = start + open;
  const src = s.slice(abs);
  let depth = 0;
  let inStr = false;
  let esc = false;
  const openCh = src[0];
  const closeCh = openCh === '{' ? '}' : ']';
  for (let i = 0; i < src.length; i++) {
    const c = src[i];
    if (inStr) {
      if (esc) {
        esc = false;
        continue;
      }
      if (c === '\\') {
        esc = true;
        continue;
      }
      if (c === '"') inStr = false;
      continue;
    }
    if (c === '"') {
      inStr = true;
      continue;
    }
    if (c === '{' || c === '[') depth += 1;
    else if (c === '}' || c === ']') {
      depth -= 1;
      if (depth === 0 && c === closeCh) {
        try {
          return { value: JSON.parse(src.slice(0, i + 1)), end: abs + i + 1 };
        } catch {
          return null;
        }
      }
    }
  }
  return null;
}

function recoverNamedArray(s: string, key: string): Record<string, unknown>[] {
  const markers = [`"${key}"`, `\\"${key}\\"`];
  let i = -1;
  for (const m of markers) {
    i = s.indexOf(m);
    if (i >= 0) break;
  }
  if (i < 0) return [];
  const lb = s.indexOf('[', i);
  if (lb < 0) return [];
  const items: Record<string, unknown>[] = [];
  let pos = lb + 1;
  while (pos < s.length) {
    while (pos < s.length && /[\s,]/.test(s[pos])) pos += 1;
    if (pos >= s.length || s[pos] === ']') break;
    if (s[pos] !== '{') break;
    const parsed = parseFirstJsonValue(s, pos);
    if (!parsed || !parsed.value || typeof parsed.value !== 'object' || Array.isArray(parsed.value)) {
      break;
    }
    items.push(parsed.value as Record<string, unknown>);
    pos = parsed.end;
  }
  return items;
}

function recoverTruncatedProduct(s: string): Record<string, unknown> | null {
  for (const key of ['test_questions', 'test_cases'] as const) {
    const items = recoverNamedArray(s, key);
    if (items.length > 0) {
      return { [key]: items, total_test_cases: items.length };
    }
  }
  return null;
}

function isDoneEnvelope(o: Record<string, unknown>): boolean {
  const typ = String(o.type || '').trim().toLowerCase();
  if (typ === 'done' || typ === 'final' || typ === 'response') return true;
  const keys = Object.keys(o);
  return Boolean(o.answer) && keys.every((k) =>
    ['type', 'answer', 'text', 'response', 'input'].includes(k),
  );
}

function productListLen(obj: unknown): number {
  if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return 0;
  const o = obj as Record<string, unknown>;
  let best = 0;
  for (const k of PRODUCT_LIST_KEYS) {
    const v = o[k];
    if (Array.isArray(v) && v.length > 0 && (typeof v[0] === 'object' || typeof v[0] === 'string')) {
      best = Math.max(best, v.length);
    }
  }
  return best;
}

function parseLoose(s: string): unknown | null {
  const t = s.trim();
  if (!t) return null;
  if (t.startsWith('{') || t.startsWith('[')) {
    try {
      return JSON.parse(t);
    } catch {
      /* truncated */
    }
    const py = tryParseJsonOrPythonLiteral(t);
    if (py != null) return py;
    const first = parseFirstJsonValue(t, 0);
    if (first) return first.value;
  }
  return recoverTruncatedProduct(t);
}

/**
 * Peel ReAct ``{"type":"done","answer":...}`` (and truncated JSON) down to the
 * usable product — test_questions JSON, not the envelope.
 */
export function unwrapExecuteProduct(raw: unknown): unknown {
  let cur: unknown = raw;
  for (let depth = 0; depth < 10; depth++) {
    if (cur == null) return cur;
    if (typeof cur === 'string') {
      const s = cur.trim();
      if (!s) return s;
      const recovered = recoverTruncatedProduct(s);
      const parsed = parseLoose(s);
      if (parsed && typeof parsed === 'object') {
        if (productListLen(parsed) >= 1) return parsed;
        if (recovered && productListLen(recovered) > productListLen(parsed)) return recovered;
        cur = parsed;
        continue;
      }
      if (recovered) return recovered;
      if (s.includes('"type"') && s.includes('"answer"')) {
        const env = parseFirstJsonValue(s, s.search(/\{/));
        if (env && env.value && typeof env.value === 'object') {
          cur = env.value;
          continue;
        }
      }
      return s;
    }
    if (typeof cur === 'object' && !Array.isArray(cur)) {
      const o = cur as Record<string, unknown>;
      if (productListLen(o) >= 1) return o;
      if (isDoneEnvelope(o)) {
        const inner = o.answer ?? o.text ?? o.response;
        if (inner != null && inner !== '') {
          cur = inner;
          continue;
        }
      }
      if (typeof o.text === 'string' && o.text.trim()) {
        cur = o.text;
        continue;
      }
      if (o.text && typeof o.text === 'object') {
        cur = o.text;
        continue;
      }
      if (typeof o.output === 'string' && o.output.trim()) {
        cur = o.output;
        continue;
      }
      if (o.output && typeof o.output === 'object') {
        cur = o.output;
        continue;
      }
      return o;
    }
    return cur;
  }
  return cur;
}

export function executeProductAsText(raw: unknown): string {
  const u = unwrapExecuteProduct(raw);
  if (u == null) return '';
  if (typeof u === 'string') {
    const again = unwrapExecuteProduct(u);
    if (again && typeof again === 'object') {
      try {
        return JSON.stringify(again, null, 2);
      } catch {
        return u;
      }
    }
    return u;
  }
  try {
    return JSON.stringify(u, null, 2);
  } catch {
    return String(u);
  }
}
