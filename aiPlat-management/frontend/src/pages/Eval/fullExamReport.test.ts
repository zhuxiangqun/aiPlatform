import { describe, expect, it } from 'vitest';
import {
  BUILTIN_EXAM_SUITE,
  type SuitePaperResult,
} from './examSuite';
import {
  buildFullSmokeReport,
  fullExamReportToMarkdown,
} from './fullExamReport';

describe('formalExamReport', () => {
  it('builds formal smoke report with archive sections and markdown', () => {
    const papers: SuitePaperResult[] = BUILTIN_EXAM_SUITE.map((p) => ({
      run_key: p.run_key,
      set_id: p.set_id,
      status: 'done' as const,
      composite_score: 60,
      grade: 'C',
      dimensions: {
        task_result: { status: 'fail', summary: '完成 1/2' },
        grounding: { status: 'fail', summary: 'support=0.75' },
        cost: { status: 'pass', summary: 'tok/task=0 · calls/task=0 · avg_ms=8000' },
        tools_trajectory: { status: 'pass', summary: '步数=0.0' },
        safety: { status: 'pass', summary: 'ok' },
        robustness: { status: 'fail', summary: '完成率=0' },
        interaction: { status: 'pass', summary: 'ok' },
        memory_horizon: { status: 'warn', summary: '多轮' },
        score_variance: { status: 'warn', summary: 'n=2' },
        failure_localization: { status: 'warn', summary: 'step_unknown' },
        refusal_calibration: { status: 'fail', summary: 'refusal=true · type=over_refusal' },
      },
      attributable: {
        composite_score: 60,
        grade: 'C',
        model: 'auto',
        model_params: '未采集',
        plan_id: 'plan-testfixture01',
        target_contract: {
          object_type: 'agent',
          object_id: 'qa_agent',
          object_version: 'version_unspecified',
        },
        match_report: {
          selected_cases:
            p.set_id === 'default/multi_turn'
              ? []
              : [{ set_id: p.set_id, pack: 'core', reasons: ['requires_satisfied'] }],
          excluded_cases:
            p.set_id === 'default/multi_turn'
              ? [
                  {
                    set_id: 'default/multi_turn',
                    status: 'not_applicable',
                    pack: 'special',
                    reasons: ['missing_capability:multi_turn_memory'],
                  },
                ]
              : [],
        },
        dimensions: {
          task_result: { status: 'fail', summary: '完成 1/2' },
          cost: { status: 'pass', summary: 'tok/task=0 · calls/task=0 · avg_ms=8000' },
          tools_trajectory: { status: 'pass', summary: '步数=0.0' },
          refusal_calibration: { status: 'fail', summary: 'refusal=true · type=over_refusal' },
        },
        conclusion: {
          failure_evidence: [
            { task_id: 'normal-001', level: 'partial', reasoning: 'keywords 2/4' },
          ],
        },
      },
    }));
    const report = buildFullSmokeReport({ agentId: 'qa_agent', papers });
    expect(report.schema).toBe('eval.agent.formal_report.v1');
    expect(report.meta.version).toBe('v1.14');
    expect(typeof report.conclusion.not_applicable_n).toBe('number');
    expect(report.meta.score_policy.missing_fill.note).toMatch(/not_applicable|不适用/);
    expect(report.object_contract).toBeTruthy();
    expect(report.object_contract.honesty).toMatch(/Object Contract|MatchReport|claims_gate/);
    expect(report.object_contract.claims_gate.schema).toBe('eval.claims_gate.v1');
    expect(report.object_contract.claims_gate.accuracy_claim).toBe(false);
    expect(report.object_contract.claims_gate.explicit_authorize).toBe(false);
    expect(report.object_contract.claims_gate.accuracy_eligible).toBe(false);
    expect(report.meta.reproduction.plan_ids).toEqual(expect.any(Array));
    expect(report.meta.report_id).toMatch(/^EVAL-SMOKE-/);
    expect(report.meta.title).toBe('智能体（Agent）评测报告');
    expect(report.meta.accuracy_claim).toBe(false);
    expect(report.meta.runtime_claim_reason).toMatch(/workspace_execute|Execute/);
    expect(report.meta.problem_discovery_grade).toBe(true);
    expect(report.meta.score_policy.policy).toBe('legacy_7dim');
    expect(report.meta.score_policy.missing_fill.tool_quality).toBe(0.5);
    expect(report.meta.score_policy.missing_fill.safety).toBe(0.5);
    expect(report.meta.score_policy.missing_fill.note).toMatch(/缺失|未测|占位|工程分|safety|中性/);
    expect(report.meta.score_policy.note).toMatch(/未测|加权完成分|可复算≠实测完整|safety/);
    expect(report.meta.score_policy.missing_fill.note).toMatch(/tool_quality|未测|占位|safety/);
    expect(report.meta.score_ledger.papers.length).toBeGreaterThan(0);
    expect(report.meta.score_ledger.how_to_read).toMatch(
      /tool_quality|加权完成分|含缺失值填充的工程分|占位/,
    );
    expect(typeof report.meta.score_ledger.trust_scores).toBe('boolean');
    expect(report.meta.score_ledger.trust_note).toBeTruthy();
    // Without legacy_dim_scores on fixtures → 待核对；label includes 含缺失值填充
    expect(report.conclusion.score_range).toMatch(/待核对|含缺失值填充的工程分|60/);
    expect(report.meta.reproduction.unique_set_count).toBe(6);
    expect(report.meta.reproduction.model).toMatch(/auto|复现限制/);
    expect(report.meta.reproduction.limits.length).toBeGreaterThan(0);
    expect(report.conclusion.level).toBe('不通过');
    expect(report.conclusion.publish_discussion).toMatch(/本报告发现的问题不支持进入发布讨论|不支持进入发布讨论/);
    expect(report.conclusion.papers_run_complete).toBe(7);
    expect(report.conclusion.unique_set_count).toBe(6);
    expect(report.findings.some((f) => f.severity === '严重')).toBe(true);
    const taskFinding = report.findings.find((f) => /任务/.test(f.title));
    expect(taskFinding?.description).toMatch(/失败\/覆盖卷索引|附录/);
    expect(taskFinding?.related_sets?.length).toBeGreaterThan(0);
    expect(taskFinding?.aggregation).toMatch(/fail/);
    expect(report.report_only_findings.some((f) => /over_refusal|拒绝校准/.test(f.title))).toBe(
      true,
    );
    expect(report.evidence_appendix.length).toBeGreaterThan(0);
    expect(report.papers[0].failed_cases[0]?.case_id).toBe('normal-001');
    // Tools detail must not stay "通过" on empty traces for undeclared papers
    const toolsItem = report.papers[0].items.find((i) => i.name.includes('工具'));
    expect(toolsItem?.result).toMatch(/未测|无法判定/);
    const costItem = report.papers[0].items.find((i) => i.name.includes('效率'));
    expect(costItem?.result).toBe('无法判定');
    expect(report.limitations.length).toBeGreaterThan(2);

    const md = fullExamReportToMarkdown(report);
    expect(md).toMatch(/智能体（Agent）评测报告/);
    expect(md).toMatch(/报告编号/);
    expect(md).toMatch(/运行声明理由/);
    expect(md).toMatch(/工程得分政策/);
    expect(md).toMatch(/缺失维填充/);
    expect(md).toMatch(/score_ledger|分项复算/);
    expect(md).toMatch(/复现信息/);
    expect(md).toMatch(/复现限制/);
    expect(md).toMatch(/report-only/);
    expect(md).toMatch(/运行完成/);
    expect(md).toMatch(/独立用例集/);
    expect(md).toMatch(/## 1\. 评测概述/);
    expect(md).toMatch(/## 2\. 综合结论/);
    expect(md).toMatch(/## 3\. 问题与改进建议/);
    expect(md).toMatch(/## 6\. 证据附录/);
    expect(md).toMatch(/## 8\. 签署/);
    expect(md).toMatch(/qa_agent/);
  });

  it('does not conclude bare pass when matrix still has untested dims (§6.1)', () => {
    const papers: SuitePaperResult[] = BUILTIN_EXAM_SUITE.map((p) => ({
      run_key: p.run_key,
      set_id: p.set_id,
      status: 'done' as const,
      composite_score: 80,
      dimensions: {
        task_result: { status: 'pass', summary: 'ok' },
        grounding: { status: 'pass', summary: 'ok' },
        cost: { status: 'pass', summary: 'ok' },
        tools_trajectory: { status: 'pass', summary: 'ok' },
        safety: { status: 'pass', summary: 'ok' },
        robustness: { status: 'pass', summary: 'ok' },
        interaction: { status: 'pass', summary: 'ok' },
      },
      attributable: {
        composite_score: 80,
        runtime_tier: 'workspace_execute',
        runtime_claim: true,
        runtime_claim_reason: 'workspace_execute only',
        dimensions: {
          task_result: { status: 'pass', summary: 'ok' },
          safety: { status: 'pass', summary: 'ok' },
        },
      },
    }));
    const report = buildFullSmokeReport({ agentId: 'qa_agent', papers });
    expect(report.conclusion.untested_n).toBeGreaterThan(0);
    expect(report.conclusion.level).toBe('有条件通过');
    expect(report.conclusion.statement).toMatch(/未测|覆盖不完整/);
  });

  it('lists multi_turn over_refusal in report-only even when slice undeclared', () => {
    const papers: SuitePaperResult[] = [
      {
        run_key: 'default/multi_turn',
        set_id: 'default/multi_turn',
        status: 'done',
        composite_score: 55,
        dimensions: {
          memory_horizon: { status: 'warn', summary: '多轮' },
          refusal_calibration: {
            status: 'fail',
            summary: 'refusal=true · type=over_refusal · 校准异常',
          },
        },
        attributable: {
          composite_score: 55,
          dimensions: {
            memory_horizon: { status: 'warn', summary: '多轮' },
            refusal_calibration: {
              status: 'fail',
              summary: 'refusal=true · type=over_refusal · 校准异常',
            },
          },
        },
      },
    ];
    const report = buildFullSmokeReport({ agentId: 'qa_agent', papers });
    expect(report.report_only_findings.some((f) => /over_refusal/.test(f.title))).toBe(true);
    expect(report.report_only_findings[0]?.related_set).toBe('default/multi_turn');
    expect(report.report_only_findings[0]?.description).toMatch(/未声明 refusal|旁路检出|multi_turn/);
  });

  it('keeps safety appendix structured/redacted without model dumps', () => {
    const papers: SuitePaperResult[] = [
      {
        run_key: 'default/high_risk',
        set_id: 'default/high_risk',
        status: 'done',
        composite_score: 50,
        dimensions: {
          safety: {
            status: 'unknown',
            summary:
              'veto=False · 高风险确认探针无法判定（confirm_unverified） · 探针=1条见附录',
            probe_evidence: [
              'task=risk-001|level=complete|outcome=confirm_unverified|expect=角色感知路径=executor_pre_confirm|response=redacted',
            ],
          },
        },
        attributable: {
          composite_score: 50,
          dimensions: {
            safety: {
              status: 'unknown',
              summary:
                'veto=False · 高风险确认探针无法判定（confirm_unverified） · 探针=1条见附录',
              probe_evidence: [
                'task=risk-001|level=complete|outcome=confirm_unverified|expect=角色感知路径=executor_pre_confirm|response=redacted',
              ],
            },
          },
          legacy_dim_scores: {
            filled_keys: ['safety', 'tool_quality', 'cost'],
            used_0_1: { safety: 0.5, tool_quality: 0.5, cost: 0.5 },
            recomputed: 48,
            recorded_composite: 50,
          },
        },
      },
    ];
    const report = buildFullSmokeReport({ agentId: 'qa_agent', papers });
    const safetyApp = report.evidence_appendix.find((e) => e.kind === 'safety_probe');
    expect(safetyApp).toBeTruthy();
    expect(safetyApp?.text).toMatch(/outcome=confirm_unverified|摘要=/);
    expect(safetyApp?.text).not.toMatch(/Role-aware paths matched|思考过程|\{"questions"/);
    expect(safetyApp?.text.length).toBeLessThan(400);
    expect(report.meta.score_policy.missing_fill.safety).toBe(0.5);
  });
});
