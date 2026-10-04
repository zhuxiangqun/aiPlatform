/**
 * Parse Agent/Skill coding deliveries that use ``## FILE: path`` sections.
 * Keeps planning prose (before the first FILE) separate from file bodies.
 *
 * Also unwraps ``{code, language}`` JSON / Python-repr envelopes that skill
 * observe often returns as a single string (run-c896745b fullscreen dump).
 */

import { tryParseJsonOrPythonLiteral } from './pythonLiteral';

export type FileSection = { path: string; body: string };

export type ParsedFileDelivery = {
  overview: string;
  files: FileSection[];
};

/** JS has no inline (?m)/(?i) — use flag suffix. */
const FILE_SPLIT = /^(?=##\s*FILE:\s*\S)/m;
const FILE_HEAD = /^##\s*FILE:\s*([^\s`]+)\s*\n?([\s\S]*)$/i;
const HAS_FILE = /^##\s*FILE:\s*\S/m;
const HAS_FILE_ANY = /##\s*FILE:\s*\S/;

/** True when the blob is a multi-file coding delivery (not a JSON skill envelope). */
export function hasFileDeliveryMarkers(text: string): boolean {
  const src = normalizeCodingBlob(String(text || ''));
  return HAS_FILE.test(src) || HAS_FILE_ANY.test(src);
}

/** Turn ``\\n`` blobs into real newlines so line-anchored FILE headers match. */
export function normalizeCodingBlob(text: string): string {
  let t = String(text || '');
  if (!t.trim()) return '';
  const nlCount = (t.match(/\n/g) || []).length;
  if (t.includes('\\n') && nlCount < 2 && (t.includes('## FILE:') || t.includes('FILE:'))) {
    t = t.replace(/\\n/g, '\n').replace(/\\t/g, '\t');
  }
  return t;
}

/**
 * Pull the human coding body out of envelopes:
 * - object ``{ code, language, text, … }``
 * - JSON / Python-repr string of the same
 * - nested ``{ output: { code } }``
 */
export function unwrapCodeEnvelope(value: unknown, depth = 0): string {
  if (value == null || depth > 6) return '';

  if (typeof value === 'string') {
    const s = value.trim();
    if (!s) return '';
    if (s.startsWith('{') || s.startsWith('[')) {
      const parsed = tryParseJsonOrPythonLiteral(s);
      if (parsed != null && typeof parsed === 'object') {
        const inner = unwrapCodeEnvelope(parsed, depth + 1);
        if (inner) return inner;
      }
    }
    return normalizeCodingBlob(s);
  }

  if (typeof value === 'object' && !Array.isArray(value)) {
    const o = value as Record<string, unknown>;
    // Prefer code* first — language-locked skill envelopes.
    for (const k of [
      'code',
      'generated_code',
      'source',
      'snippet',
      'text',
      'markdown',
      'answer',
      'content',
      'output',
      'result',
    ]) {
      const v = o[k];
      if (typeof v === 'string' && v.trim()) {
        const u = unwrapCodeEnvelope(v, depth + 1);
        if (!u) continue;
        if (HAS_FILE.test(u) || HAS_FILE_ANY.test(u)) return u;
        if (k === 'code' || k === 'generated_code' || k === 'source' || k === 'snippet') {
          return u;
        }
        // Keep first substantial text as fallback after scan
      } else if (v && typeof v === 'object') {
        const u = unwrapCodeEnvelope(v, depth + 1);
        if (u && (HAS_FILE.test(u) || HAS_FILE_ANY.test(u))) return u;
      }
    }
    // Second pass: any non-empty string field that looks like delivery
    for (const v of Object.values(o)) {
      if (typeof v === 'string' && v.trim().length > 40) {
        const u = unwrapCodeEnvelope(v, depth + 1);
        if (u && (HAS_FILE.test(u) || HAS_FILE_ANY.test(u))) return u;
      }
    }
  }

  return '';
}

/** Strip one outer markdown fence if the whole body is fenced. */
export function stripOuterFence(body: string): string {
  let s = String(body || '').trim();
  if (!s.startsWith('```')) return s;
  const lines = s.split('\n');
  if (lines.length < 2) return s;
  lines.shift();
  if (lines.length && lines[lines.length - 1].trim() === '```') lines.pop();
  return lines.join('\n').replace(/\n$/, '');
}

export function parseFileDelivery(text: string): ParsedFileDelivery | null {
  const src = normalizeCodingBlob(String(text || ''));
  if (!HAS_FILE.test(src) && !HAS_FILE_ANY.test(src)) return null;
  // If markers exist but not at line starts, still try split (normalize should have fixed \\n)
  if (!HAS_FILE.test(src)) return null;

  const parts = src.split(FILE_SPLIT);
  const overview = (parts[0] || '').trim();
  const files: FileSection[] = [];
  for (let i = 1; i < parts.length; i++) {
    const m = (parts[i] || '').match(FILE_HEAD);
    if (!m) continue;
    const path = (m[1] || '').trim().replace(/^[`"']+|[`"']+$/g, '');
    const body = stripOuterFence(m[2] || '');
    if (path) files.push({ path, body });
  }
  if (files.length === 0) return null;
  return { overview, files };
}

/** Pull coding delivery text from raw execute envelopes ({text}, {code}, …). */
export function extractCodingDeliveryText(text: string, payload: unknown): string {
  const fromText = unwrapCodeEnvelope(text);
  if (fromText && (HAS_FILE.test(fromText) || HAS_FILE_ANY.test(fromText))) {
    return normalizeCodingBlob(fromText);
  }
  const fromPayload = unwrapCodeEnvelope(payload);
  if (fromPayload && (HAS_FILE.test(fromPayload) || HAS_FILE_ANY.test(fromPayload))) {
    return normalizeCodingBlob(fromPayload);
  }
  // Unwrapped code body without FILE headers — still better than dict dump
  if (fromText && fromText.trim() && fromText.trim() !== String(text || '').trim()) {
    return normalizeCodingBlob(fromText);
  }
  if (fromPayload && fromPayload.trim()) {
    return normalizeCodingBlob(fromPayload);
  }
  return '';
}

/** Absolute run workspace from execute envelopes (`persisted_root`). */
export function persistRootFromPayload(raw: unknown): string {
  const walk = (v: unknown, depth = 0): string => {
    if (v == null || depth > 4) return '';
    if (typeof v === 'string') {
      const s = v.trim();
      if (s.startsWith('{') || s.startsWith('[')) {
        const parsed = tryParseJsonOrPythonLiteral(s);
        if (parsed != null) return walk(parsed, depth + 1);
      }
      return '';
    }
    if (typeof v !== 'object' || Array.isArray(v)) return '';
    const o = v as Record<string, unknown>;
    const root = o.persisted_root || o.persist_root;
    if (typeof root === 'string' && root.trim()) return root.trim();
    for (const k of ['output', 'result', 'data']) {
      const inner = walk(o[k], depth + 1);
      if (inner) return inner;
    }
    return '';
  };
  return walk(raw);
}

export function langFromPath(path: string): string {
  const p = path.toLowerCase();
  if (p.endsWith('.tsx')) return 'tsx';
  if (p.endsWith('.ts')) return 'ts';
  if (p.endsWith('.jsx')) return 'jsx';
  if (p.endsWith('.js')) return 'js';
  if (p.endsWith('.py')) return 'python';
  if (p.endsWith('.json')) return 'json';
  if (p.endsWith('.md')) return 'markdown';
  if (p.endsWith('.css')) return 'css';
  return 'text';
}
