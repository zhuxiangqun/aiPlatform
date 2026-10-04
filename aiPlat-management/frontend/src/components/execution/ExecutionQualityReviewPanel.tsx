import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Button } from '../ui';

export type ExecutionQualityFix = {
  type?: string;
  fix_id?: string;
  issue_code?: string;
  auto_applicable?: boolean;
  title?: string;
};

export type ExecutionQualityIssue = {
  code?: string;
  severity?: string;
  message: string;
  suggestion?: string;
  where?: string;
  where_label?: string;
  how?: string;
  fix_available?: boolean;
  fix?: ExecutionQualityFix;
};

export type ExecutionQualityReview = {
  ok?: boolean;
  runtime_ok?: boolean;
  verdict?: 'pass' | 'warn' | 'fail' | string;
  headline?: string;
  issues?: ExecutionQualityIssue[];
  summary?: {
    errors?: number;
    warnings?: number;
    info?: number;
    total?: number;
    health?: string;
  };
  fix_guide?: {
    primary_where?: string;
    primary_label?: string;
    primary_how?: string;
    steps?: string[];
  };
  fixable_issue_codes?: string[];
  /** Backend-chosen CTA: rerun when SOP iron already present; else apply_sop_fix / check_runtime */
  primary_action?: 'rerun_with_fail_constraints' | 'apply_sop_fix' | 'check_runtime' | string;
  sop_iron?: {
    present_codes?: string[];
    missing_codes?: string[];
    all_present?: boolean;
    skill_ids?: string[];
  };
  /** Text to inject into next same-case run when primary_action is rerun_with_fail_constraints */
  rerun_constraint_overlay?: string;
};

type Props = {
  review: ExecutionQualityReview | null | undefined;
  loading?: boolean;
  /** Open Skill/Agent editor focused on SOP. */
  onEditSop?: () => void;
  /** One-click: write SOP iron-laws for given issue codes. */
  onApplyQualityFix?: (issueCodes: string[]) => Promise<void> | void;
  /** Parent confirms SOP write (or noop-already-present); show re-run CTA in-panel. */
  fixApplied?: boolean;
  /** Re-run the same input after SOP write — must work inside fullscreen flow too. */
  onRerunSameCase?: () => void;
  rerunLoading?: boolean;
  /**
   * Initial expand state. Default: pass → expanded (short); fail/warn → collapsed
   * so the execution graph keeps most of the viewport.
   */
  defaultExpanded?: boolean;
  /** sessionStorage key suffix for remember expand + detail height (optional). */
  persistKey?: string;
};

const DETAIL_H_MIN = 96;
const DETAIL_H_MAX = 480;
const DETAIL_H_DEFAULT = 180;
const STORAGE_PREFIX = 'aiplat.eq_panel.';

function collectFixableCodes(review: ExecutionQualityReview, issues: ExecutionQualityIssue[]): string[] {
  const fromIssues = issues
    .filter((i) => i.fix_available !== false && (i.fix || i.fix_available) && i.code)
    .map((i) => String(i.code));
  const fromTop = (review.fixable_issue_codes || []).map(String).filter(Boolean);
  return Array.from(new Set([...fromTop, ...fromIssues].filter(Boolean)));
}

const ARCH_QUALITY_CODES = new Set([
  'architecture_sections_thin',
  'public_cloud_photo_storage',
  'invented_third_party_api',
  'architecture_template_echo',
]);

function readPersist(key: string | undefined): { expanded?: boolean; detailH?: number } {
  if (!key || typeof sessionStorage === 'undefined') return {};
  try {
    const raw = sessionStorage.getItem(STORAGE_PREFIX + key);
    if (!raw) return {};
    const o = JSON.parse(raw);
    return {
      expanded: typeof o?.expanded === 'boolean' ? o.expanded : undefined,
      detailH: typeof o?.detailH === 'number' ? o.detailH : undefined,
    };
  } catch {
    return {};
  }
}

function writePersist(key: string | undefined, patch: { expanded?: boolean; detailH?: number }) {
  if (!key || typeof sessionStorage === 'undefined') return;
  try {
    const prev = readPersist(key);
    sessionStorage.setItem(STORAGE_PREFIX + key, JSON.stringify({ ...prev, ...patch }));
  } catch {
    /* ignore quota / private mode */
  }
}

