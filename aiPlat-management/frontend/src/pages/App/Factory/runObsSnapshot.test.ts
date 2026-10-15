import { describe, expect, it } from 'vitest';
import {
  buildRunObsSnapshot,
  formatCardStuckHint,
  isHitlWaitPhase,
  matchStageByKey,
  type StageLite,
} from './runObsSnapshot';

const stages: StageLite[] = [
  { id: 's1', agent_id: 'architect', agent_name: '架构师', output_artifact: 'architecture' },
  { id: 's2', agent_id: 'coder', agent_name: '程序员', output_artifact: 'code' },
  { id: 's3', agent_id: 'qa', agent_name: '测试', output_artifact: 'test_report' },
];

describe('isHitlWaitPhase', () => {
  it('matches paused / awaiting_approval / *approval*', () => {
    expect(isHitlWaitPhase('paused')).toBe(true);
    expect(isHitlWaitPhase('awaiting_approval')).toBe(true);
    expect(isHitlWaitPhase('awaiting_human_approval')).toBe(true);
    expect(isHitlWaitPhase('failed')).toBe(false);
    expect(isHitlWaitPhase(null)).toBe(false);
  });
});

describe('matchStageByKey', () => {
  it('matches id, agent_id, or output_artifact', () => {
    expect(matchStageByKey(stages, 's2')?.agent_name).toBe('程序员');
    expect(matchStageByKey(stages, 'qa')?.id).toBe('s3');
    expect(matchStageByKey(stages, 'architecture')?.id).toBe('s1');
    expect(matchStageByKey(stages, '')).toBeNull();
  });
});

describe('buildRunObsSnapshot stage resolve', () => {
  it('prefers _hitl_stage_id over _current_stage_idx', () => {
    const snap = buildRunObsSnapshot(
      { phase: 'paused', _hitl_stage_id: 's3', _current_stage_idx: 0 },
      stages,
      null,
    );
    expect(snap.stageId).toBe('s3');
    expect(snap.stageLabel).toBe('测试');
    expect(snap.canResume).toBe(true);
  });

  it('on failed falls back to hop by_failed_stage top key', () => {
    const snap = buildRunObsSnapshot(
      { phase: 'failed', _current_stage_idx: -1 },
      stages,
      {
        hops: {
          effective_n: 12,
          effective_success_rate: 0.25,
          by_failed_stage: { code: 5, architecture: 1 },
        },
      },
    );
    expect(snap.stageId).toBe('s2');
    expect(snap.stageLabel).toBe('程序员');
    expect(snap.hopLine).toContain('N=12');
    expect(snap.hopLine).toContain('code×5');
    expect(snap.canResume).toBe(true);
  });

  it('prefers handoff.next for whyStuck and preferRegenerate', () => {
    const snap = buildRunObsSnapshot(
      {
        phase: 'failed',
        _current_stage_idx: 1,
        _handoff: {
          code: { next: '补齐 API 鉴权', known_issues: ['缺 JWT'] },
        },
      },
      stages,
      { next_actions: ['忽略我'], summary: 'summary' },
    );
    expect(snap.whyStuck).toBe('补齐 API 鉴权');
    expect(snap.preferRegenerate).toBe(true);
  });

  it('uses multi_agent_upgrade.fix_hint when no handoff next', () => {
    const snap = buildRunObsSnapshot(
      { phase: 'done', _current_stage_idx: 2 },
      stages,
      {
        multi_agent_upgrade: {
          fix_hint: '五条 AND 通过 0/5；先补 orthogonal_subtasks',
          next_actions: ['列子任务'],
        },
      },
    );
    expect(snap.whyStuck).toContain('orthogonal_subtasks');
    expect(snap.canResume).toBe(false);
  });
});

describe('formatCardStuckHint', () => {
  it('prefixes stageLabel and truncates', () => {
    const snap = buildRunObsSnapshot(
      {
        phase: 'failed',
        _current_stage_idx: 1,
        _handoff: {
          code: {
            next: '补齐一段很长很长很长很长很长很长很长很长很长很长很长的鉴权与错误处理说明以便截断展示',
          },
        },
      },
      stages,
      null,
    );
    const hint = formatCardStuckHint(snap, 40);
    expect(hint.startsWith('程序员:')).toBe(true);
    expect(hint.endsWith('…')).toBe(true);
    expect(hint.length).toBeLessThanOrEqual(40);
  });
});
