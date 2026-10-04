import React, { useEffect, useMemo, useState } from 'react';
import { Button } from '../ui';

export type AssetAuditIssue = {
  severity: string;
  category: string;
  field?: string;
  current?: string;
  message: string;
  suggestion?: string;
  fix_available?: boolean;
  fix?: { type: string; [k: string]: unknown };
  create_brief?: {
    where?: string;
    must_have?: string;
    [k: string]: unknown;
  };
};

export type AssetAuditResult = {
  issues?: AssetAuditIssue[];
  summary?: {
    errors?: number;
    warnings?: number;
    info?: number;
    total?: number;
    health?: string;
    fixable?: number;
    unfixable?: number;
  };
};

/** Toast copy after one-click apply + re-audit. */
export function auditRemainToast(
  applied: number,
  summary?: AssetAuditResult['summary'] | null,
): { kind: 'success' | 'info'; text: string } {
  const left = Number(summary?.errors || 0) + Number(summary?.warnings || 0);
  const leftManual = Number(summary?.unfixable || 0);
  if (left <= 0) {
    return { kind: 'success', text: applied > 0 ? '一键修复完成，审核已通过' : '审核已通过' };
  }
  return {
    kind: 'info',
    text:
      `已应用 ${applied} 项；仍剩 ${left} 项问题` +
      (leftManual > 0 ? `（${leftManual} 项需手工）` : '（可再点一键修复）'),
  };
}

type Props = {
  result: AssetAuditResult | null;
  loading?: boolean;
  onAudit: () => void;
  onApplyFix?: (fix: NonNullable<AssetAuditIssue['fix']>) => void;
  onApplyAll?: () => void;
  fixLabel?: (fix: NonNullable<AssetAuditIssue['fix']>) => string;
  auditButtonLabel?: string;
  /** Hide the built-in audit button (caller already has one in footer). */
  hideAuditButton?: boolean;
};

const SEV_RANK: Record<string, number> = { error: 0, warning: 1, info: 2 };

function isPassInfo(issue: AssetAuditIssue): boolean {
  const c = String(issue.category || '');
  return (
    issue.severity === 'info' &&
    (c.endsWith('_binding_ok') ||
      c === 'engine_skill_binding' ||
      c === 'sop_content_ok' ||
      c === 'prompt_md_ok' ||
      c === 'audit_draft_sop' ||
      c === 'model_auto' ||
      c === 'missing_skill_model_purpose')
  );
}

