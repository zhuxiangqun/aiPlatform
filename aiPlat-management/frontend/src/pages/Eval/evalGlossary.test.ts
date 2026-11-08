import { describe, expect, it } from 'vitest';
import {
  EVAL_GLOSSARY,
  evalGlossaryDomainCounts,
  flattenEvalGlossary,
} from './evalGlossary';
import { EVAL_TAB_GUIDES } from './evalTabGuides';

describe('evalGlossary (systematic SSOT)', () => {
  it('covers all Eval domains with at least one entry', () => {
    const counts = evalGlossaryDomainCounts();
    const domains = [
      'honesty',
      'plane',
      'g2a',
      'g2b',
      'g2c',
      'preference',
      'scorecard',
      'evidence',
      'worksheets',
      'gates',
      'review',
      'runners',
      'reports',
      'sets',
      'object_contract',
    ] as const;
    for (const d of domains) {
      expect((counts[d] || 0) > 0, `missing domain ${d}`).toBe(true);
    }
  });

  it('has unique canonical terms and non-empty meanings', () => {
    const seen = new Set<string>();
    for (const e of EVAL_GLOSSARY) {
      expect(e.term.trim().length).toBeGreaterThan(0);
      expect(e.meaning.trim().length, e.term).toBeGreaterThan(8);
      expect(seen.has(e.term), `duplicate term ${e.term}`).toBe(false);
      seen.add(e.term);
    }
  });

  it('flattens aliases so UI labels resolve', () => {
    const flat = flattenEvalGlossary();
    expect(flat.accuracy_claim).toMatch(/准确率/);
    expect(flat.claims_gate || flat['L5门禁']).toMatch(/claims-gate|门禁/);
    expect(flat['κ'] || flat.kappa).toMatch(/一致/);
    expect(flat['黄金集锁定'] || flat.v0_locked).toMatch(/锁定/);
    expect(flat.Enqueue || flat['Enqueue job']).toMatch(/worker|排队/);
    expect(flat['评测成熟度五级'] || flat['L1-L5']).toMatch(/L1|compile-plan|校准/);
    expect(flat['A维evaluates'] || flat.evaluates).toMatch(/evaluates/);
    expect(flat['Knowledge≠dataset'] || flat.kb_eval).toMatch(/dataset/);
  });

  it('maps every tab guide title into glossary (term or alias)', () => {
    const flat = flattenEvalGlossary();
    const keys = Object.keys(flat);
    for (const g of Object.values(EVAL_TAB_GUIDES)) {
      const hit = keys.some(
        (k) => k === g.title || k.toLowerCase() === g.title.toLowerCase(),
      );
      expect(hit, `tab title missing from glossary: ${g.title}`).toBe(true);
    }
  });
});
