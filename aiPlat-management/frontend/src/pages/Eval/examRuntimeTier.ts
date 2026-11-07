/**
 * Eval exam runtime tiers — SSOT labels for UI
 * (docs/architecture/plans/eval-exam-runtime-tiers.md v1.3).
 * runtime_tier = actual execution; target_runtime = intended delivery form.
 */
export type RuntimeTier =
  | 'fixture'
  | 'pi'
  | 'workspace_execute'
  | 'core_skill_execute'
  | 'eval_worker'
  | 'external_pull';

export const RUNTIME_TIER_LABELS: Record<RuntimeTier, string> = {
  fixture: 'fixture · 规则/结构/dry-run（未调用被测对象）',
  pi: 'pi · 厂外薄宿主（确已执行）',
  workspace_execute: 'workspace_execute · 命名工作区 Execute',
  core_skill_execute: 'core_skill_execute · Core skill_manager 已调 Skill',
  eval_worker: 'eval_worker · 独立 Eval Worker',
  external_pull: 'external_pull · 外部 HTTP 已拉对话',
};

export const RUNTIME_TIER_TABLE: Array<{
  id: RuntimeTier;
  use: string;
  boundary: string;
}> = [
  {
    id: 'fixture',
    use: '预检、仅导出/结构、路由候选（未调被测对象）',
    boundary: '不得声明被测对象运行行为；目标形态另见 target_runtime',
  },
  {
    id: 'pi',
    use: '生成应用 Pi live（CLI/宿主确已跑）',
    boundary: '≠ 仅结构导出；≠ 工作区 ReAct/PolicyGate',
  },
  {
    id: 'workspace_execute',
    use: 'Agent 正式 live / 本地冒烟（当前）',
    boundary: '≠ eval_worker；≠ 执行平面已迁移',
  },
  {
    id: 'core_skill_execute',
    use: 'Skill suite quality（skill_manager 已调）',
    boundary: '≠ trigger 仅路由；≠ Agent workspace_execute',
  },
  {
    id: 'eval_worker',
    use: '确在 Worker 的 allowlist Job',
    boundary: '≠ Agent exam 默认路径；≠ 平面授权切流',
  },
  {
    id: 'external_pull',
    use: '外部目标已 scored pull',
    boundary: 'dry 未拉 ≠ 本档；≠ 本机 Agent；≠ pi',
  },
];

export type RuntimeAnn = {
  runtime_tier: RuntimeTier;
  target_runtime: string;
  runtime_claim: boolean;
  runtime_claim_reason: string;
  execution_mode?: string;
};

export function agentExamRuntimeAnn(live: boolean): RuntimeAnn {
  if (live) {
    return {
      runtime_tier: 'workspace_execute',
      target_runtime: 'workspace_execute',
      runtime_claim: true,
      runtime_claim_reason:
        '结论仅适用于本命名工作区 Execute 路径；≠ eval_worker；≠ 执行平面已迁移',
    };
  }
  return {
    runtime_tier: 'fixture',
    target_runtime: 'workspace_execute',
    runtime_claim: false,
    runtime_claim_reason: 'fixture does not execute subject',
  };
}

/** Skill suite (platform skill_evals) — ≠ 验管道 skill fixture Job. */
export function skillEvalRuntimeAnn(
  evalKind: 'trigger' | 'quality' = 'trigger',
  mode: 'heuristic' | 'live' = 'heuristic',
): RuntimeAnn {
  if (evalKind === 'quality') {
    return {
      runtime_tier: 'core_skill_execute',
      target_runtime: 'core_skill_execute',
      runtime_claim: true,
      runtime_claim_reason:
        '结论仅适用于经 Core skill_manager 调用该 Skill 的路径；≠ workspace_execute agent',
      execution_mode: 'skill_manager_quality',
    };
  }
  return {
    runtime_tier: 'fixture',
    target_runtime: 'core_skill_execute',
    runtime_claim: false,
    runtime_claim_reason: `skill trigger ${mode}: routing candidates only; target skill handler not executed`,
    execution_mode: `skill_trigger_${mode}`,
  };
}

/** Generated-app — target always pi; actual pi only when live host ran. */
export function generatedAppRuntimeAnn(
  mode: 'runs_eval' | 'pi_offline' | 'pi_live',
): RuntimeAnn {
  if (mode === 'pi_live') {
    return {
      runtime_tier: 'pi',
      target_runtime: 'pi',
      runtime_claim: true,
      runtime_claim_reason:
        '结论仅适用于厂外 Pi 薄宿主交付态冒烟；≠ workspace_execute；≠ PolicyGate',
    };
  }
  if (mode === 'pi_offline') {
    return {
      runtime_tier: 'fixture',
      target_runtime: 'pi',
      runtime_claim: false,
      runtime_claim_reason: 'target_runtime=pi but pi CLI not invoked; structural/export only',
    };
  }
  return {
    runtime_tier: 'fixture',
    target_runtime: 'pi',
    runtime_claim: false,
    runtime_claim_reason:
      'target_runtime=pi; platform runs_eval only — pi host not wired for this result',
  };
}

export function formatRuntimeAnn(ann: {
  runtime_tier?: string;
  target_runtime?: string;
  runtime_claim?: boolean;
  runtime_claim_reason?: string;
}): string {
  const tier = String(ann.runtime_tier || '');
  const label =
    (RUNTIME_TIER_LABELS as Record<string, string>)[tier] || tier || '—';
  const target = ann.target_runtime ? ` · target=${ann.target_runtime}` : '';
  const claim = ann.runtime_claim ? 'runtime_claim=true' : 'runtime_claim=false';
  const reason = ann.runtime_claim_reason ? ` · ${ann.runtime_claim_reason}` : '';
  return `${label}${target} · ${claim}${reason}`;
}
