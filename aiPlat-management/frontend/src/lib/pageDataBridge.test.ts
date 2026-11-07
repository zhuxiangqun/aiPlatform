import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  clearAssetAuditPageFields,
  clearPageData,
  clearSmokeEvalPageFields,
  formatAuditIssueForPage,
  getPageData,
  pageDataToText,
  patchPageData,
  reportAssetAuditToPage,
  reportPageData,
} from './pageDataBridge';

describe('formatAuditIssueForPage', () => {
  it('uses Chinese suggestion instead of truncated English message', () => {
    const line = formatAuditIssueForPage({
      severity: 'error',
      category: 'unrealized_side_effect',
      message:
        "SIDE_EFFECT_UNREALIZED: skill declares mutating effects/permissions ['inferred:upload'] but execution_type=prompt has no handler.py, registered tools or MCP",
      suggestion:
        '真上传：点「去安装 Tool」或「去安装 MCP」，装好后回本页勾选并保存。不真传：点「改成只出文案」。一键不会编 handler.py 或假 play_url。',
      create_brief: { must_have: '名称含 oss/upload' },
    });
    expect(line).toContain('error/unrealized_side_effect');
    expect(line).toContain('去安装 Tool');
    expect(line).toContain('应具备:名称含 oss/upload');
    expect(line).not.toMatch(/registe/);
    expect(line).not.toContain('SIDE_EFFECT_UNREALIZED');
  });
});

describe('reportAssetAuditToPage', () => {
  const route = '/workspace/skills';

  beforeEach(() => {
    (globalThis as any).window = (globalThis as any).window || {};
    (globalThis as any).window.__AIPLAT_PAGE_DATA__ = {};
  });

  afterEach(() => {
    clearPageData(route);
  });

  it('writes issue0 + skillId and preserves guideGlossary across list refresh', () => {
    reportPageData(route, { guideGlossary: 'Skill=可复用动作', totalSkills: 3 });
    reportAssetAuditToPage({
      route,
      kind: 'skill',
      id: 'demo_skill',
      name: 'demo',
      result: {
        summary: { errors: 1, warnings: 0, info: 0, total: 1, health: 'warn' },
        issues: [
          {
            severity: 'error',
            category: 'unrealized_side_effect',
            suggestion: '点「改成只出文案」',
          },
        ],
      },
    });
    const mid = getPageData(route)!;
    expect(mid.skillId).toBe('demo_skill');
    expect(String(mid.issue0)).toMatch(/改成只出文案/);
    expect(mid.guideGlossary).toBe('Skill=可复用动作');

    reportPageData(route, { guideGlossary: 'Skill=可复用动作', totalSkills: 4 });
    const after = getPageData(route)!;
    expect(after.totalSkills).toBe(4);
    expect(after.skillId).toBe('demo_skill');
    expect(after.issue0).toBeTruthy();

    clearAssetAuditPageFields(route);
    const cleared = getPageData(route)!;
    expect(cleared.issue0).toBeUndefined();
    expect(cleared.guideGlossary).toBe('Skill=可复用动作');
    expect(pageDataToText(cleared)).toMatch(/guideGlossary/);
  });
});

describe('eval smoke page fields', () => {
  const route = '/eval';

  beforeEach(() => {
    (globalThis as any).window = (globalThis as any).window || {};
    (globalThis as any).window.__AIPLAT_PAGE_DATA__ = {};
  });

  afterEach(() => {
    clearPageData(route);
  });

  it('preserves smokeIssue* across EvalCenter reportPageData refresh', () => {
    reportPageData(route, { selectedTab: 'agents', pending: 10 });
    patchPageData(route, {
      smokeSummary: 'fail=1,warn=2',
      smokeIssue0: 'fail|task_result|任务结果|原因:未完成|对策:去单卷|卷:default/normal',
      smokeHint: '按 smokeIssue* 答',
    });
    reportPageData(route, { selectedTab: 'agents', pending: 11 });
    const after = getPageData(route)!;
    expect(after.pending).toBe(11);
    expect(after.smokeIssue0).toMatch(/task_result/);
    expect(pageDataToText(after)).toMatch(/smokeIssue0/);

    clearSmokeEvalPageFields(route);
    const cleared = getPageData(route)!;
    expect(cleared.smokeIssue0).toBeUndefined();
    expect(cleared.selectedTab).toBe('agents');
  });
});
