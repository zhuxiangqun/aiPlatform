import { describe, expect, it } from 'vitest';
import {
  groupsToExpandForLocation,
  menuItemMatchesLocation,
} from './AppLayout';

describe('menuItemMatchesLocation', () => {
  it('matches plain path ignoring extra ?tab=', () => {
    expect(
      menuItemMatchesLocation('/knowledge/business', '/knowledge/business', '?tab=factory'),
    ).toBe(true);
    expect(
      menuItemMatchesLocation('/diagnostics/fde', '/diagnostics/fde', ''),
    ).toBe(true);
  });

  it('does not mark sibling when exact child menu exists', () => {
    expect(
      menuItemMatchesLocation('/diagnostics', '/diagnostics/fde', ''),
    ).toBe(false);
  });

  it('matches ?tab= menu keys', () => {
    expect(
      menuItemMatchesLocation('/platform/kb?tab=wiki', '/platform/kb', '?tab=wiki'),
    ).toBe(true);
    expect(
      menuItemMatchesLocation('/platform/kb?tab=wiki', '/platform/kb', '?tab=vector'),
    ).toBe(false);
  });
});

describe('groupsToExpandForLocation', () => {
  it('expands knowledge for business shell with tab', () => {
    expect(groupsToExpandForLocation('/knowledge/business', '?tab=domains')).toContain(
      'knowledge',
    );
  });

  it('expands build for FDE workbench (menu lives under AI 应用工厂)', () => {
    expect(groupsToExpandForLocation('/diagnostics/fde', '')).toEqual(['build']);
  });
});

