/**
 * Attributable report — plain-language first; jargon in collapsed details.
 */
export type AttributableReport = {
  schema?: string;
  accuracy_claim?: boolean;
  sufficiency_claim?: boolean;
  agent_id?: string;
  set_id?: string;
  requested_set_id?: string | null;
  result_set_id?: string | null;
  set_scoped?: boolean;
  eval_time?: number | string | null;
  live?: boolean | null;
  composite_score?: number | null;
  grade?: string;
  ok?: boolean;
  error?: string;
  coverage_note?: string;
  gate?: {
    pass?: boolean;
    veto?: boolean;
    veto_reasons?: string[];
    policy?: string;
    note?: string;
    publish_allowed?: boolean;
  };
  publish?: {
    allowed?: boolean;
    decision?: string;
    veto?: boolean;
    reasons?: string[];
  };
  dimensions?: {
    task_result?: DimSlice;
    tools_trajectory?: DimSlice;
    safety?: DimSlice & { veto?: boolean; veto_reasons?: string[] };
    cost?: DimSlice & { flags?: string[] };
    refusal_calibration?: DimSlice;
    score_variance?: DimSlice & { n?: number; std?: number };
    grounding?: DimSlice;
    memory_horizon?: DimSlice;
    failure_localization?: DimSlice;
    online_ux?: DimSlice;
    judge_agreement?: DimSlice;
    controlled_ab?: DimSlice;
    robustness?: DimSlice & { tags?: string[]; completion_rate?: number };
    interaction?: DimSlice & {
      tags?: string[];
      text_quality_overall?: number;
      completion_rate?: number;
    };
  };
  attribution?: Array<{ layer?: string; hint?: string; detail?: string }>;
  conclusion?: {
    publish_allowed?: boolean;
    publish_decision?: string;
    coverage?: {
      measured_slices?: string[];
      unmeasured_slices?: string[];
      insufficient_slices?: string[];
      note?: string;
    };
    sample?: {
      history_n?: number;
      variance_n?: number;
      confidence?: string;
      accuracy_claim?: boolean;
    };
    failure_evidence_count?: number;
    failure_evidence?: Array<Record<string, unknown>>;
    applicable_env?: Record<string, unknown>;
  };
};

type DimSlice = {
  status?: string;
  summary?: string;
  [k: string]: unknown;
};

function statusLabel(status?: string): string {
  if (status === 'pass') return '通过';
  if (status === 'fail' || status === 'veto') return '未通过';
  if (status === 'warn') return '需留意';
  if (status === 'unknown' || status === 'inconclusive') return '无法判定';
  if (status === 'missing') return '本卷没测';
  return status || '—';
}

function statusClass(status?: string): string {
  if (status === 'pass') return 'text-green-300';
  if (status === 'veto' || status === 'fail') return 'text-red-300';
  if (status === 'warn' || status === 'unknown' || status === 'inconclusive') {
    return 'text-amber-300';
  }
  if (status === 'missing') return 'text-gray-500';
  return 'text-gray-400';
}

function formatEvalTime(v: unknown): string {
  const n = typeof v === 'number' ? v : Number(v);
  if (!Number.isFinite(n) || n <= 0) return '';
  const ms = n < 1e12 ? n * 1000 : n;
  try {
    return new Date(ms).toLocaleString();
  } catch {
    return '';
  }
}

const LAYER_PLAIN: Record<string, string> = {
  task_result: '任务有没有做完',
  tools_trajectory: '工具用得对不对',
  safety: '安全',
  cost: '耗时与成本',
  refusal_calibration: '该不该拒答',
  score_variance: '分数稳不稳',
  grounding: '关键信息写全了没',
  memory_horizon: '多轮记忆',
  failure_localization: '失败好不好查',
  online_ux: '真实线上体验',
  judge_agreement: '人和机器判分是否一致',
  controlled_ab: '对照实验',
  robustness: '抗干扰',
  interaction: '问得清、答得好不好',
};

const DIM_ROWS: Array<{ key: keyof NonNullable<AttributableReport['dimensions']>; label: string }> = [
  { key: 'task_result', label: '任务有没有做完' },
  { key: 'tools_trajectory', label: '工具用得对不对' },
  { key: 'safety', label: '安全' },
  { key: 'cost', label: '耗时与成本' },
  { key: 'refusal_calibration', label: '该不该拒答' },
  { key: 'score_variance', label: '分数稳不稳' },
  { key: 'grounding', label: '关键信息写全了没' },
  { key: 'memory_horizon', label: '多轮记忆' },
  { key: 'failure_localization', label: '失败好不好查' },
  { key: 'online_ux', label: '真实线上体验' },
  { key: 'judge_agreement', label: '人和机器判分是否一致' },
  { key: 'controlled_ab', label: '对照实验' },
  { key: 'robustness', label: '抗干扰' },
  { key: 'interaction', label: '问得清、答得好不好' },
];

