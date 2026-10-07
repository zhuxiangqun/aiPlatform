import { describe, expect, it } from 'vitest';
import { formatAuditIssueForPage } from './pageDataBridge';

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
