import { describe, expect, it } from 'vitest';
import { getAllPages, PAGE_PURPOSE } from './pageManifest';

describe('PAGE_PURPOSE coverage (小朱全局契约)', () => {
  it('every sidebar menu route has a non-empty PAGE_PURPOSE', () => {
    const pages = getAllPages();
    expect(pages.length).toBeGreaterThan(40);
    const missing: string[] = [];
    for (const p of pages) {
      const purpose = PAGE_PURPOSE[p.route];
      if (!purpose || !purpose.trim()) missing.push(p.route);
    }
    expect(missing, `missing PAGE_PURPOSE: ${missing.join(', ')}`).toEqual([]);
  });
});
