import { describe, expect, it } from 'vitest';
import {
  SKILLS_GLOSSARY,
  flattenSkillsGlossary,
  skillsGlossaryDomainCounts,
} from './skillsGlossary';

describe('skillsGlossary (Layer A SSOT)', () => {
  it('covers all domains', () => {
    const counts = skillsGlossaryDomainCounts();
    for (const d of ['lifecycle', 'actions', 'roles', 'categories', 'gov', 'ops'] as const) {
      expect((counts[d] || 0) > 0, `missing ${d}`).toBe(true);
    }
  });

  it('unique terms with meanings', () => {
    const seen = new Set<string>();
    for (const e of SKILLS_GLOSSARY) {
      expect(e.meaning.trim().length, e.term).toBeGreaterThan(8);
      expect(seen.has(e.term), `dup ${e.term}`).toBe(false);
      seen.add(e.term);
    }
  });

  it('resolves key aliases', () => {
    const flat = flattenSkillsGlossary();
    expect(flat.execution_type || flat['执行类型']).toMatch(/handler/);
    expect(flat.ready || flat['待审核']).toMatch(/资产审批|待审核/);
    expect(flat['治理'] || flat['签名/冒烟']).toMatch(/签名|审核/);
  });
});