const AssetAuditPanel: React.FC<Props> = ({
  result,
  loading,
  onAudit,
  onApplyFix,
  onApplyAll,
  fixLabel,
  auditButtonLabel = '🔍 AI 审核',
  hideAuditButton = false,
}) => {
  const health = result?.summary?.health || '?';
  const borderCls =
    health === 'A'
      ? 'border-emerald-500/30 bg-emerald-900/10'
      : health === 'B'
        ? 'border-sky-500/30 bg-sky-900/10'
        : 'border-amber-500/30 bg-amber-900/10';

  const labelFor = (fix: NonNullable<AssetAuditIssue['fix']>) => {
    if (fixLabel) return fixLabel(fix);
    if (fix.type === 'apply_lint_fix') return '应用';
    if (fix.type === 'set_model') return `模型 → ${fix.model}`;
    if (fix.type === 'set_description') return '补描述';
    if (fix.type === 'set_parameters') return '补参数 schema';
    if (fix.type === 'set_display_name') return '补显示名';
    if (fix.type === 'set_allowed_tools') return '写入工具白名单';
    if (fix.type === 'set_agent_type') return `类型 → ${fix.agent_type}`;
    if (fix.type === 'set_transport') return `transport → ${fix.transport}`;
    if (fix.type === 'set_status') return `状态 → ${fix.status}`;
    if (fix.type === 'set_name') return `名称 → ${fix.name}`;
    if (fix.type === 'set_url') return '补 URL';
    if (fix.type === 'set_command') return '补 command';
    if (fix.type === 'remove_mcp') return '解绑 MCP';
    if (fix.type === 'remove_agent') return '解绑子Agent';
    if (fix.type === 'remove_workflow') return '解绑 Workflow';
    if (fix.type === 'remove_skill') return '移除技能';
    if (fix.type === 'remove_tool') return '移除工具';
    if (fix.type === 'set_loop_type') return `策略 → ${fix.loop_type}`;
    if (fix.type === 'set_permissions') return '补权限';
    if (fix.type === 'set_toolset') return `Toolset → ${fix.toolset}`;
    if (fix.type === 'set_skill_model_purpose') return `purpose → ${fix.purpose}`;
    if (fix.type === 'set_system_prompt') return '补 System Prompt';
    if (fix.type === 'set_kb_collection') return '设置知识库';
    if (fix.type === 'replace_tool') return `替换 → ${fix.to}`;
    if (fix.type === 'add_skill') return `+${fix.skill}`;
    if (fix.type === 'append_sop_skill_refs') return '追加 Skill 附录';
    if (fix.type === 'append_sop_appendix') {
      return String(fix.label || '').trim() || '追加 SOP 附录';
    }
    return '修复';
  };

  const { actionIssues, passIssues } = useMemo(() => {
    const all = [...(result?.issues || [])].sort(
      (a, b) => (SEV_RANK[a.severity] ?? 9) - (SEV_RANK[b.severity] ?? 9),
    );
    const pass: AssetAuditIssue[] = [];
    const action: AssetAuditIssue[] = [];
    for (const i of all) {
      if (isPassInfo(i)) pass.push(i);
      else action.push(i);
    }
    return { actionIssues: action, passIssues: pass };
  }, [result?.issues]);

  const [passOpen, setPassOpen] = useState(false);
  // When only pass infos (health A), auto-expand so "通过也可见"
  React.useEffect(() => {
    if (result && actionIssues.length === 0 && passIssues.length > 0) {
      setPassOpen(true);
    } else {
      setPassOpen(false);
    }
  }, [result, actionIssues.length, passIssues.length]);
  const unfixable = Number(result?.summary?.unfixable || 0);
  const fixableCount = (result?.issues || []).filter((i) => i.fix_available && i.fix).length;

  const renderIssue = (issue: AssetAuditIssue, idx: number, list: AssetAuditIssue[]) => (
    <div
      key={`${issue.category}-${idx}-${issue.current || ''}`}
      className={`flex gap-2 py-1.5 ${idx < list.length - 1 ? 'border-b border-dark-border/30' : ''}`}
    >
      <span className="mt-0.5 shrink-0">
        {issue.severity === 'error' ? '❌' : issue.severity === 'warning' ? '⚠️' : 'ℹ️'}
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex flex-wrap items-center gap-1.5 mb-0.5">
          {issue.field ? (
            <span className="text-[10px] px-1.5 py-0.5 rounded border border-dark-border text-gray-500 font-mono">
              {issue.field}
            </span>
          ) : null}
          {issue.category ? (
            <span className="text-[10px] text-gray-600 font-mono truncate max-w-[14rem]" title={issue.category}>
              {issue.category}
            </span>
          ) : null}
        </div>
        <div className="text-gray-300 leading-relaxed">{issue.message}</div>
        {issue.suggestion ? (
          <div className="text-gray-500 mt-0.5 leading-relaxed whitespace-pre-wrap">{issue.suggestion}</div>
        ) : null}
        {issue.create_brief?.must_have ? (
          <div className="mt-1 text-[10px] text-amber-200/80 whitespace-pre-wrap border-l border-amber-500/40 pl-2">
            <div className="text-amber-300/90 mb-0.5">
              建议到{issue.create_brief.where || '对应库'}新建后再绑定
            </div>
            <div>应具备：{issue.create_brief.must_have}</div>
          </div>
        ) : null}
      </div>
      {issue.fix_available && issue.fix && onApplyFix ? (
        <Button
          variant="secondary"
          size="sm"
          className="text-[10px] py-0 px-2 h-6 whitespace-nowrap shrink-0"
          onClick={() => onApplyFix(issue.fix!)}
        >
          {labelFor(issue.fix)}
        </Button>
      ) : null}
    </div>
  );

  return (
    <div className="space-y-2">
      {!hideAuditButton ? (
        <div className="flex items-center gap-2">
          <Button variant="secondary" size="sm" onClick={onAudit} loading={!!loading}>
            {auditButtonLabel}
          </Button>
          {result?.summary ? (
            <span className="text-[11px] text-gray-500">
              {result.summary.errors || 0}错误 {result.summary.warnings || 0}警告{' '}
              {result.summary.info || 0}提示
              {unfixable > 0 ? ` · ${unfixable}项需手工` : ''}
            </span>
          ) : null}
        </div>
      ) : null}
      {result && (
        <div className={`rounded-xl border p-3 space-y-2 text-xs ${borderCls}`}>
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <span className="text-sm font-medium text-gray-200">
              审核结果
              <span className="ml-1.5 font-mono text-[11px] text-gray-400">({health})</span>
            </span>
            <span className="text-[11px] text-gray-500">
              {result.summary?.errors || 0}错误 · {result.summary?.warnings || 0}警告 ·{' '}
              {result.summary?.info || 0}提示
            </span>
          </div>

          {actionIssues.length === 0 && passIssues.length > 0 ? (
            <div className="text-[11px] text-emerald-200/80 leading-relaxed">
              无阻断项。下方为已检查通过的绑定摘要（可展开）。
            </div>
          ) : null}

          {actionIssues.length > 0 ? (
            <div className="space-y-0">{actionIssues.map((i, idx) => renderIssue(i, idx, actionIssues))}</div>
          ) : null}

          {passIssues.length > 0 ? (
            <div className="rounded-lg border border-dark-border/60 bg-dark-bg/30 overflow-hidden">
              <button
                type="button"
                className="w-full flex items-center justify-between px-2.5 py-1.5 text-[11px] text-gray-400 hover:text-gray-200"
                onClick={() => setPassOpen((v) => !v)}
              >
                <span>已通过检查（{passIssues.length}）</span>
                <span>{passOpen ? '收起' : '展开'}</span>
              </button>
              {passOpen ? (
                <div className="px-2.5 pb-2 border-t border-dark-border/40">
                  {passIssues.map((i, idx) => renderIssue(i, idx, passIssues))}
                </div>
              ) : null}
            </div>
          ) : null}

          {onApplyAll && fixableCount > 0 ? (
            <div className="mt-1 pt-2 border-t border-dark-border/30 flex items-center gap-2">
              <Button variant="primary" size="sm" onClick={onApplyAll}>
                ⚡ 一键修复 ({fixableCount}/{(result.issues || []).length})
              </Button>
              {unfixable > 0 ? (
                <span className="text-[10px] text-gray-500">
                  {unfixable} 项需手工（上架/连通/画布等）
                </span>
              ) : null}
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
};

export default AssetAuditPanel;
