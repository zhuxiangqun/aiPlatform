import { describe, expect, it } from 'vitest';
import {
  RUNTIME_TIER_TABLE,
  agentExamRuntimeAnn,
  formatRuntimeAnn,
  generatedAppRuntimeAnn,
  skillEvalRuntimeAnn,
} from './examRuntimeTier';

describe('examRuntimeTier', () => {
  it('defines archival tiers including core_skill_execute', () => {
    expect(RUNTIME_TIER_TABLE.map((r) => r.id)).toEqual([
      'fixture',
      'pi',
      'workspace_execute',
      'core_skill_execute',
      'eval_worker',
      'external_pull',
    ]);
  });

  it('maps agent dry-run to fixture and live to workspace_execute', () => {
    const dry = agentExamRuntimeAnn(false);
    expect(dry.runtime_tier).toBe('fixture');
    expect(dry.target_runtime).toBe('workspace_execute');
    expect(dry.runtime_claim).toBe(false);
    const live = agentExamRuntimeAnn(true);
    expect(live.runtime_tier).toBe('workspace_execute');
    expect(live.runtime_claim).toBe(true);
  });

  it('keeps target_runtime=pi when actual host did not run', () => {
    const runs = generatedAppRuntimeAnn('runs_eval');
    expect(runs.runtime_tier).toBe('fixture');
    expect(runs.target_runtime).toBe('pi');
    expect(runs.runtime_claim).toBe(false);
    const offline = generatedAppRuntimeAnn('pi_offline');
    expect(offline.runtime_tier).toBe('fixture');
    expect(offline.target_runtime).toBe('pi');
    const live = generatedAppRuntimeAnn('pi_live');
    expect(live.runtime_tier).toBe('pi');
    expect(live.target_runtime).toBe('pi');
    expect(live.runtime_claim).toBe(true);
  });

  it('maps skill trigger to fixture and quality to core_skill_execute', () => {
    const t = skillEvalRuntimeAnn('trigger', 'heuristic');
    expect(t.runtime_tier).toBe('fixture');
    expect(t.target_runtime).toBe('core_skill_execute');
    expect(t.runtime_claim).toBe(false);
    const q = skillEvalRuntimeAnn('quality');
    expect(q.runtime_tier).toBe('core_skill_execute');
    expect(q.target_runtime).toBe('core_skill_execute');
    expect(q.runtime_claim).toBe(true);
    expect(q.execution_mode).toBe('skill_manager_quality');
  });

  it('formats annotation line with target_runtime', () => {
    const s = formatRuntimeAnn(generatedAppRuntimeAnn('pi_offline'));
    expect(s).toContain('fixture');
    expect(s).toContain('target=pi');
    expect(s).toContain('runtime_claim=false');
  });
});
