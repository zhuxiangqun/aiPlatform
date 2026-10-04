import { describe, expect, it } from 'vitest';
import { auditRemainToast } from './AssetAuditPanel';

describe('auditRemainToast', () => {
  it('ignores info-only leftover (draft tip must not look like remaining problems)', () => {
    const msg = auditRemainToast(3, {
      errors: 0,
      warnings: 0,
      info: 4,
      total: 4,
      health: 'A',
      fixable: 0,
      unfixable: 0,
    });
    expect(msg.kind).toBe('success');
    expect(msg.text).toContain('审核已通过');
  });

  it('reports remaining errors+warnings after apply', () => {
    const msg = auditRemainToast(2, {
      errors: 0,
      warnings: 3,
      info: 1,
      total: 4,
      health: 'B',
      fixable: 3,
      unfixable: 0,
    });
    expect(msg.kind).toBe('info');
    expect(msg.text).toContain('仍剩 3 项问题');
  });
});
