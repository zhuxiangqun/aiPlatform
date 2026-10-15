/** Factory run observability: 跑到哪 / 为何卡 (no new backend). */

export type StageLite = {
  agent_name?: string;
  agent_id?: string;
  phase?: string;
  id?: string;
  output_artifact?: string;
};

export type RunObsPromotion = {
  blockers?: string[];
  next_actions?: string[];
  summary?: string;
  hops?: {
    effective_n?: number;
    effective_success_rate?: number;
    by_failed_stage?: Record<string, number>;
  };
  multi_agent_upgrade?: { fix_hint?: string; summary?: string; next_actions?: string[] };
};

export type RunObsSnapshot = {
  stageLabel: string;
  stageId: string;
  whyStuck: string;
  hopLine: string;
  canResume: boolean;
  preferRegenerate: boolean;
};

/** HITL wait phases — Core may emit ``paused`` or ``awaiting_approval``. */
export function isHitlWaitPhase(phase?: string | null): boolean {
  if (!phase) return false;
  return phase === 'paused' || phase === 'awaiting_approval' || phase.includes('approval');
}

export function matchStageByKey(stages: StageLite[], key: string): StageLite | null {
  const k = String(key || '').trim();
  if (!k) return null;
  return (
    stages.find(
      (s) => s.id === k || s.agent_id === k || s.output_artifact === k,
    ) || null
  );
}

/** Derive 跑到哪 / 为何卡 from pipeline state + promotion. */
export function buildRunObsSnapshot(
  state: Record<string, unknown> | null | undefined,
  stages: StageLite[],
  promotion: RunObsPromotion | null,
): RunObsSnapshot {
  const phase = String(state?.phase || '');
  const hops = promotion?.hops;
  const failed = hops?.by_failed_stage || {};
  const topFail = Object.entries(failed).sort((a, b) => b[1] - a[1])[0];

  // Prefer Core HITL id (resume/regenerate match s.id | output_artifact); then idx; then hop top-fail; then last artifact.
  const hitlId = String(state?._hitl_stage_id || '').trim();
  const idxRaw = state?._current_stage_idx;
  const idx = typeof idxRaw === 'number' && idxRaw >= 0 ? idxRaw : -1;
  const active =
    matchStageByKey(stages, hitlId)
    || (idx >= 0 && idx < stages.length ? stages[idx] : null)
    || (phase === 'failed' && topFail ? matchStageByKey(stages, topFail[0]) : null)
    || [...stages].reverse().find((s) => s.output_artifact)
    || null;

  const stageId = String(
    (active && (active.id || active.agent_id || active.output_artifact))
    || hitlId
    || (topFail && phase === 'failed' ? topFail[0] : '')
    || '',
  );
  const stageLabel =
    (active?.agent_name || active?.agent_id || active?.id
      || (idx >= 0 ? `阶段 ${idx + 1}` : stageId || '尚未进入阶段')) as string;

  const handoffBucket = (state?._handoff && typeof state._handoff === 'object')
    ? (state._handoff as Record<string, unknown>)
    : {};
  const artKey = String(active?.output_artifact || '');
  let handoff: Record<string, unknown> | null = null;
  if (artKey && handoffBucket[artKey] && typeof handoffBucket[artKey] === 'object') {
    handoff = handoffBucket[artKey] as Record<string, unknown>;
  } else {
    const vals = Object.values(handoffBucket).filter((v) => v && typeof v === 'object') as Record<string, unknown>[];
    handoff = vals.length ? vals[vals.length - 1] : null;
  }

  const next = String(handoff?.next || '').trim();
  const issues = Array.isArray(handoff?.known_issues)
    ? (handoff!.known_issues as unknown[]).map(String).filter(Boolean)
    : [];
  const promoWhy =
    (promotion?.multi_agent_upgrade?.fix_hint || '').trim()
    || (promotion?.multi_agent_upgrade?.next_actions || [])[0]
    || (promotion?.next_actions || [])[0]
    || (promotion?.blockers || [])[0]
    || (promotion?.summary || '').trim();
  const whyStuck =
    next
    || (issues.length ? `已知问题：${issues.slice(0, 2).join('；')}` : '')
    || String(promoWhy || '').trim()
    || '尚无交接 next / 晋升门提示（可打开部署日志或 hop 证据）';

  const n = hops?.effective_n ?? 0;
  let hopLine = '尚无 hop 样本';
  if (n > 0) {
    const rate = hops?.effective_success_rate;
    const pct = typeof rate === 'number' ? `${Math.round(rate * 100)}%` : '—';
    hopLine = `有效 hop N=${n} · 成功率 ${pct}`
      + (topFail ? ` · 常失败阶段 ${topFail[0]}×${topFail[1]}` : '');
  }

  const canResume = Boolean(stageId) && (phase === 'failed' || isHitlWaitPhase(phase) || phase === 'paused');
  const preferRegenerate = Boolean(next || issues.length);

  return { stageLabel, stageId, whyStuck, hopLine, canResume, preferRegenerate };
}

/** Short line for Factory project cards (failed / HITL). */
export function formatCardStuckHint(snap: RunObsSnapshot, maxLen = 56): string {
  const base = `${snap.stageLabel}: ${snap.whyStuck}`.replace(/\s+/g, ' ').trim();
  if (!base || base.startsWith('尚未进入阶段')) return '';
  if (base.length <= maxLen) return base;
  return `${base.slice(0, Math.max(1, maxLen - 1))}…`;
}
