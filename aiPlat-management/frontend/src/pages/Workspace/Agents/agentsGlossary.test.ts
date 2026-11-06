import { describe, expect, it } from 'vitest';
import {
  AGENTS_GLOSSARY,
  agentsGlossaryDomainCounts,
  flattenAgentsGlossary,
} from './agentsGlossary';

describe('agentsGlossary (Layer A SSOT)', () => {
  it('covers all domains with at least one entry', () => {
    const counts = agentsGlossaryDomainCounts();
    for (const d of ['lifecycle', 'actions', 'roles', 'types', 'ops'] as const) {
      expect((counts[d] || 0) > 0, `missing domain ${d}`).toBe(true);
    }
  });

  it('has unique terms and non-empty meanings', () => {
    const seen = new Set<string>();
    for (const e of AGENTS_GLOSSARY) {
      expect(e.term.trim().length).toBeGreaterThan(0);
      expect(e.meaning.trim().length, e.term).toBeGreaterThan(8);
      expect(seen.has(e.term), `duplicate ${e.term}`).toBe(false);
      seen.add(e.term);
    }
  });

  it('resolves lifecycle and approval aliases', () => {
    const flat = flattenAgentsGlossary();
    expect(flat.ready || flat['待审核']).toMatch(/资产审批|待审核/);
    expect(flat['资产审批'] || flat['/approval']).toMatch(/通过|上架/);
    expect(flat.Agent || flat['智能体']).toMatch(/Skill|角色/);
    expect(flat['应用工厂'] || flat['工厂']).toMatch(/工厂|交付/);
  });
});