function publishPlain(veto: boolean, allowed: boolean | undefined): string {
  if (veto) return '不可上线：安全没过';
  if (allowed) return '可讨论上线（仍有缺口）';
  return '暂不建议上线';
}

function plainVerdict(
  veto: boolean,
  inPaper: Array<{ label: string; slice?: DimSlice }>,
): string {
  if (veto) return '安全检查没过，这卷不能当「可以上线」。';
  const bad = inPaper.filter((r) => r.slice?.status === 'fail' || r.slice?.status === 'veto');
  const warn = inPaper.filter(
    (r) =>
      r.slice?.status === 'warn' ||
      r.slice?.status === 'unknown' ||
      r.slice?.status === 'inconclusive',
  );
  if (bad.length) {
    const names = bad.map((b) => b.label).join('、');
    return `这卷有 ${bad.length} 项未通过（${names}）。先改这些，再重测。`;
  }
  if (warn.length) {
    return `没有硬失败，但有 ${warn.length} 项需留意或无法判定。可以先记下，不算已经合格。`;
  }
  return '这卷主要检查项都过了。没测到的项不代表已经合格。';
}

type DimRow = { label: string; slice?: DimSlice };

function renderDimCard({ label, slice }: DimRow) {
  return (
    <div key={label} className="rounded border border-gray-700/80 bg-gray-950/40 px-2 py-2">
      <div className="flex justify-between gap-2">
        <span className="text-gray-200">{label}</span>
        <span className={`font-medium ${statusClass(slice?.status)}`}>
          {statusLabel(slice?.status)}
        </span>
      </div>
      <p className="text-gray-400 mt-1 leading-relaxed">{slice?.summary || '—'}</p>
      {label === '关键信息写全了没' &&
      Array.isArray(slice?.details) &&
      (slice?.details as unknown[]).length > 0 ? (
        <ul className="mt-1.5 list-disc pl-4 space-y-0.5 text-[11px] text-gray-500">
          {(slice?.details as Array<Record<string, unknown>>).slice(0, 6).map((d, i) => (
            <li key={String(d.task_id || i)}>
              题目 {String(d.task_id || i + 1)}：对上了 {String(d.hits ?? '—')}/
              {String(d.checks ?? '—')} 个要点
              {Array.isArray(d.missing) && d.missing.length
                ? `；还缺：${(d.missing as string[]).slice(0, 3).join('、')}`
                : ''}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

type Props = {
  report: AttributableReport | null | undefined;
  title?: string;
  /** session = 本页刚跑；stored = 落盘历史（可能不是你刚点的那次） */
  source?: 'session' | 'stored' | null;
};

export default function EvalAttributableReportCard({
  report,
  title = '评测结果说明',
  source = null,
}: Props) {
  if (!report) return null;
  if (report.ok === false && report.error) {
    const want = report.requested_set_id || report.set_id;
    return (
      <div
        className="rounded-lg border border-amber-800/40 bg-amber-950/20 px-3 py-2 text-xs text-amber-100/90 space-y-1"
        data-testid="eval-attributable-report"
        data-empty="true"
      >
        <div className="font-medium text-amber-50">{title}</div>
        <p>
          {want
            ? `还没有「${want}」这套题的正式评测记录。先点「正式评测」跑一遍。`
            : '还没有评测记录。'}
        </p>
      </div>
    );
  }

  const dims = report.dimensions || {};
  const gate = report.gate || {};
  const publish = report.publish || {};
  const conclusion = report.conclusion || {};
  const veto = Boolean(gate.veto || publish.veto);
  const publishAllowed = publish.allowed ?? gate.publish_allowed ?? gate.pass;
  const setLabel = report.result_set_id || report.set_id || '';
  const when = formatEvalTime(report.eval_time);
  const allRows: DimRow[] = DIM_ROWS.map(({ key, label }) => ({
    label,
    slice: dims[key],
  }));
  const inPaper = allRows.filter((r) => r.slice?.status && r.slice.status !== 'missing');
  const outOfPaper = allRows.filter((r) => !r.slice?.status || r.slice.status === 'missing');
  const verdict = plainVerdict(veto, inPaper);

  return (
    <section
      className={`rounded-lg border px-3 py-3 space-y-3 text-xs ${
        veto
          ? 'border-red-700/50 bg-red-950/20 text-red-50'
          : 'border-emerald-800/40 bg-emerald-950/10 text-emerald-50'
      }`}
      data-testid="eval-attributable-report"
      data-gate-pass={gate.pass ? 'true' : 'false'}
      data-safety-veto={veto ? 'true' : 'false'}
      data-publish-allowed={publishAllowed ? 'true' : 'false'}
      data-report-source={source || ''}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-medium text-gray-100">{title}</h3>
          <p className="text-sm text-gray-100 mt-1.5 leading-snug" data-testid="eval-report-verdict">
            {verdict}
          </p>
          <p className="text-[11px] text-gray-400 mt-1">
            {source === 'session'
              ? '这是你刚才跑出来的结果'
              : source === 'stored'
                ? '这是这套题最近一次保存的结果（不一定是你刚点的那次）'
                : '评测结果'}
            {setLabel ? ` · 题集 ${setLabel}` : ''}
            {when ? ` · ${when}` : ''}
          </p>
        </div>
        <div className="text-right shrink-0">
          <div
            className={`text-sm font-medium ${
              veto ? 'text-red-300' : publishAllowed ? 'text-emerald-300' : 'text-amber-300'
            }`}
          >
            {publishPlain(veto, publishAllowed)}
          </div>
          <div className="text-gray-400 mt-0.5">
            得分 {report.composite_score ?? '—'}
            {report.grade ? `（等级 ${report.grade}）` : ''}
          </div>
          <p className="text-[10px] text-gray-500 mt-0.5">得分只是工程参考，不是「准确率认证」</p>
        </div>
      </div>

      <div>
        <h4 className="text-[11px] font-medium text-gray-300 mb-1.5">这套题查到的结果</h4>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {inPaper.length ? (
            inPaper.map(renderDimCard)
          ) : (
            <p className="text-gray-500 col-span-full">这套题还没有检查结果。</p>
          )}
        </div>
      </div>

      {outOfPaper.length ? (
        <details
          className="rounded border border-gray-800 bg-gray-950/30 px-2 py-1.5"
          data-testid="eval-report-out-of-paper"
        >
          <summary className="cursor-pointer text-[11px] text-gray-400">
            这套题没查的项目（{outOfPaper.length}）· 不是做错了 · 点开可看
          </summary>
          <p className="text-[11px] text-gray-500 mt-1.5 mb-2">
            例如真实线上、多人交叉打分、抗干扰卷等，要另选题或另开流程才会测到。
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">{outOfPaper.map(renderDimCard)}</div>
        </details>
      ) : null}

      {(conclusion.failure_evidence_count || 0) > 0 ? (
        <div className="rounded border border-amber-800/40 bg-amber-950/20 px-2 py-2 text-[11px] text-amber-100/90">
          <div className="font-medium text-amber-50 mb-1">
            哪道题没过（{conclusion.failure_evidence_count}）
          </div>
          <ul className="list-disc pl-4 space-y-0.5 text-amber-100/80">
            {(conclusion.failure_evidence || []).slice(0, 5).map((f, i) => (
              <li key={i}>
                {String(f.task_id || '题目')}
                {f.level ? `（${String(f.level)}）` : ''}
                {f.reasoning ? `：${String(f.reasoning).slice(0, 100)}` : ''}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {(report.attribution || []).length > 0 ? (
        <div>
          <div className="text-gray-300 mb-1">建议先改这些</div>
          <ul className="list-disc pl-4 space-y-0.5 text-gray-400">
            {(report.attribution || []).map((a, i) => (
              <li key={`${a.layer}-${a.hint}-${i}`}>
                <span className="text-gray-200">
                  {LAYER_PLAIN[String(a.layer || '')] || a.layer}
                </span>
                ：{a.hint}
                {a.detail ? `（${a.detail}）` : ''}
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="text-gray-500">这套题没有需要优先改的未通过项。</p>
      )}

      {conclusion.coverage ? (
        <details className="rounded border border-gray-800 bg-gray-950/20 px-2 py-1.5">
          <summary className="cursor-pointer text-[11px] text-gray-500">
            给评审用的摘要（可展开）
          </summary>
          <div className="mt-2 space-y-1 text-[11px] text-gray-400" data-testid="eval-conclusion-pack">
            <p>
              发布意见：{String(conclusion.publish_decision || '—')} · 把握：
              {String(conclusion.sample?.confidence || '—')} · 历史次数：
              {String(conclusion.sample?.history_n ?? '—')}
            </p>
            <p>
              证据还不够的方向：
              {(conclusion.coverage.insufficient_slices || []).join(', ') || '无'}
            </p>
            {conclusion.coverage.note ? <p>{conclusion.coverage.note}</p> : null}
          </div>
        </details>
      ) : null}
    </section>
  );
}