/** Post-run content-quality panel: collapsible + drag-resizable detail body. */
const ExecutionQualityReviewPanel: React.FC<Props> = ({
  review,
  loading,
  onEditSop,
  onApplyQualityFix,
  fixApplied = false,
  onRerunSameCase,
  rerunLoading = false,
  defaultExpanded,
  persistKey = 'default',
}) => {
  const rootRef = useRef<HTMLDivElement>(null);
  const [applying, setApplying] = useState(false);
  const [localApplied, setLocalApplied] = useState(false);
  const [appliedCodes, setAppliedCodes] = useState<string[]>([]);
  const [expanded, setExpanded] = useState(false);
  const [detailH, setDetailH] = useState(DETAIL_H_DEFAULT);
  const lastReviewKeyRef = useRef('');
  const dragRef = useRef<{ startY: number; startH: number } | null>(null);

  // New review resets write state; expand prefers session persist → prop → auto
  useEffect(() => {
    if (!review) return;
    const key = `${review.verdict}|${review.headline}|${(review.issues || []).length}`;
    if (key === lastReviewKeyRef.current) return;
    lastReviewKeyRef.current = key;
    setLocalApplied(false);
    setAppliedCodes([]);
    const saved = readPersist(persistKey);
    if (typeof saved.detailH === 'number') {
      setDetailH(Math.min(DETAIL_H_MAX, Math.max(DETAIL_H_MIN, saved.detailH)));
    }
    if (typeof saved.expanded === 'boolean') {
      setExpanded(saved.expanded);
      return;
    }
    const v = String(review.verdict || (review.ok ? 'pass' : 'fail'));
    const autoExpand =
      defaultExpanded !== undefined
        ? defaultExpanded
        : v === 'pass' || (!(review.issues || []).length && v !== 'fail' && v !== 'warn');
    setExpanded(autoExpand);
  }, [review, defaultExpanded, persistKey]);

  const setExpandedPersist = useCallback(
    (next: boolean | ((prev: boolean) => boolean)) => {
      setExpanded((prev) => {
        const v = typeof next === 'function' ? next(prev) : next;
        writePersist(persistKey, { expanded: v });
        return v;
      });
    },
    [persistKey],
  );

  const onResizePointerDown = useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault();
      e.stopPropagation();
      (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
      dragRef.current = { startY: e.clientY, startH: detailH };
    },
    [detailH],
  );

  const onResizePointerMove = useCallback((e: React.PointerEvent) => {
    if (!dragRef.current) return;
    const dy = e.clientY - dragRef.current.startY;
    const next = Math.min(DETAIL_H_MAX, Math.max(DETAIL_H_MIN, dragRef.current.startH + dy));
    setDetailH(next);
  }, []);

  const onResizePointerUp = useCallback(
    (e: React.PointerEvent) => {
      if (!dragRef.current) return;
      dragRef.current = null;
      try {
        (e.target as HTMLElement).releasePointerCapture?.(e.pointerId);
      } catch {
        /* ignore */
      }
      setDetailH((h) => {
        writePersist(persistKey, { detailH: h });
        return h;
      });
    },
    [persistKey],
  );

  if (loading) {
    return (
      <div className="rounded-lg border border-dark-border/60 bg-dark-card/40 px-3 py-2 text-xs text-gray-400">
        正在对照产物做质量复核…
      </div>
    );
  }
  if (!review) return null;

  const verdict = String(review.verdict || (review.ok ? 'pass' : 'fail'));
  const borderCls =
    verdict === 'pass'
      ? 'border-green-500/30 bg-green-900/10'
      : verdict === 'warn'
        ? 'border-amber-500/30 bg-amber-900/10'
        : 'border-orange-500/35 bg-orange-950/20';

  const issues = review.issues || [];
  const guide = review.fix_guide;
  const needsAction = verdict === 'fail' || verdict === 'warn' || issues.length > 0;
  const uniqueFixable = collectFixableCodes(review, issues);
  const missingIron = (review.sop_iron?.missing_codes || []).map(String).filter(Boolean);
  const presentIron = (review.sop_iron?.present_codes || []).map(String).filter(Boolean);
  const archIssue = issues.some((i) => ARCH_QUALITY_CODES.has(String(i.code || '')));
  const ironAlreadyPresent = Boolean(
    review.primary_action === 'rerun_with_fail_constraints' ||
      (review.sop_iron?.all_present && uniqueFixable.length > 0) ||
      (presentIron.length > 0 && missingIron.length === 0) ||
      (archIssue && missingIron.length === 0),
  );
  // Only offer one-click write when markers are still missing (or unknown / no probe).
  const applyCodes =
    missingIron.length > 0
      ? uniqueFixable.filter((c) => missingIron.includes(c))
      : ironAlreadyPresent
        ? []
        : uniqueFixable;
  const canApply = Boolean(onApplyQualityFix) && applyCodes.length > 0;
  const showFixDone = Boolean(fixApplied || localApplied);
  const preferRerun =
    Boolean(onRerunSameCase) &&
    needsAction &&
    (ironAlreadyPresent || showFixDone || archIssue || canApply) &&
    review.primary_action !== 'check_runtime';
  const emptyOrTimeout = issues.some((i) =>
    ['empty_output', 'runtime_timeout', 'runtime_failed'].includes(String(i.code || '')),
  );
  const isRuntimeCheck =
    review.primary_action === 'check_runtime' || emptyOrTimeout;
  const headline =
    review.headline ||
    (verdict === 'pass'
      ? '流程完成且未发现明显质量问题'
      : '流程可以完成，但产物未达可验收标准——展开查看问题点与改 SOP 指引');

  const runApply = async (codes: string[]) => {
    if (!onApplyQualityFix) return;
    const list = (codes || []).map(String).filter(Boolean);
    if (!list.length) return;
    try {
      setApplying(true);
      await onApplyQualityFix(list);
      setLocalApplied(true);
      setAppliedCodes((prev) => Array.from(new Set([...prev, ...list])));
    } finally {
      setApplying(false);
    }
  };

  /** One click: write missing SOP iron (if any) then same-case fail-constraint rerun. */
  const runFixAndRerun = async () => {
    if (canApply && applyCodes.length) {
      await runApply(applyCodes);
    }
    onRerunSameCase?.();
  };

  const actionButtons = (
    <div className="flex items-center gap-1.5 shrink-0 flex-wrap justify-end relative z-20">
      {review.summary ? (
        <span className="text-[11px] text-gray-500 tabular-nums">
          {review.summary.errors || 0}错误 {review.summary.warnings || 0}警告
        </span>
      ) : issues.length > 0 ? (
        <span className="text-[11px] text-gray-500 tabular-nums">{issues.length} 项</span>
      ) : null}
      {preferRerun && onRerunSameCase ? (
        <Button
          type="button"
          variant="primary"
          size="sm"
          loading={rerunLoading || applying}
          disabled={applying && !canApply}
          title={
            canApply
              ? '写入缺失铁律（若有）→ 同一用例 + 失败点约束重跑'
              : '同一用例 + 失败点约束重跑（铁律已在，不改 SKILL.md）'
          }
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            void runFixAndRerun();
          }}
        >
          一键修复 → 同一用例重跑
        </Button>
      ) : null}
      {isRuntimeCheck && onRerunSameCase && !preferRerun ? (
        <Button
          type="button"
          variant="primary"
          size="sm"
          loading={rerunLoading}
          disabled={applying}
          title="空产物/超时与 SOP 无关：用同一用例重新执行"
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onRerunSameCase();
          }}
        >
          重新执行
        </Button>
      ) : null}
      {needsAction && canApply && !preferRerun && !isRuntimeCheck ? (
        <Button
          type="button"
          variant="primary"
          size="sm"
          loading={applying}
          title={`将 ${applyCodes.length} 类铁律写入 SKILL.md`}
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            void runApply(applyCodes);
          }}
        >
          一键修复 SOP（{applyCodes.length}）
        </Button>
      ) : null}
      {needsAction && canApply && preferRerun && !isRuntimeCheck ? (
        <Button
          type="button"
          variant="secondary"
          size="sm"
          loading={applying}
          title="只写 SOP，不立刻重跑"
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            void runApply(applyCodes);
          }}
        >
          仅写入 SOP
        </Button>
      ) : null}
      {needsAction && onEditSop && !isRuntimeCheck ? (
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onEditSop();
          }}
          disabled={applying}
        >
          去改 SOP
        </Button>
      ) : null}
      <button
        type="button"
        className="text-[11px] text-gray-400 hover:text-gray-200 px-1.5 py-1 rounded border border-dark-border/60 hover:border-dark-border bg-dark-bg/40"
        aria-expanded={expanded}
        title={expanded ? '收起详情' : '展开详情'}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setExpandedPersist((v) => !v);
        }}
      >
        {expanded ? '收起 ▴' : '展开 ▾'}
      </button>
    </div>
  );

  return (
    <div
      ref={rootRef}
      className={`rounded-lg border text-xs ${borderCls} relative z-10 ${expanded ? 'p-3 pb-1 space-y-2' : 'px-3 py-2'}`}
      data-testid="execution-quality-review"
      data-expanded={expanded ? '1' : '0'}
    >
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <button
          type="button"
          className="min-w-0 flex-1 text-left group"
          onClick={() => setExpandedPersist((v) => !v)}
          title={expanded ? '收起' : '展开详情'}
        >
          <div className="text-sm font-medium text-gray-100 flex items-center gap-1.5">
            <span>{verdict === 'pass' ? '✅' : verdict === 'warn' ? '⚠️' : '❌'}</span>
            <span>产物质量复核</span>
            {review.summary?.health ? (
              <span className="text-[11px] font-normal text-gray-500">({review.summary.health})</span>
            ) : null}
          </div>
          {!expanded ? (
            <div className="text-[11px] text-gray-400 mt-0.5 leading-snug line-clamp-1 group-hover:text-gray-300">
              {headline}
            </div>
          ) : null}
        </button>
        {actionButtons}
      </div>

      {expanded ? (
        <>
          <div className="space-y-2 overflow-y-auto pr-0.5" style={{ maxHeight: detailH }}>
            <div className="text-[11px] text-gray-400 leading-relaxed">{headline}</div>

            {needsAction && ironAlreadyPresent ? (
              <div className="rounded border border-sky-500/30 bg-sky-950/25 px-2.5 py-2 flex items-center justify-between gap-2 flex-wrap">
                <div className="text-[11px] text-sky-100/90 leading-relaxed min-w-0 flex-1">
                  相关 SOP 铁律<strong>已在</strong> Skill/Agent 中；再点「仅写入 SOP」多为幂等 noop。
                  本轮答卷仍不合格——请点右上角「一键修复 → 同一用例重跑」（注入失败约束，不改 SKILL.md）。
                </div>
                {/* Header already has the primary CTA when preferRerun — avoid a second identical button. */}
                {!preferRerun && onRerunSameCase ? (
                  <Button
                    type="button"
                    variant="primary"
                    size="sm"
                    loading={rerunLoading || applying}
                    disabled={applying}
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      void runFixAndRerun();
                    }}
                  >
                    一键修复 → 同一用例重跑
                  </Button>
                ) : !preferRerun && !onRerunSameCase ? (
                  <span className="text-[10px] text-sky-200/70 shrink-0">请关闭全屏后点「执行」并自行追加失败约束</span>
                ) : null}
              </div>
            ) : null}

            {needsAction && !canApply && !ironAlreadyPresent && !isRuntimeCheck ? (
              <div className="text-[11px] text-amber-200/85 rounded border border-amber-500/25 bg-amber-950/20 px-2 py-1.5">
                {!onApplyQualityFix
                  ? '一键修复未接线：请点「去改 SOP」打开编辑页，或到对应 Skill 执行弹窗使用一键修复。'
                  : '这些问题暂无自动补丁：请点「去改 SOP」按下方「改哪里 / 怎么改」手工加固后重跑。'}
              </div>
            ) : null}

            {needsAction && emptyOrTimeout ? (
              <div className="text-[11px] text-amber-100/90 rounded border border-amber-500/30 bg-amber-950/25 px-2.5 py-2 space-y-1">
                <div>
                  空输出 / 超时与 SOP 铁律无关——请看执行轨迹是否已调用 Skill、是否卡在 LLM。
                  勿点「一键修复 SOP」或「去改 SOP」。
                </div>
                {onRerunSameCase ? (
                  <div className="flex justify-end">
                    <Button
                      type="button"
                      variant="primary"
                      size="sm"
                      loading={rerunLoading}
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        onRerunSameCase();
                      }}
                    >
                      重新执行
                    </Button>
                  </div>
                ) : null}
              </div>
            ) : null}

            {showFixDone && !ironAlreadyPresent ? (
              <div className="rounded border border-emerald-500/30 bg-emerald-950/25 px-2.5 py-2 flex items-center justify-between gap-2 flex-wrap">
                <div className="text-[11px] text-emerald-100/90 leading-relaxed min-w-0 flex-1">
                  SOP 铁律已写入。上方红灯仍是本轮旧产物——不会自动变绿，
                  {preferRerun
                    ? '请点右上角「一键修复 → 同一用例重跑」。'
                    : '请点下方「一键修复 → 同一用例重跑」。'}
                </div>
                {/* Only show inline CTA when header does not already expose the same primary action. */}
                {!preferRerun && onRerunSameCase ? (
                  <Button
                    type="button"
                    variant="primary"
                    size="sm"
                    loading={rerunLoading || applying}
                    disabled={applying}
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      void runFixAndRerun();
                    }}
                  >
                    一键修复 → 同一用例重跑
                  </Button>
                ) : !preferRerun && !onRerunSameCase ? (
                  <span className="text-[10px] text-emerald-200/70 shrink-0">请关闭全屏后点「执行」重跑</span>
                ) : null}
              </div>
            ) : null}

            {needsAction && guide ? (
              <div className="rounded border border-sky-500/25 bg-sky-950/20 px-2.5 py-2 space-y-1">
                <div className="text-[11px] font-medium text-sky-200/90">改哪里 / 怎么改</div>
                {guide.primary_label ? (
                  <div className="text-[11px] text-gray-300">
                    <span className="text-gray-500">位置：</span>
                    <span className="text-sky-300/90">{guide.primary_label}</span>
                  </div>
                ) : null}
                {guide.primary_how ? (
                  <div className="text-[11px] text-gray-400 leading-relaxed">{guide.primary_how}</div>
                ) : null}
                {(guide.steps || []).length > 0 ? (
                  <ol className="list-decimal list-inside space-y-0.5 text-[11px] text-gray-400 pt-0.5">
                    {guide.steps!.map((s, i) => (
                      <li key={i} className="leading-relaxed">
                        {s.replace(/^\d+\.\s*/, '')}
                      </li>
                    ))}
                  </ol>
                ) : null}
              </div>
            ) : null}

            {issues.length > 0 ? (
              <div className="space-y-2 pt-1">
                <div className="text-[11px] font-medium text-gray-300">问题点（{issues.length}）</div>
                {issues.map((issue, idx) => {
                  const code = issue.code ? String(issue.code) : '';
                  const ironPresentForRow = Boolean(
                    code && (review.sop_iron?.present_codes || []).map(String).includes(code),
                  );
                  const rowWrote =
                    Boolean(code && appliedCodes.includes(code)) || showFixDone || ironPresentForRow;
                  const rowFixable = Boolean(
                    onApplyQualityFix &&
                      code &&
                      (issue.fix_available || issue.fix) &&
                      !ironPresentForRow,
                  );
                  return (
                    <div
                      key={`${code || 'q'}-${idx}`}
                      className={`flex gap-2 py-1.5 ${
                        idx < issues.length - 1 ? 'border-b border-dark-border/30' : ''
                      }`}
                    >
                      <span className="mt-0.5 shrink-0">
                        {issue.severity === 'error' ? '❌' : issue.severity === 'warning' ? '⚠️' : 'ℹ️'}
                      </span>
                      <div className="flex-1 min-w-0 space-y-1">
                        <div className="text-gray-200">{issue.message}</div>
                        {issue.suggestion ? (
                          <div className="text-gray-500">建议：{issue.suggestion}</div>
                        ) : null}
                        {(issue.where_label || issue.how) && (
                          <div className="rounded border border-dark-border/50 bg-dark-bg/50 px-2 py-1.5 text-[11px] text-gray-400 space-y-0.5">
                            {issue.where_label ? (
                              <div>
                                <span className="text-gray-500">改哪里：</span>
                                <span className="text-sky-300/90">{issue.where_label}</span>
                              </div>
                            ) : null}
                            {issue.how ? (
                              <div>
                                <span className="text-gray-500">怎么改：</span>
                                {issue.how}
                              </div>
                            ) : null}
                          </div>
                        )}
                      </div>
                      {rowFixable ? (
                        <Button
                          type="button"
                          variant="secondary"
                          size="sm"
                          className="text-[10px] py-0 px-2 h-6 whitespace-nowrap shrink-0 relative z-20"
                          loading={applying}
                          onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            void runApply([code]);
                          }}
                        >
                          {issue.fix?.title ? `写入·${issue.fix.title}` : '写入 SOP'}
                        </Button>
                      ) : rowWrote || ironPresentForRow ? (
                        <span className="text-[10px] text-emerald-300/85 whitespace-nowrap shrink-0 py-0.5">
                          {ironPresentForRow ? '铁律已在' : '已写入 SOP'}
                        </span>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            ) : needsAction ? (
              <div className="text-[11px] text-amber-200/80">
                未列出细则问题，但仍建议按上方指引检查 SOP / 输出铁律后重跑同一用例。
              </div>
            ) : null}
          </div>
          {/* Drag handle — stretch detail height */}
          <div
            role="separator"
            aria-orientation="horizontal"
            aria-label="拖动调整质量复核高度"
            title="拖动调整高度"
            className="h-3 flex items-center justify-center cursor-row-resize select-none touch-none group"
            onPointerDown={onResizePointerDown}
            onPointerMove={onResizePointerMove}
            onPointerUp={onResizePointerUp}
            onPointerCancel={onResizePointerUp}
          >
            <div className="w-10 h-1 rounded-full bg-dark-border group-hover:bg-gray-400 transition-colors" />
          </div>
        </>
      ) : null}
    </div>
  );
};

export default ExecutionQualityReviewPanel;
