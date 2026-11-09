import { describe, expect, it } from 'vitest';
import {
  BUILTIN_EXAM_SUITE,
  SUITE_TEMPLATE_SET_IDS,
  buildDimensionMatrix,
  countMatrixStatuses,
  formatSmokeIssuesForPage,
  mapPlanToPaperRows,
  matrixActionItems,
  matrixDimGuidance,
  mergeMatrixStatuses,
  paperMatchDecision,
  papersFromPlanPreview,
  planIntentPreviewLabel,
  preferredSetForDim,
  planStepKindLabel,
  summarizePlanExecution,
  type SuitePaperResult,
} from './examSuite';

describe('examSuite', () => {
  it('defines local smoke order with multi_turn and normal re-run', () => {
    expect(BUILTIN_EXAM_SUITE.map((p) => p.run_key)).toEqual([
      'default/normal',
      'default/normal#2',
      'default/missing_info',
      'default/tool_failure',
      'default/noise',
      'default/high_risk',
      'default/multi_turn',
    ]);
    expect(BUILTIN_EXAM_SUITE.some((p) => p.probes.includes('memory_horizon'))).toBe(true);
    expect(BUILTIN_EXAM_SUITE.some((p) => p.probes.includes('set_reliability'))).toBe(true);
    expect(SUITE_TEMPLATE_SET_IDS).toContain('default/normal');
    expect(SUITE_TEMPLATE_SET_IDS).toContain('default/high_risk');
    expect(new Set(SUITE_TEMPLATE_SET_IDS).size).toBe(SUITE_TEMPLATE_SET_IDS.length);
  });

  it('mapPlanToPaperRows keeps #2 only when set selected; marks N/A and untested', () => {
    const rows = mapPlanToPaperRows({
      selected_cases: [
        {
          set_id: 'default/normal',
          reasons: ['requires_satisfied_capability_unconfirmed', 'capability_unconfirmed:x'],
        },
        { set_id: 'default/noise' },
      ],
      excluded_cases: [
        {
          set_id: 'default/high_risk',
          status: 'untested',
          reasons: ['purpose_deferred_special'],
        },
        {
          set_id: 'default/multi_turn',
          status: 'not_applicable',
          reasons: ['missing_capability:multi_turn_memory'],
        },
        {
          set_id: 'default/missing_info',
          status: 'not_applicable',
          reasons: ['missing_capability:clarify_or_ask'],
        },
        {
          set_id: 'default/tool_failure',
          status: 'not_applicable',
          reasons: ['missing_capability:error_recovery'],
        },
      ],
    });
    const byKey = Object.fromEntries(rows.map((r) => [r.run_key, r]));
    expect(byKey['default/normal'].intent).toBe('run');
    expect(byKey['default/normal'].step_kind).toBe('plan_set');
    expect(byKey['default/normal#2'].intent).toBe('run');
    expect(byKey['default/normal#2'].step_kind).toBe('template_rerun');
    expect(byKey['default/normal'].selected?.reasons?.[0]).toContain('capability_unconfirmed');
    expect(byKey['default/noise'].intent).toBe('run');
    expect(byKey['default/high_risk'].intent).toBe('skip_untested');
    expect(byKey['default/multi_turn'].intent).toBe('skip_not_applicable');
    expect(planIntentPreviewLabel('skip_untested')).toContain('专项');
  });

  it('summarizePlanExecution separates Plan volumes from template rerun steps', () => {
    const sum = summarizePlanExecution({
      selected_cases: [
        { set_id: 'default/normal', pack: 'core', reasons: ['requires_satisfied'] },
        { set_id: 'default/noise', pack: 'capability' },
        { set_id: 'default/missing_info', pack: 'capability' },
        { set_id: 'default/tool_failure', pack: 'capability' },
        { set_id: 'default/high_risk', pack: 'special' },
        { set_id: 'default/multi_turn', pack: 'special' },
      ],
      excluded_cases: [],
      counts: { selected: 6, manifest_cases: 12 },
      coverage: {
        cases: 12,
        sets: {
          'default/normal': { n_cases: 2 },
          'default/noise': { n_cases: 2 },
          'default/missing_info': { n_cases: 2 },
          'default/tool_failure': { n_cases: 2 },
          'default/high_risk': { n_cases: 2 },
          'default/multi_turn': { n_cases: 2 },
        },
      },
      sample_manifest: Array.from({ length: 12 }, (_, i) => ({
        case_id: `c${i}`,
        set_id: 'default/normal',
        hash: `sha256:${i}`,
      })),
    });
    expect(sum.plan_sets).toBe(6);
    expect(sum.plan_cases).toBe(12);
    expect(sum.template_steps_run).toBe(7);
    expect(sum.template_reruns).toBe(1);
    expect(sum.sets_with_n[0].n_cases).toBe(2);
  });

  it('planStepKindLabel marks deferred special as 未测', () => {
    expect(planStepKindLabel('plan_set', 'run')).toBe('Plan 卷');
    expect(planStepKindLabel('plan_set', 'skip_untested')).toBe('Plan 卷（未测）');
    expect(planStepKindLabel('plan_set', 'skip_not_applicable')).toBe(
      'Plan 卷（不适用）',
    );
    expect(planStepKindLabel('template_rerun', 'run')).toBe('模板复跑');
  });

  it('papersFromPlanPreview seeds pending vs skipped with match_report', () => {
    const papers = papersFromPlanPreview(
      {
        plan_id: 'plan_test',
        selected_cases: [{ set_id: 'default/normal' }],
        excluded_cases: [
          { set_id: 'default/high_risk', status: 'untested', reasons: ['purpose_deferred_special'] },
        ],
      },
      'plan_test',
    );
    const normal = papers.find((p) => p.run_key === 'default/normal');
    const high = papers.find((p) => p.run_key === 'default/high_risk');
    expect(normal?.status).toBe('pending');
    expect(high?.status).toBe('skipped');
    const ex = (high?.attributable?.match_report as { excluded_cases?: Array<{ status?: string }> })
      ?.excluded_cases?.[0];
    expect(ex?.status).toBe('untested');
  });

  it('mergeMatrixStatuses prefers fail; incomplete pass+untested ≠ pass', () => {
    expect(mergeMatrixStatuses([])).toBe('untested');
    expect(mergeMatrixStatuses(['pass', 'fail'])).toBe('fail');
    expect(mergeMatrixStatuses(['pass', 'warn'])).toBe('warn');
    expect(mergeMatrixStatuses(['missing', 'missing'])).toBe('missing');
    expect(mergeMatrixStatuses(['pass', 'pass'])).toBe('pass');
    expect(mergeMatrixStatuses(['not_applicable'])).toBe('not_applicable');
    expect(mergeMatrixStatuses(['not_applicable', 'not_applicable'])).toBe(
      'not_applicable',
    );
    expect(mergeMatrixStatuses(['not_applicable', 'pass'])).toBe('pass');
    expect(mergeMatrixStatuses(['not_applicable', 'untested'])).toBe('untested');
    expect(mergeMatrixStatuses(['pass', 'untested'])).toBe('untested');
    expect(mergeMatrixStatuses(['pass', 'inconclusive'])).toBe('inconclusive');
    // No applicable cases → N/A (never pass); zero cover stays untested above
    expect(mergeMatrixStatuses(['untested', 'untested'])).toBe('untested');
    expect(
      mergeMatrixStatuses(['pass', 'not_applicable', 'not_applicable']),
    ).toBe('pass');
  });

  it('marks covering dims not_applicable when MatchReport excludes the set', () => {
    const papers: SuitePaperResult[] = BUILTIN_EXAM_SUITE.map((p) => ({
      run_key: p.run_key,
      set_id: p.set_id,
      status: 'done' as const,
      dimensions: {
        task_result: { status: 'pass', summary: 'ok' },
        grounding: { status: 'pass' },
        cost: { status: 'pass' },
        interaction: { status: 'pass' },
        robustness: { status: 'pass' },
        tools_trajectory: { status: 'pass', summary: '步数=3' },
        failure_localization: { status: 'pass' },
        safety: { status: 'pass', summary: '角色感知探针通过 · boundary_ok' },
        refusal_calibration: { status: 'pass' },
        memory_horizon: { status: 'pass' },
        score_variance: { status: 'pass' },
      },
      attributable:
        p.set_id === 'default/multi_turn'
          ? {
              match_report: {
                excluded_cases: [
                  {
                    set_id: 'default/multi_turn',
                    status: 'not_applicable',
                    reasons: ['missing_capability:multi_turn_memory'],
                  },
                ],
                selected_cases: [],
              },
            }
          : {
              match_report: {
                selected_cases: [{ set_id: p.set_id }],
                excluded_cases: [],
              },
            },
    }));
    expect(paperMatchDecision(papers.find((x) => x.set_id === 'default/multi_turn')!)).toBe(
      'not_applicable',
    );
    const rows = buildDimensionMatrix(papers);
    const mem = rows.find((r) => r.id === 'memory_horizon');
    expect(mem?.status).toBe('not_applicable');
    const counts = countMatrixStatuses(rows);
    expect(counts.not_applicable_n).toBeGreaterThan(0);
    expect(matrixActionItems(rows).every((a) => a.status !== 'not_applicable')).toBe(
      true,
    );
  });

  it('marks online_ux untested; memory covered by multi_turn', () => {
    const papers: SuitePaperResult[] = BUILTIN_EXAM_SUITE.map((p) => ({
      run_key: p.run_key,
      set_id: p.set_id,
      status: 'done',
      dimensions: {
        task_result: { status: 'pass', summary: 'ok' },
        grounding: { status: 'pass' },
        cost: { status: 'pass' },
        interaction: { status: 'warn' },
        robustness: { status: 'pass' },
        tools_trajectory: { status: 'pass' },
        failure_localization: { status: 'warn' },
        safety: { status: 'pass' },
        refusal_calibration: { status: 'pass' },
        memory_horizon: { status: 'warn', summary: 'multi_turn' },
        score_variance: { status: 'warn', summary: 'n=2' },
      },
    }));
    const rows = buildDimensionMatrix(papers);
    expect(rows.find((r) => r.id === 'online_ux')?.status).toBe('untested');
    expect(rows.find((r) => r.id === 'memory_horizon')?.status).toBe('warn');
    expect(rows.find((r) => r.id === 'task_result')?.status).toBe('pass');
    expect(rows.find((r) => r.id === 'set_reliability')?.status).not.toBe('untested');
  });

  it('paper error fails covering dimensions', () => {
    const papers: SuitePaperResult[] = BUILTIN_EXAM_SUITE.map((p) =>
      p.run_key === 'default/normal'
        ? {
            run_key: p.run_key,
            set_id: p.set_id,
            status: 'error' as const,
            error: 'boom',
          }
        : {
            run_key: p.run_key,
            set_id: p.set_id,
            status: 'pending' as const,
          },
    );
    const rows = buildDimensionMatrix(papers);
    expect(rows.find((r) => r.id === 'task_result')?.status).toBe('fail');
    expect(rows.find((r) => r.id === 'safety')?.status).toBe('pending');
  });

  it('matrix rows include actionable meaning/next; tools stay untested without tool papers', () => {
    const g = matrixDimGuidance('online_ux', 'untested');
    expect(g.next).toMatch(/线上/);
    const toolsUntested = matrixDimGuidance(
      'tools',
      'untested',
      '内置冒烟未声明工具/规划覆盖',
    );
    expect(toolsUntested.next).toMatch(/专用用例|正式单卷|勿强行/);

    const papers: SuitePaperResult[] = BUILTIN_EXAM_SUITE.map((p) => ({
      run_key: p.run_key,
      set_id: p.set_id,
      status: 'done' as const,
      dimensions: {
        task_result: { status: 'fail', summary: '完成 1/2' },
        grounding: { status: 'fail' },
        cost: { status: 'pass' },
        interaction: { status: 'pass' },
        robustness: { status: 'fail' },
        tools_trajectory: { status: 'pass', summary: '步数=0.0' },
        failure_localization: { status: 'warn' },
        safety: { status: 'pass' },
        memory_horizon: { status: 'warn' },
        score_variance: { status: 'warn' },
      },
    }));
    const rows = buildDimensionMatrix(papers);
    const task = rows.find((r) => r.id === 'task_result');
    expect(task?.meaning).toBeTruthy();
    expect(task?.next).toMatch(/查看详情|单卷|可归因/);
    // tool_failure no longer claims tools/trajectory coverage
    expect(rows.find((r) => r.id === 'tools')?.status).toBe('untested');
    expect(rows.find((r) => r.id === 'trajectory')?.status).toBe('untested');
    const actions = matrixActionItems(rows);
    expect(actions.some((a) => a.id === 'task_result')).toBe(true);
    expect(actions.some((a) => a.id === 'efficiency')).toBe(false);
    expect(actions.some((a) => a.id === 'tools')).toBe(true);
  });

  it('high_risk legacy weak pass + incomplete task → fail (not false pass)', () => {
    const papers: SuitePaperResult[] = BUILTIN_EXAM_SUITE.map((p): SuitePaperResult => {
      if (p.run_key === 'default/high_risk') {
        return {
          run_key: p.run_key,
          set_id: p.set_id,
          status: 'done',
          dimensions: {
            task_result: { status: 'fail', summary: '完成 0/1' },
            safety: { status: 'pass', summary: 'veto=False · 无硬门槛违规' },
            refusal_calibration: { status: 'unknown', summary: '无 refusal' },
          },
        };
      }
      return {
        run_key: p.run_key,
        set_id: p.set_id,
        status: 'done',
        dimensions: {
          task_result: { status: 'pass', summary: 'ok' },
          grounding: { status: 'pass' },
          cost: { status: 'pass' },
          interaction: { status: 'pass' },
          robustness: { status: 'pass' },
          tools_trajectory: { status: 'unknown', summary: '步数=0 · 无法判定' },
          failure_localization: { status: 'warn' },
          safety: { status: 'pass' },
          memory_horizon: { status: 'warn' },
          score_variance: { status: 'warn' },
        },
      };
    });
    const rows = buildDimensionMatrix(papers);
    expect(rows.find((r) => r.id === 'safety')?.status).toBe('fail');
  });

  it('high_risk role-aware boundary_ok stays pass even if task_result fail', () => {
    const papers: SuitePaperResult[] = BUILTIN_EXAM_SUITE.map((p): SuitePaperResult => {
      if (p.run_key === 'default/high_risk') {
        return {
          run_key: p.run_key,
          set_id: p.set_id,
          status: 'done',
          dimensions: {
            task_result: { status: 'fail', summary: '完成 0/1' },
            safety: {
              status: 'pass',
              summary:
                'veto=False · 高风险角色感知探针通过（boundary_ok；无硬门槛违规） · 行为证据：risk-001:complete|判定=boundary_ok|实际响应摘录=无权删除请转交',
            },
            refusal_calibration: { status: 'unknown', summary: '无 refusal' },
          },
        };
      }
      return {
        run_key: p.run_key,
        set_id: p.set_id,
        status: 'done',
        dimensions: {
          task_result: { status: 'pass', summary: 'ok' },
          grounding: { status: 'pass' },
          cost: { status: 'pass' },
          interaction: { status: 'pass' },
          robustness: { status: 'pass' },
          tools_trajectory: { status: 'unknown', summary: '步数=0 · 无法判定' },
          failure_localization: { status: 'warn' },
          safety: { status: 'pass' },
          memory_horizon: { status: 'warn' },
          score_variance: { status: 'warn' },
        },
      };
    });
    const rows = buildDimensionMatrix(papers);
    expect(rows.find((r) => r.id === 'safety')?.status).toBe('pass');
  });

  it('high_risk confirm_unverified → matrix inconclusive (not pass)', () => {
    const papers: SuitePaperResult[] = BUILTIN_EXAM_SUITE.map((p): SuitePaperResult => {
      if (p.run_key === 'default/high_risk') {
        return {
          run_key: p.run_key,
          set_id: p.set_id,
          status: 'done',
          dimensions: {
            task_result: { status: 'pass', summary: '完成 1/1' },
            safety: {
              status: 'unknown',
              summary:
                'veto=False · 高风险确认探针无法判定（confirm_unverified）：仅有词面或测试用例设计命中',
            },
          },
        };
      }
      return {
        run_key: p.run_key,
        set_id: p.set_id,
        status: 'done',
        dimensions: {
          task_result: { status: 'pass', summary: 'ok' },
          grounding: { status: 'pass' },
          cost: { status: 'pass' },
          interaction: { status: 'pass' },
          robustness: { status: 'pass' },
          tools_trajectory: { status: 'unknown', summary: '步数=0 · 无法判定' },
          failure_localization: { status: 'warn' },
          safety: { status: 'pass' },
          memory_horizon: { status: 'warn' },
          score_variance: { status: 'warn' },
        },
      };
    });
    const rows = buildDimensionMatrix(papers);
    expect(rows.find((r) => r.id === 'safety')?.status).toBe('inconclusive');
  });

  it('task_result matrix fails when another paper has incomplete tasks', () => {
    const papers: SuitePaperResult[] = BUILTIN_EXAM_SUITE.map((p): SuitePaperResult => {
      if (p.run_key === 'default/normal') {
        return {
          run_key: p.run_key,
          set_id: p.set_id,
          status: 'done',
          dimensions: { task_result: { status: 'pass', summary: '完成 2/2' } },
        };
      }
      if (p.run_key === 'default/missing_info') {
        return {
          run_key: p.run_key,
          set_id: p.set_id,
          status: 'done',
          dimensions: {
            task_result: { status: 'fail', summary: '完成 0/2' },
            interaction: { status: 'fail', summary: 'ok' },
            robustness: { status: 'fail', summary: 'ok' },
            grounding: { status: 'fail', summary: 'ok' },
          },
        };
      }
      return {
        run_key: p.run_key,
        set_id: p.set_id,
        status: 'done',
        dimensions: {
          task_result: { status: 'pass', summary: 'ok' },
          grounding: { status: 'pass' },
          cost: { status: 'pass' },
          interaction: { status: 'pass' },
          robustness: { status: 'pass' },
          tools_trajectory: { status: 'unknown', summary: '步数=0 · 无法判定' },
          failure_localization: { status: 'warn' },
          safety: { status: 'pass' },
          memory_horizon: { status: 'warn' },
          score_variance: { status: 'warn' },
        },
      };
    });
    const rows = buildDimensionMatrix(papers);
    const task = rows.find((r) => r.id === 'task_result');
    expect(task?.status).toBe('fail');
    expect(task?.evidence).toMatch(/跨卷补入|聚合规则/);
    expect(task?.evidence).toMatch(/聚合规则：/);
    // Must not mid-truncate long formulas into tokens like `correct_f`
    expect(task?.evidence || '').not.toMatch(/correct_f\b/);
  });

  it('preferredSetForDim maps dims to builtin covering sets', () => {
    expect(preferredSetForDim('task_result')).toBe('default/normal');
    expect(preferredSetForDim('robustness')).toBe('default/missing_info');
    expect(preferredSetForDim('memory_horizon')).toBe('default/multi_turn');
    expect(preferredSetForDim('online_ux')).toBe('');
    expect(preferredSetForDim('tools')).toBe('');
    expect(preferredSetForDim('trajectory')).toBe('');
  });

  it('formatSmokeIssuesForPage flattens actionable rows for 小朱', () => {
    const papers: SuitePaperResult[] = BUILTIN_EXAM_SUITE.map((p) => ({
      run_key: p.run_key,
      set_id: p.set_id,
      status: 'done' as const,
      dimensions: {
        task_result: { status: 'fail', summary: '完成 1/2' },
        grounding: { status: 'pass' },
        cost: { status: 'pass' },
        interaction: { status: 'pass' },
        robustness: { status: 'pass' },
        tools_trajectory: { status: 'pass' },
        failure_localization: { status: 'pass' },
        safety: { status: 'pass' },
        memory_horizon: { status: 'warn' },
        score_variance: { status: 'pass' },
      },
    }));
    const rows = buildDimensionMatrix(papers);
    const page = formatSmokeIssuesForPage(rows, 'qa_agent');
    expect(page.smokeAgentId).toBe('qa_agent');
    expect(page.smokeSummary).toMatch(/fail=/);
    expect(page.smokeHint).toMatch(/smokeIssue/);
    expect(page.smokeIssue0).toMatch(/fail|warn/);
    expect(String(page.smokeIssue0)).toMatch(/原因:|对策:/);
  });
});
