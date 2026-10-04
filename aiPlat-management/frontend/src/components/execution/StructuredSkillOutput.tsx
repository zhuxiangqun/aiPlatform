import React, { useMemo, useState } from 'react';
import { coerceSkillEnvelope } from './artifactDownloads';
import {
  extractCodingDeliveryText,
  langFromPath,
  parseFileDelivery,
  persistRootFromPayload,
} from './fileDelivery';
import { tryParseJsonOrPythonLiteral } from './pythonLiteral';
import { unwrapExecuteProduct } from './executeProduct';

function tryParseJson(text: string): unknown | null {
  return tryParseJsonOrPythonLiteral(text);
}

function looksLikePrd(obj: unknown): obj is Record<string, unknown> {
  if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return false;
  const o = obj as Record<string, unknown>;
  return (
    Array.isArray(o.functional_requirements) ||
    Array.isArray(o.user_stories) ||
    (o.constraints != null && typeof o.constraints === 'object' && !Array.isArray(o.components) && !Array.isArray(o.folder_structure)) ||
    Array.isArray(o.open_questions) ||
    (typeof o.title === 'string' && (o.description != null || o.decisions != null) && !Array.isArray(o.components) && !Array.isArray(o.folder_structure))
  );
}

function looksLikeArchitecture(obj: unknown): obj is Record<string, unknown> {
  if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return false;
  const o = obj as Record<string, unknown>;
  if (Array.isArray(o.functional_requirements)) return false;
  return (
    Array.isArray(o.components) ||
    Array.isArray(o.folder_structure) ||
    Array.isArray(o.api_contracts) ||
    Array.isArray(o.api_design) ||
    Array.isArray(o.data_model) ||
    Array.isArray(o.data_flow) ||
    Array.isArray(o.agents) ||
    Array.isArray(o.design_decisions) ||
    o.document_type === 'architecture_design' ||
    o.architecture_mode === 'code' ||
    o.architecture_mode === 'agent' ||
    (o.tech_stack != null && typeof o.tech_stack === 'object') ||
    (typeof o.overview === 'string' && (o.security != null || o['6_weeks_pilot'] != null || o.rollout_and_risks != null))
  );
}

/** Deep-unwrap common execute envelopes until PRD-shaped or exhausted. */
function extractPrd(raw: unknown, text?: string): Record<string, unknown> | null {
  const queue: unknown[] = [];
  const seen = new Set<unknown>();
  const push = (v: unknown) => {
    if (v == null || seen.has(v)) return;
    seen.add(v);
    queue.push(v);
  };
  push(coerceSkillEnvelope(raw));
  if (text) push(tryParseJson(text));

  while (queue.length) {
    const cur = queue.shift();
    if (looksLikePrd(cur)) return cur as Record<string, unknown>;
    if (!cur || typeof cur !== 'object' || Array.isArray(cur)) continue;
    const o = cur as Record<string, unknown>;
    for (const k of ['output', 'prd', 'result', 'data', 'payload']) {
      if (o[k] != null) push(typeof o[k] === 'string' ? tryParseJson(String(o[k])) ?? o[k] : o[k]);
    }
  }
  return null;
}

/** Deep-unwrap until architecture-shaped JSON is found. */
function extractArchitecture(raw: unknown, text?: string): Record<string, unknown> | null {
  const queue: unknown[] = [];
  const seen = new Set<unknown>();
  const push = (v: unknown) => {
    if (v == null || seen.has(v)) return;
    seen.add(v);
    queue.push(v);
  };
  push(coerceSkillEnvelope(raw));
  if (typeof raw === 'object' && raw != null) push(raw);
  if (typeof raw === 'string') push(tryParseJson(raw));
  if (text) {
    push(tryParseJson(text));
    // Agent often stringifies the object into resultText — parse again after strip
    const plain = String(text).replace(/^\uFEFF/, '').trim();
    if (plain !== text) push(tryParseJson(plain));
  }

  while (queue.length) {
    const cur = queue.shift();
    if (looksLikeArchitecture(cur)) return cur as Record<string, unknown>;
    if (typeof cur === 'string') {
      push(tryParseJson(cur));
      continue;
    }
    if (!cur || typeof cur !== 'object' || Array.isArray(cur)) continue;
    const o = cur as Record<string, unknown>;
    for (const k of [
      'output',
      'result',
      'data',
      'payload',
      'architecture',
      'answer',
      'response',
      'content',
      'text',
      'message',
    ]) {
      if (o[k] == null) continue;
      const v = o[k];
      if (typeof v === 'string') push(tryParseJson(v) ?? v);
      else push(v);
    }
  }
  return null;
}

function asList(v: unknown): string[] {
  if (v == null) return [];
  if (typeof v === 'string') return v.trim() ? [v.trim()] : [];
  if (Array.isArray(v)) {
    return v
      .map((x) => {
        if (typeof x === 'string') return x.trim();
        if (x && typeof x === 'object') {
          const o = x as Record<string, unknown>;
          if (o.label != null || o.value != null) {
            const lab = fmtVal(o.label);
            const val = fmtVal(o.value);
            if (lab && val && lab !== val) return `${lab}：${val}`;
            return val || lab;
          }
          return String(o.description || o.text || o.name || fmtVal(o) || '').trim();
        }
        return String(x || '').trim();
      })
      .filter(Boolean);
  }
  if (typeof v === 'object') {
    return Object.entries(v as Record<string, unknown>).map(([k, val]) => {
      if (Array.isArray(val)) return `${k}：${val.map(fmtVal).join('；')}`;
      return `${k}：${fmtVal(val)}`;
    });
  }
  return [String(v)];
}

function fmtVal(v: unknown): string {
  if (v == null) return '';
  if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') return String(v);
  if (Array.isArray(v)) return v.map(fmtVal).filter(Boolean).join('；');
  if (typeof v === 'object') {
    try {
      return JSON.stringify(v);
    } catch {
      return '';
    }
  }
  return String(v);
}

function acTexts(item: Record<string, unknown>): string[] {
  const ac = item.acceptance_criteria;
  if (typeof ac === 'string') return ac.trim() ? [ac.trim()] : [];
  if (!Array.isArray(ac)) return [];
  return ac
    .map((x) => {
      if (typeof x === 'string') return x.trim();
      if (x && typeof x === 'object') {
        const o = x as Record<string, unknown>;
        return String(o.description || o.text || o.label || o.name || '').trim();
      }
      return '';
    })
    .filter(Boolean);
}

function frTitle(fr: Record<string, unknown>, idx: number): { id: string; name: string } {
  const id = String(fr.id || fr.label || `FR-${idx + 1}`).trim();
  const name = String(fr.name || fr.label || fr.description || id).trim();
  return { id, name };
}

const PRIORITY_CLS: Record<string, string> = {
  high: 'bg-rose-500/15 text-rose-200 border-rose-500/35',
  medium: 'bg-amber-500/15 text-amber-200 border-amber-500/35',
  standard: 'bg-amber-500/15 text-amber-200 border-amber-500/35',
  low: 'bg-slate-500/15 text-slate-300 border-slate-500/30',
};

const Section: React.FC<{
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
  tone?: 'sky' | 'emerald' | 'amber' | 'violet' | 'slate' | 'indigo' | 'cyan';
  badge?: string;
}> = ({ title, children, defaultOpen = true, tone = 'slate', badge }) => {
  const [open, setOpen] = useState(defaultOpen);
  const toneCls: Record<string, string> = {
    sky: 'border-sky-500/25 bg-sky-500/5',
    emerald: 'border-emerald-500/25 bg-emerald-500/5',
    amber: 'border-amber-500/25 bg-amber-500/5',
    violet: 'border-violet-500/25 bg-violet-500/5',
    slate: 'border-dark-border bg-dark-card/40',
    indigo: 'border-indigo-500/25 bg-indigo-500/5',
    cyan: 'border-cyan-500/25 bg-cyan-500/5',
  };
  return (
    <div className={`rounded-lg border ${toneCls[tone]} overflow-hidden`}>
      <button
        type="button"
        className="w-full flex items-center justify-between gap-2 px-3 py-2 text-left hover:bg-white/[0.02]"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="flex items-center gap-2 min-w-0">
          <span className="text-xs font-semibold text-gray-200 truncate">{title}</span>
          {badge ? (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-dark-bg/70 text-gray-400 border border-dark-border shrink-0">
              {badge}
            </span>
          ) : null}
        </span>
        <span className="text-[10px] text-gray-500 shrink-0">{open ? '收起' : '展开'}</span>
      </button>
      {open ? <div className="px-3 pb-3 pt-0 space-y-2 border-t border-white/5">{children}</div> : null}
    </div>
  );
};

const PrdOverview: React.FC<{ data: Record<string, unknown> }> = ({ data }) => {
  const title = String(data.title || data.name || '需求分析产物').trim();
  const desc = String(data.description || '').trim();
  const frs = Array.isArray(data.functional_requirements)
    ? (data.functional_requirements as Record<string, unknown>[])
    : [];
  const stories = Array.isArray(data.user_stories) ? (data.user_stories as Record<string, unknown>[]) : [];
  const constraints = data.constraints;
  const perf = asList(
    constraints && typeof constraints === 'object' && !Array.isArray(constraints)
      ? (constraints as any).performance
      : null,
  );
  const secu = asList(
    constraints && typeof constraints === 'object' && !Array.isArray(constraints)
      ? (constraints as any).security
      : Array.isArray(constraints)
        ? constraints
        : typeof constraints === 'string'
          ? constraints
          : null,
  );
  const decisions = data.decisions;
  const decisionItems =
    decisions && typeof decisions === 'object' && !Array.isArray(decisions)
      ? Object.entries(decisions as Record<string, unknown>).map(([k, v]) => ({ k, v: fmtVal(v) }))
      : Array.isArray(decisions)
        ? (decisions as any[]).map((d, i) => ({
            k: String(d?.id || d?.label || `D${i + 1}`),
            v: fmtVal(d?.description ?? d?.rationale ?? d?.label ?? d),
          }))
        : [];
  const oqs = asList(data.open_questions);
  const [showRaw, setShowRaw] = useState(false);

  // Hide US section when it mostly mirrors FR names (noise)
  const frNames = new Set(
    frs
      .map((f, i) => {
        const { name } = frTitle(f, i);
        return name;
      })
      .filter(Boolean),
  );
  const storiesDistinct = stories.filter((us, idx) => {
    const n = String(us.name || us.label || us.description || '').trim();
    return n && !frNames.has(n);
  });
  const showStories = storiesDistinct.length > 0 ? storiesDistinct : stories.length > frs.length ? stories : [];

  return (
    <div className="flex flex-col gap-3">
      {/* Hero */}
      <div className="rounded-xl border border-sky-500/25 bg-gradient-to-br from-sky-500/10 via-dark-card/40 to-transparent px-3.5 py-3">
        <div className="text-[10px] uppercase tracking-wider text-sky-300/70 mb-1">需求分析产物</div>
        <div className="text-base font-semibold text-gray-50 leading-snug break-words">{title}</div>
        {desc ? <p className="mt-1.5 text-xs text-gray-400 leading-relaxed break-words">{desc}</p> : null}
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {frs.length > 0 ? (
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-200/90 border border-emerald-500/30">
              {frs.length} 条功能需求
            </span>
          ) : null}
          {secu.length > 0 ? (
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-violet-500/10 text-violet-200/90 border border-violet-500/30">
              安全约束 {secu.length}
            </span>
          ) : null}
          {oqs.length > 0 ? (
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-100 border border-amber-500/35">
              {oqs.length} 项待确认
            </span>
          ) : (
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-200/80 border border-emerald-500/25">
              无待确认项
            </span>
          )}
        </div>
      </div>

      {/* Open questions first when present — draft signal */}
      {oqs.length > 0 ? (
        <Section title="待确认" badge={String(oqs.length)} tone="amber" defaultOpen>
          <ol className="list-decimal ml-4 space-y-1.5">
            {oqs.map((q, i) => (
              <li key={i} className="text-xs text-amber-50/90 leading-relaxed pl-0.5 break-words">
                {q}
              </li>
            ))}
          </ol>
        </Section>
      ) : null}

      {frs.length > 0 ? (
        <Section title="功能需求" badge={String(frs.length)} tone="emerald">
          <div className="space-y-2.5">
            {frs.map((fr, idx) => {
              const { id, name } = frTitle(fr, idx);
              const priority = String(fr.priority || '').trim().toLowerCase();
              const acs = acTexts(fr);
              const descFr = fr.description ? String(fr.description) : '';
              const showDesc = Boolean(descFr && descFr !== name && descFr !== id);
              return (
                <div
                  key={`${id}-${idx}`}
                  className="rounded-lg border border-emerald-500/15 bg-dark-bg/35 px-2.5 py-2"
                >
                  <div className="flex items-start gap-2 flex-wrap">
                    <span className="font-mono text-[10px] text-emerald-300/90 mt-0.5 shrink-0">{id}</span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="text-xs text-gray-100 font-medium leading-snug break-words">{name}</span>
                        {priority ? (
                          <span
                            className={`text-[10px] px-1.5 py-0.5 rounded border ${
                              PRIORITY_CLS[priority] || PRIORITY_CLS.low
                            }`}
                          >
                            {priority}
                          </span>
                        ) : null}
                      </div>
                      {showDesc ? (
                        <p className="mt-1 text-[11px] text-gray-500 leading-relaxed break-words">{descFr}</p>
                      ) : null}
                    </div>
                  </div>
                  {acs.length > 0 ? (
                    <div className="mt-2 pl-1 space-y-1">
                      <div className="text-[10px] text-gray-500">验收标准</div>
                      {acs.map((ac, i) => (
                        <div
                          key={i}
                          className="flex gap-1.5 text-[11px] text-gray-300 leading-relaxed"
                        >
                          <span className="text-emerald-400/70 shrink-0 mt-px">✓</span>
                          <span className="min-w-0 break-words">{ac}</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="mt-1.5 text-[11px] text-amber-300/80">无验收标准</p>
                  )}
                </div>
              );
            })}
          </div>
        </Section>
      ) : null}

      {(perf.length > 0 || secu.length > 0) && (
        <Section title="约束" tone="violet" defaultOpen badge={String(perf.length + secu.length)}>
          <div className="flex flex-col gap-2.5">
            <div className="rounded-md bg-dark-bg/40 border border-dark-border/80 px-2.5 py-2.5">
              <div className="text-[10px] font-medium text-violet-200/80 mb-1.5">
                性能 Performance
                {perf.length ? <span className="text-gray-600 font-normal"> · {perf.length}</span> : null}
              </div>
              {perf.length ? (
                <ul className="space-y-1.5">
                  {perf.map((p, i) => (
                    <li key={i} className="text-xs text-gray-300 leading-relaxed flex gap-1.5">
                      <span className="text-violet-400/50 shrink-0">·</span>
                      <span className="min-w-0 break-words">{p}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="text-[11px] text-gray-600">未填写</div>
              )}
            </div>
            <div className="rounded-md bg-dark-bg/40 border border-dark-border/80 px-2.5 py-2.5">
              <div className="text-[10px] font-medium text-violet-200/80 mb-1.5">
                安全 Security
                {secu.length ? <span className="text-gray-600 font-normal"> · {secu.length}</span> : null}
              </div>
              {secu.length ? (
                <ul className="space-y-1.5">
                  {secu.map((p, i) => (
                    <li key={i} className="text-xs text-gray-300 leading-relaxed flex gap-1.5">
                      <span className="text-violet-400/50 shrink-0">·</span>
                      <span className="min-w-0 break-words">{p}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="text-[11px] text-gray-600">未填写</div>
              )}
            </div>
          </div>
        </Section>
      )}

      {decisionItems.length > 0 ? (
        <Section title="决策" badge={String(decisionItems.length)} tone="sky" defaultOpen>
          <div className="space-y-2">
            {decisionItems.map(({ k, v }) => (
              <div
                key={k}
                className="flex flex-col gap-1 text-xs rounded-md bg-dark-bg/30 px-2.5 py-2 border border-sky-500/10"
              >
                <span className="font-mono text-[10px] text-sky-300/90 break-all" title={k}>
                  {k}
                </span>
                <span className="text-gray-300 leading-relaxed break-words whitespace-pre-wrap">{v}</span>
              </div>
            ))}
          </div>
        </Section>
      ) : null}

      {showStories.length > 0 ? (
        <Section title="用户故事" badge={String(showStories.length)} defaultOpen>
          <ul className="space-y-2">
            {showStories.map((us, idx) => {
              const id = String(us.id || us.label || `US-${idx + 1}`);
              const body = String(us.name || us.label || us.description || us.story || '').trim();
              return (
                <li
                  key={`${id}-${idx}`}
                  className="text-xs flex flex-col gap-0.5 rounded-md bg-dark-bg/30 border border-dark-border/70 px-2.5 py-2"
                >
                  <span className="font-mono text-[10px] text-gray-500">{id}</span>
                  <span className="text-gray-300 leading-relaxed break-words">{body}</span>
                </li>
              );
            })}
          </ul>
        </Section>
      ) : null}

      <div className="rounded-lg border border-dark-border/80 bg-dark-bg/30">
        <button
          type="button"
          className="w-full flex items-center justify-between px-3 py-1.5 text-[11px] text-gray-500 hover:text-gray-400"
          onClick={() => setShowRaw((v) => !v)}
        >
          <span>原始 JSON</span>
          <span>{showRaw ? '收起' : '展开复制用'}</span>
        </button>
        {showRaw ? (
          <pre className="px-3 pb-3 text-[10px] text-gray-500 overflow-auto max-h-48 whitespace-pre-wrap break-words border-t border-dark-border/50 pt-2">
            {JSON.stringify(data, null, 2)}
          </pre>
        ) : null}
      </div>
    </div>
  );
};

const ArchitectureOverview: React.FC<{ data: Record<string, unknown> }> = ({ data }) => {
  const [showRaw, setShowRaw] = useState(false);
  const title = String(data.title || data.name || '系统架构产物').trim();
  const mode = String(data.architecture_mode || data.document_type || '').trim();
  const context = String(data.context || data.overview || data.description || '').trim();
  const components = Array.isArray(data.components)
    ? (data.components as Record<string, unknown>[])
    : Array.isArray(data.folder_structure)
      ? (data.folder_structure as Record<string, unknown>[])
      : [];
  const apisFromTop = Array.isArray(data.api_contracts)
    ? (data.api_contracts as Record<string, unknown>[])
    : Array.isArray(data.api_design)
      ? (data.api_design as Record<string, unknown>[])
      : [];
  const apisNested: Record<string, unknown>[] = [];
  for (const c of components) {
    const iface = c.interfaces ?? c.apis ?? c.endpoints;
    if (Array.isArray(iface)) {
      for (const row of iface) {
        if (row && typeof row === 'object') {
          apisNested.push({
            ...(row as Record<string, unknown>),
            _component: String(c.name || c.layer || ''),
          });
        }
      }
    }
  }
  const apis = apisFromTop.length ? apisFromTop : apisNested;
  const models = Array.isArray(data.data_model) ? (data.data_model as Record<string, unknown>[]) : [];
  const agents = Array.isArray(data.agents) ? (data.agents as Record<string, unknown>[]) : [];
  const decisions = Array.isArray(data.design_decisions)
    ? (data.design_decisions as Record<string, unknown>[])
    : [];
  const dataFlow = Array.isArray(data.data_flow) ? (data.data_flow as Record<string, unknown>[]) : [];
  const tech =
    data.tech_stack && typeof data.tech_stack === 'object' && !Array.isArray(data.tech_stack)
      ? (data.tech_stack as Record<string, unknown>)
      : null;
  const deploy =
    data.deployment && typeof data.deployment === 'object' && !Array.isArray(data.deployment)
      ? (data.deployment as Record<string, unknown>)
      : data.deployment != null
        ? { note: data.deployment }
        : null;
  const security = data.security != null ? fmtVal(data.security) : '';
  const rollout =
    (data.rollout_and_risks && typeof data.rollout_and_risks === 'object'
      ? (data.rollout_and_risks as Record<string, unknown>)
      : null)
    || (data['6_weeks_pilot'] && typeof data['6_weeks_pilot'] === 'object'
      ? (data['6_weeks_pilot'] as Record<string, unknown>)
      : null);
  const risks = asList(
    data.risks
      ?? data.risk_list
      ?? data.pilot_risks
      ?? (rollout ? rollout.risks : undefined),
  );
  const phases = Array.isArray(rollout?.phases) ? (rollout!.phases as Record<string, unknown>[]) : [];
  const assumptions = asList(data.assumptions ?? data.open_questions);
  const blob = JSON.stringify(data);
  const cloudRisk =
    /阿里云|OSS|\bS3\b|公有云|对象存储/.test(blob) &&
    /不可上公网|不上公网|不外传|不能传到公网/.test(blob);

  return (
    <div className="flex flex-col gap-3">
      <div className="rounded-xl border border-indigo-500/25 bg-gradient-to-br from-indigo-500/10 via-dark-card/40 to-transparent px-3.5 py-3">
        <div className="text-[10px] uppercase tracking-wider text-indigo-300/70 mb-1">系统架构产物</div>
        <div className="text-base font-semibold text-gray-50 leading-snug break-words">{title}</div>
        {mode ? <div className="mt-1 text-[10px] text-indigo-200/70 font-mono">{mode}</div> : null}
        {context ? <p className="mt-1.5 text-xs text-gray-400 leading-relaxed break-words">{context}</p> : null}
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {components.length > 0 ? (
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-100 border border-indigo-500/30">
              {components.length} 个组件
            </span>
          ) : null}
          {apis.length > 0 ? (
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-sky-500/10 text-sky-100 border border-sky-500/30">
              {apis.length} 个 API
            </span>
          ) : null}
          {dataFlow.length > 0 ? (
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-100 border border-cyan-500/30">
              {dataFlow.length} 步数据流
            </span>
          ) : null}
          {models.length > 0 ? (
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-violet-500/10 text-violet-100 border border-violet-500/30">
              {models.length} 个数据实体
            </span>
          ) : null}
          {phases.length > 0 ? (
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-100 border border-amber-500/30">
              {phases.length} 个分期
            </span>
          ) : null}
          {tech
            ? Object.entries(tech)
                .slice(0, 6)
                .map(([k, v]) => (
                  <span
                    key={k}
                    className="text-[10px] px-2 py-0.5 rounded-full bg-dark-bg/60 text-gray-300 border border-dark-border"
                  >
                    {k}: {fmtVal(v)}
                  </span>
                ))
            : null}
        </div>
        {cloudRisk ? (
          <div className="mt-2 text-[11px] text-rose-300/90 border border-rose-500/30 bg-rose-500/10 rounded-md px-2 py-1">
            ⚠ 产物中出现公有云/对象存储表述，请对照「照片不上公网」约束复核。
          </div>
        ) : null}
      </div>

      {components.length > 0 ? (
        <Section title="组件 / 目录结构" badge={String(components.length)} tone="indigo" defaultOpen>
          <div className="space-y-2">
            {components.map((c, idx) => {
              const name = String(c.name || c.layer || `#${idx + 1}`);
              const layer = c.layer != null && String(c.layer) !== name ? String(c.layer) : '';
              const techStr = c.tech != null ? fmtVal(c.tech) : '';
              const resp = Array.isArray(c.responsibility)
                ? (c.responsibility as unknown[]).map(String).join('；')
                : c.responsibility != null
                  ? fmtVal(c.responsibility)
                  : c.description != null
                    ? fmtVal(c.description)
                    : '';
              return (
                <div key={`${name}-${idx}`} className="rounded-lg border border-dark-border/70 bg-dark-bg/40 px-3 py-2">
                  <div className="flex flex-wrap items-baseline gap-2">
                    <span className="text-xs font-medium text-gray-100">{name}</span>
                    {layer ? <span className="text-[10px] text-indigo-200/80">{layer}</span> : null}
                    {techStr ? <span className="text-[10px] font-mono text-gray-500">{techStr}</span> : null}
                  </div>
                  {resp ? <p className="mt-1 text-[11px] text-gray-400 leading-relaxed">{resp}</p> : null}
                </div>
              );
            })}
          </div>
        </Section>
      ) : null}

      {apis.length > 0 ? (
        <Section title="API 契约" badge={String(apis.length)} tone="sky" defaultOpen>
          <div className="space-y-2">
            {apis.map((a, idx) => {
              const method = String(a.method || a.http_method || '').toUpperCase();
              const path = String(a.path || a.url || a.endpoint || '');
              const desc = String(a.description || '').trim();
              const comp = a._component ? String(a._component) : '';
              return (
                <div key={`${method}-${path}-${idx}`} className="rounded-lg border border-dark-border/70 bg-dark-bg/40 px-3 py-2">
                  <div className="text-xs font-mono text-sky-200">
                    {method ? <span className="text-sky-300 font-semibold">{method}</span> : null}
                    {path ? <span className="ml-2 text-gray-200">{path}</span> : null}
                    {!method && !path ? <span>#{idx + 1}</span> : null}
                  </div>
                  {comp ? <div className="mt-0.5 text-[10px] text-gray-500">组件 · {comp}</div> : null}
                  {desc ? <p className="mt-1 text-[11px] text-gray-400">{desc}</p> : null}
                  {(a.request != null || a.response != null) ? (
                    <div className="mt-1.5 grid gap-1 text-[10px] text-gray-500 font-mono">
                      {a.request != null ? <div>req: {fmtVal(a.request)}</div> : null}
                      {a.response != null ? <div>res: {fmtVal(a.response)}</div> : null}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        </Section>
      ) : null}

      {dataFlow.length > 0 ? (
        <Section title="数据流" badge={String(dataFlow.length)} tone="cyan" defaultOpen>
          <ol className="space-y-2 list-decimal list-inside">
            {dataFlow.map((step, idx) => (
              <li key={idx} className="text-[11px] text-gray-300 leading-relaxed">
                <span className="text-gray-100 font-medium">
                  {String(step.description || step.name || `步骤 ${step.step ?? idx + 1}`)}
                </span>
                {step.details != null ? (
                  <span className="text-gray-500"> — {fmtVal(step.details)}</span>
                ) : null}
              </li>
            ))}
          </ol>
        </Section>
      ) : null}

      {security ? (
        <Section title="安全与合规" tone="emerald" defaultOpen>
          <pre className="text-[11px] text-gray-300 whitespace-pre-wrap break-words font-sans">{security}</pre>
        </Section>
      ) : null}

      {(phases.length > 0 || risks.length > 0) ? (
        <Section title="分期与风险" tone="amber" defaultOpen>
          {phases.length > 0 ? (
            <div className="space-y-2 mb-2">
              {phases.map((p, idx) => (
                <div key={idx} className="rounded-lg border border-dark-border/70 bg-dark-bg/40 px-3 py-2">
                  <div className="text-xs text-amber-100 font-medium">
                    {String(p.phase || p.name || `Phase ${idx + 1}`)}
                  </div>
                  {p.description != null ? (
                    <p className="mt-0.5 text-[11px] text-gray-300">{fmtVal(p.description)}</p>
                  ) : null}
                  {p.details != null ? (
                    <p className="mt-0.5 text-[11px] text-gray-500">{fmtVal(p.details)}</p>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}
          {risks.length > 0 ? (
            <ul className="list-disc list-inside text-[11px] text-gray-400 space-y-0.5">
              {risks.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          ) : null}
        </Section>
      ) : null}

      {models.length > 0 ? (
        <Section title="数据实体" badge={String(models.length)} tone="violet">
          <GenericValue value={models} depth={0} />
        </Section>
      ) : null}
      {agents.length > 0 ? (
        <Section title="Agents" badge={String(agents.length)} tone="slate">
          <GenericValue value={agents} depth={0} />
        </Section>
      ) : null}
      {decisions.length > 0 ? (
        <Section title="设计决策" badge={String(decisions.length)} tone="slate">
          <GenericValue value={decisions} depth={0} />
        </Section>
      ) : null}
      {deploy ? (
        <Section title="部署" tone="slate">
          <GenericValue value={deploy} depth={0} />
        </Section>
      ) : null}
      {assumptions.length > 0 ? (
        <Section title="假设 / 待确认" badge={String(assumptions.length)} tone="slate" defaultOpen>
          <ul className="list-disc list-inside text-[11px] text-gray-400 space-y-0.5">
            {assumptions.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
        </Section>
      ) : null}

      <div className="rounded-lg border border-dark-border/60 bg-dark-card/30">
        <button
          type="button"
          className="w-full flex items-center justify-between px-3 py-2 text-[11px] text-gray-500 hover:text-gray-300"
          onClick={() => setShowRaw((v) => !v)}
        >
          <span>原始 JSON</span>
          <span>{showRaw ? '收起' : '展开复制用'}</span>
        </button>
        {showRaw ? (
          <pre className="px-3 pb-3 text-[10px] text-gray-500 overflow-auto max-h-48 whitespace-pre-wrap break-words border-t border-dark-border/50 pt-2">
            {JSON.stringify(data, null, 2)}
          </pre>
        ) : null}
      </div>
    </div>
  );
};
type JsonSchemaLike = {
  type?: string;
  description?: string;
  properties?: Record<string, JsonSchemaLike>;
  items?: JsonSchemaLike;
  'x-display-profile'?: string;
  'x-aiplat'?: { display_profile?: string };
  [k: string]: unknown;
};

type DisplayProfile = 'prd' | 'architecture';

type Props = {
  text?: string;
  raw?: unknown;
  /**
   * Skill `output_schema` — drives section order + labels.
   * Extension point: new Skill declares schema; UI needs no field whitelist.
   */
  schema?: JsonSchemaLike | Record<string, unknown> | null;
  /** Force specialty layout; prefer schema `x-display-profile` or payload `document_type`. */
  displayProfile?: DisplayProfile | string | null;
};

/** Resolve a usable object-schema from Skill output_schema (may nest under prd / result / …). */
function resolveObjectSchema(schema: unknown): JsonSchemaLike | null {
  if (!schema || typeof schema !== 'object' || Array.isArray(schema)) return null;
  const s = schema as JsonSchemaLike;
  if (s.properties && typeof s.properties === 'object') return s;
  // Common Skill shape: { prd: { type: object, properties }, markdown: {...} }
  for (const v of Object.values(s)) {
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      const child = v as JsonSchemaLike;
      if (child.properties && typeof child.properties === 'object') return child;
      if (child.type === 'object' && child.properties) return child;
    }
  }
  return s.properties ? s : null;
}

/**
 * Specialty layouts — keyed by Skill-declared profile / document_type, NOT by sniffing
 * business field names (functional_requirements / components / …).
 */
const DOCUMENT_TYPE_PROFILE: Record<string, DisplayProfile> = {
  architecture_design: 'architecture',
  prd: 'prd',
  requirement_analysis: 'prd',
  requirements: 'prd',
};

function profileFromSchema(schema: unknown): DisplayProfile | null {
  if (!schema || typeof schema !== 'object' || Array.isArray(schema)) return null;
  const s = schema as JsonSchemaLike;
  const raw =
    s['x-display-profile'] ||
    s['x-aiplat']?.display_profile ||
    (typeof (s as any).display_profile === 'string' ? (s as any).display_profile : null);
  const v = String(raw || '')
    .trim()
    .toLowerCase();
  if (v === 'prd' || v === 'architecture') return v;
  // Nested under envelope key (e.g. output_schema.prd)
  for (const child of Object.values(s)) {
    if (!child || typeof child !== 'object' || Array.isArray(child)) continue;
    const nested = profileFromSchema(child);
    if (nested) return nested;
  }
  return null;
}

function resolveDisplayProfile(
  payload: unknown,
  schema: unknown,
  explicit?: string | null,
): DisplayProfile | null {
  const ex = String(explicit || '')
    .trim()
    .toLowerCase();
  if (ex === 'prd' || ex === 'architecture') return ex;
  const fromSchema = profileFromSchema(schema);
  if (fromSchema) return fromSchema;
  if (payload && typeof payload === 'object' && !Array.isArray(payload)) {
    const dt = String((payload as Record<string, unknown>).document_type || '')
      .trim()
      .toLowerCase();
    if (dt && DOCUMENT_TYPE_PROFILE[dt]) return DOCUMENT_TYPE_PROFILE[dt];
    // Shape sniff when Skill forgot x-display-profile / document_type
    if (looksLikeArchitecture(payload)) return 'architecture';
    if (looksLikePrd(payload)) return 'prd';
  }
  return null;
}

const META_SKIP = new Set([
  '_meta',
  'meta',
  'trace_id',
  'traceId',
  'request_id',
  'requestId',
  'raw',
  'debug',
]);

function humanizeKey(k: string): string {
  return k
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/_/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function isParagraph(s: string): boolean {
  return s.length > 96 || s.includes('\n') || /[。！？.!?]\s/.test(s);
}

/** Structural card title: first short string field (no business key whitelist). */
function itemPrimaryLabel(item: unknown, idx: number): string {
  if (item == null) return `#${idx + 1}`;
  if (typeof item !== 'object') return String(item).slice(0, 80);
  const o = item as Record<string, unknown>;
  for (const [, v] of Object.entries(o)) {
    if (typeof v === 'string' && v.trim() && !isParagraph(v.trim())) return v.trim().slice(0, 120);
  }
  // HTTP-ish pair without naming the domain: method + path-like sibling
  const method = o.method ?? o.http_method;
  const path = o.path ?? o.url ?? o.endpoint;
  if (method != null && path != null) return `${String(method).toUpperCase()} ${String(path)}`;
  return `#${idx + 1}`;
}

/** Structural subtitle: first longer string field not equal to primary. */
function itemSecondary(item: unknown, primary: string): string {
  if (!item || typeof item !== 'object') return '';
  const o = item as Record<string, unknown>;
  for (const [, v] of Object.entries(o)) {
    if (typeof v !== 'string') continue;
    const s = v.trim();
    if (!s || s === primary) continue;
    if (isParagraph(s) || s.length >= 24) return s;
  }
  return '';
}

function schemaLabel(schema: JsonSchemaLike | null, key: string): string {
  const prop = schema?.properties?.[key];
  const desc = typeof prop?.description === 'string' ? prop.description.trim() : '';
  // Prefer short schema description as section title; else humanize key
  if (desc && desc.length <= 40 && !desc.includes('（') && !desc.includes('(')) return desc;
  return humanizeKey(key);
}

function orderedObjectKeys(obj: Record<string, unknown>, schema: JsonSchemaLike | null): string[] {
  const own = Object.keys(obj).filter((k) => !META_SKIP.has(k));
  const structuralRank = (k: string): number => {
    const v = obj[k];
    if (Array.isArray(v)) return 0;
    if (v && typeof v === 'object') return 1;
    if (typeof v === 'string' && v.length > 80) return 2;
    return 3;
  };
  const byStructure = (a: string, b: string) =>
    structuralRank(a) - structuralRank(b) || a.localeCompare(b);

  if (!schema?.properties) return [...own].sort(byStructure);
  const fromSchema = Object.keys(schema.properties).filter((k) => own.includes(k));
  const rest = own.filter((k) => !fromSchema.includes(k)).sort(byStructure);
  return [...fromSchema, ...rest];
}

function pickHeroTitle(obj: Record<string, unknown>): { title: string; subtitle: string; used: Set<string> } {
  const used = new Set<string>();
  let title = '执行产物';
  let subtitle = '';
  // Universal conventions only (JSON Schema / OpenAPI style) — not business fields
  for (const k of ['title', 'name', 'label']) {
    const v = obj[k];
    if (typeof v === 'string' && v.trim()) {
      title = v.trim();
      used.add(k);
      break;
    }
  }
  for (const k of ['summary', 'description', 'context', 'overview']) {
    const v = obj[k];
    if (typeof v === 'string' && v.trim() && v.trim() !== title) {
      subtitle = v.trim();
      used.add(k);
      break;
    }
  }
  if (title === '执行产物') {
    for (const [k, v] of Object.entries(obj)) {
      if (META_SKIP.has(k)) continue;
      if (typeof v === 'string' && v.trim() && !isParagraph(v.trim())) {
        title = v.trim();
        used.add(k);
        break;
      }
    }
  }
  return { title, subtitle, used };
}

/** Dig through common execute envelopes to a renderable object/array. */
function unwrapRenderable(raw: unknown, text?: string): unknown | null {
  const queue: unknown[] = [];
  const seen = new Set<unknown>();
  const push = (v: unknown) => {
    if (v == null || seen.has(v)) return;
    seen.add(v);
    queue.push(v);
  };
  push(unwrapExecuteProduct(raw));
  if (text) push(unwrapExecuteProduct(text));
  push(coerceSkillEnvelope(raw));
  if (typeof raw === 'object' && raw != null) push(raw);
  if (typeof raw === 'string') push(tryParseJson(raw));
  if (text) push(tryParseJson(text));

  const WRAPPER = new Set([
    'output',
    'result',
    'data',
    'payload',
    'answer',
    'response',
    'content',
    'text',
    'message',
    'success',
    'ok',
    'error',
  ]);

  while (queue.length) {
    const cur = queue.shift();
    if (typeof cur === 'string') {
      push(tryParseJson(cur));
      continue;
    }
    if (Array.isArray(cur)) return cur;
    if (!cur || typeof cur !== 'object') continue;
    const o = cur as Record<string, unknown>;
    const keys = Object.keys(o);
    const wrapperOnly = keys.length <= 3 && keys.every((k) => WRAPPER.has(k));
    if (!wrapperOnly && keys.length > 0) return o;
    for (const k of [
      'output',
      'result',
      'data',
      'payload',
      'answer',
      'response',
      'content',
      'text',
      'message',
    ]) {
      if (o[k] == null) continue;
      const v = o[k];
      if (typeof v === 'string') push(tryParseJson(v) ?? v);
      else push(v);
    }
  }
  return null;
}

const GenericValue: React.FC<{ value: unknown; depth?: number }> = ({ value, depth = 0 }) => {
  if (value == null) return <span className="text-gray-500">—</span>;
  if (typeof value === 'boolean') {
    return <span className="text-sky-200/90">{value ? 'true' : 'false'}</span>;
  }
  if (typeof value === 'number') {
    return <span className="font-mono text-gray-200">{value}</span>;
  }
  if (typeof value === 'string') {
    const s = value.trim();
    if (!s) return <span className="text-gray-500">—</span>;
    if ((s.startsWith('{') || s.startsWith('[')) && s.length > 2) {
      const parsed = tryParseJson(s);
      if (parsed != null) return <GenericValue value={parsed} depth={depth} />;
    }
    return <span className="text-xs text-gray-300 leading-relaxed break-words whitespace-pre-wrap">{s}</span>;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-gray-500">（空列表）</span>;
    const allScalar = value.every(
      (x) => x == null || typeof x === 'string' || typeof x === 'number' || typeof x === 'boolean',
    );
    if (allScalar) {
      return (
        <ul className="space-y-1">
          {value.slice(0, 40).map((x, i) => (
            <li key={i} className="text-xs text-gray-300 leading-relaxed flex gap-1.5">
              <span className="text-gray-500 shrink-0">·</span>
              <span className="break-words min-w-0">{fmtVal(x)}</span>
            </li>
          ))}
          {value.length > 40 ? (
            <li className="text-[10px] text-gray-500">…另有 {value.length - 40} 项</li>
          ) : null}
        </ul>
      );
    }
    return (
      <div className="space-y-2">
        {value.slice(0, 30).map((item, idx) => {
          const label = itemPrimaryLabel(item, idx);
          const secondary = itemSecondary(item, label);
          const rest =
            item && typeof item === 'object' && !Array.isArray(item)
              ? Object.entries(item as Record<string, unknown>).filter(([k, v]) => {
                  if (META_SKIP.has(k)) return false;
                  if (typeof v === 'string' && (v.trim() === label || v.trim() === secondary)) return false;
                  return true;
                })
              : [];
          return (
            <div
              key={idx}
              className="rounded-lg border border-dark-border/80 bg-dark-bg/35 px-2.5 py-2 space-y-1"
            >
              <div className="text-xs font-medium text-gray-100 break-words">{label}</div>
              {secondary ? (
                <p className="text-[11px] text-gray-400 leading-relaxed break-words">{secondary}</p>
              ) : null}
              {depth < 2 && rest.length > 0 ? (
                <div className="grid gap-1 pt-0.5">
                  {rest.slice(0, 12).map(([k, v]) => (
                    <div key={k} className="text-[10px] text-gray-500 flex gap-1.5 min-w-0">
                      <span className="shrink-0 text-gray-500/80">{humanizeKey(k)}</span>
                      <span className="text-gray-400 break-words min-w-0">
                        {typeof v === 'object' && v != null ? (
                          <GenericValue value={v} depth={depth + 1} />
                        ) : (
                          fmtVal(v)
                        )}
                      </span>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          );
        })}
        {value.length > 30 ? (
          <div className="text-[10px] text-gray-500">…另有 {value.length - 30} 项</div>
        ) : null}
      </div>
    );
  }
  if (typeof value === 'object') {
    if (depth >= 3) {
      return (
        <pre className="text-[10px] text-gray-500 whitespace-pre-wrap break-words max-h-32 overflow-auto">
          {JSON.stringify(value, null, 2)}
        </pre>
      );
    }
    const entries = Object.entries(value as Record<string, unknown>).filter(([k]) => !META_SKIP.has(k));
    if (entries.length === 0) return <span className="text-gray-500">（空）</span>;
    return (
      <div className="space-y-1.5">
        {entries.map(([k, v]) => (
          <div key={k} className="text-[11px] flex gap-2 min-w-0">
            <span className="text-gray-500 shrink-0 w-[7.5rem] truncate" title={k}>
              {humanizeKey(k)}
            </span>
            <div className="min-w-0 flex-1">
              <GenericValue value={v} depth={depth + 1} />
            </div>
          </div>
        ))}
      </div>
    );
  }
  return <span className="text-xs text-gray-300">{String(value)}</span>;
};

/**
 * Schema/structure-driven view for ANY JSON — no business field whitelist.
 * New Skill: declare output_schema (+ optional document_type); UI needs no code change.
 */
const GenericObjectOverview: React.FC<{ data: unknown; schema?: JsonSchemaLike | null }> = ({
  data,
  schema: schemaProp,
}) => {
  const [showRaw, setShowRaw] = useState(false);
  const schema = resolveObjectSchema(schemaProp);
  const root = data;
  const isArr = Array.isArray(root);
  const obj = !isArr && root && typeof root === 'object' ? (root as Record<string, unknown>) : null;

  const hero = obj ? pickHeroTitle(obj) : { title: isArr ? `列表（${(root as unknown[]).length}）` : '执行产物', subtitle: '', used: new Set<string>() };
  const typeChip =
    obj && typeof obj.document_type === 'string' && obj.document_type.trim()
      ? String(obj.document_type).trim()
      : obj && typeof obj.architecture_mode === 'string'
        ? String(obj.architecture_mode).trim()
        : '';

  const sections: { key: string; label: string; value: unknown; open: boolean }[] = [];
  if (isArr) {
    sections.push({ key: 'items', label: schema?.description || '条目', value: root, open: true });
  } else if (obj) {
    for (const k of orderedObjectKeys(obj, schema)) {
      if (hero.used.has(k) && ['title', 'name', 'label', 'summary', 'description', 'context'].includes(k)) continue;
      const v = obj[k];
      if (v == null) continue;
      if (typeof v === 'string' && !v.trim()) continue;
      if (Array.isArray(v) && v.length === 0) continue;
      const open =
        Array.isArray(v) ||
        (typeof v === 'object' && v != null) ||
        (typeof v === 'string' && v.length > 80);
      sections.push({ key: k, label: schemaLabel(schema, k), value: v, open });
    }
  }

  const chipEntries =
    obj != null
      ? Object.entries(obj)
          .filter(([k, v]) => {
            if (META_SKIP.has(k) || hero.used.has(k)) return false;
            if (typeof v === 'number' || typeof v === 'boolean') return true;
            if (typeof v === 'string' && v.length > 0 && v.length <= 48 && !isParagraph(v)) return true;
            if (Array.isArray(v)) return true;
            return false;
          })
          .slice(0, 8)
      : [];

  return (
    <div className="flex flex-col gap-3">
      <div className="rounded-xl border border-slate-500/25 bg-gradient-to-br from-slate-500/10 via-dark-card/40 to-transparent px-3.5 py-3">
        <div className="text-[10px] uppercase tracking-wider text-slate-300/70 mb-1">结构化产物</div>
        <div className="text-base font-semibold text-gray-50 leading-snug break-words">{hero.title}</div>
        {typeChip ? <div className="mt-1 text-[10px] text-slate-300/70 font-mono">{typeChip}</div> : null}
        {hero.subtitle && hero.subtitle !== hero.title ? (
          <p className="mt-1.5 text-xs text-gray-400 leading-relaxed break-words line-clamp-4">{hero.subtitle}</p>
        ) : null}
        {chipEntries.length > 0 ? (
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {chipEntries.map(([k, v]) => (
              <span
                key={k}
                className="text-[10px] px-2 py-0.5 rounded-full bg-dark-bg/60 text-gray-300 border border-dark-border"
              >
                {Array.isArray(v)
                  ? `${schemaLabel(schema, k)} · ${v.length}`
                  : `${schemaLabel(schema, k)}: ${fmtVal(v)}`}
              </span>
            ))}
          </div>
        ) : null}
      </div>

      {sections.length === 0 ? (
        <div className="text-xs text-gray-500">无可展示字段</div>
      ) : (
        sections.map((s, idx) => (
          <Section
            key={s.key}
            title={s.label}
            badge={Array.isArray(s.value) ? String(s.value.length) : undefined}
            tone={
              idx % 5 === 0 ? 'sky' : idx % 5 === 1 ? 'emerald' : idx % 5 === 2 ? 'violet' : idx % 5 === 3 ? 'amber' : 'slate'
            }
            defaultOpen={s.open && idx < 6}
          >
            <GenericValue value={s.value} depth={0} />
          </Section>
        ))
      )}

      <div className="rounded-lg border border-dark-border/60 bg-dark-card/30">
        <button
          type="button"
          className="w-full flex items-center justify-between px-3 py-2 text-[11px] text-gray-500 hover:text-gray-300"
          onClick={() => setShowRaw((v) => !v)}
        >
          <span>原始 JSON</span>
          <span>{showRaw ? '收起' : '展开复制用'}</span>
        </button>
        {showRaw ? (
          <pre className="px-3 pb-3 text-[10px] text-gray-500 overflow-auto max-h-48 whitespace-pre-wrap break-words border-t border-dark-border/50 pt-2">
            {JSON.stringify(root, null, 2)}
          </pre>
        ) : null}
      </div>
    </div>
  );
};

/** Multi-file coding delivery: plan collapsed; each ``## FILE:`` as a tab. */
export const FileDeliveryOverview: React.FC<{
  text: string;
  /** compact = embed in result panel; fill = use parent flex height (fullscreen). */
  layout?: 'compact' | 'fill';
  persistRoot?: string;
}> = ({ text, layout = 'compact', persistRoot }) => {
  const parsed = useMemo(() => parseFileDelivery(text), [text]);
  const [active, setActive] = useState(0);
  const [showPlan, setShowPlan] = useState(false);
  const [copied, setCopied] = useState(false);
  const fill = layout === 'fill';

  if (!parsed || parsed.files.length === 0) return null;

  const idx = Math.min(Math.max(0, active), parsed.files.length - 1);
  const file = parsed.files[idx];
  const lang = langFromPath(file.path);
  const lineCount = file.body ? file.body.split('\n').length : 0;

  const copyCurrent = async () => {
    try {
      await navigator.clipboard.writeText(file.body || '');
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    } catch {
      /* ignore */
    }
  };

  const copyAll = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    } catch {
      /* ignore */
    }
  };

  const fileList = (
    <div className={fill ? 'w-56 shrink-0 overflow-y-auto pr-1 space-y-0.5' : 'flex flex-col gap-0.5 flex-shrink-0'}>
      {parsed.files.map((f, i) => {
        const name = f.path.includes('/') ? f.path.split('/').pop() || f.path : f.path;
        const selected = i === idx;
        const nLines = f.body ? f.body.split('\n').length : 0;
        return (
          <button
            key={`${f.path}-${i}`}
            type="button"
            title={f.path}
            onClick={() => setActive(i)}
            className={
              selected
                ? 'w-full text-left px-2.5 py-1.5 rounded-md bg-dark-card border border-dark-border'
                : 'w-full text-left px-2.5 py-1.5 rounded-md hover:bg-dark-card/60'
            }
          >
            <div className="text-[12px] font-medium text-gray-100 truncate">{name}</div>
            <div className="text-[10px] text-gray-500 font-mono truncate">{f.path}</div>
            <div className="text-[10px] text-gray-600 tabular-nums">{nLines} 行</div>
          </button>
        );
      })}
    </div>
  );

  return (
    <div
      className={
        fill
          ? 'flex flex-col gap-2 h-full min-h-0 overflow-hidden'
          : 'flex flex-col gap-2'
      }
    >
      <div className="flex items-center gap-2 flex-wrap flex-shrink-0">
        <span className="text-[12px] font-semibold text-gray-100">交付文件</span>
        <span className="text-[11px] text-gray-400 tabular-nums">
          {parsed.files.length} 个 · 当前 {lineCount} 行
        </span>
        {persistRoot ? (
          <span className="text-[11px] text-emerald-300/90 font-mono truncate max-w-[min(100%,36rem)]" title={persistRoot}>
            已落盘 {persistRoot}
          </span>
        ) : null}
        <button
          type="button"
          className="text-[11px] text-gray-400 hover:text-gray-200"
          onClick={copyAll}
          title="复制含规划与全部 ## FILE 的完整原文"
        >
          复制全部
        </button>
        {parsed.overview ? (
          <button
            type="button"
            className="ml-auto text-[11px] text-sky-400/90 hover:text-sky-300"
            onClick={() => setShowPlan((v) => !v)}
          >
            {showPlan ? '收起规划' : '展开规划/分析'}
          </button>
        ) : null}
      </div>

      {showPlan && parsed.overview ? (
        <div className="rounded-lg border border-sky-500/25 bg-sky-500/5 p-2.5 max-h-40 overflow-y-auto flex-shrink-0">
          <div className="text-[10px] font-medium text-sky-300/90 mb-1">规划 / 分析（非最终代码）</div>
          <pre className="text-[11px] text-gray-300 whitespace-pre-wrap break-words leading-relaxed">
            {fill ? parsed.overview : parsed.overview.slice(0, 12000)}
          </pre>
        </div>
      ) : null}

      <div className={fill ? 'flex flex-1 min-h-0 gap-3 overflow-hidden' : 'flex flex-col gap-2'}>
        {fileList}
        <div
          className={
            fill
              ? 'flex-1 min-h-0 rounded-lg border border-dark-border bg-dark-card overflow-hidden flex flex-col'
              : 'rounded-lg border border-dark-border bg-dark-card overflow-hidden flex flex-col'
          }
        >
          <div className="px-2.5 py-1.5 border-b border-dark-border/50 flex items-center gap-2 flex-shrink-0">
            <span className="text-[11px] text-gray-300 font-mono truncate" title={file.path}>
              {file.path}
            </span>
            <button
              type="button"
              onClick={copyCurrent}
              className="text-[11px] text-gray-400 hover:text-gray-200 ml-auto shrink-0"
            >
              {copied ? '已复制' : '复制文件'}
            </button>
            <span className="text-[9px] text-gray-600 uppercase shrink-0">{lang}</span>
          </div>
          <pre
            className={
              fill
                ? 'px-3 py-2 text-[12px] text-gray-200 font-mono leading-relaxed overflow-auto flex-1 min-h-0 whitespace-pre'
                : 'px-3 py-2 text-[12px] text-gray-200 font-mono leading-relaxed overflow-auto min-h-[16rem] max-h-[min(60vh,36rem)] whitespace-pre'
            }
          >
            {file.body || '(空文件)'}
          </pre>
        </div>
      </div>
    </div>
  );
};

/** Markdown research-style cards (existing last30days / ## sections path). */
const MarkdownCards: React.FC<{ text: string }> = ({ text: input }) => {
  // Coding multi-file delivery must not collapse into a single 「概览」 card.
  const coding = parseFileDelivery(input);
  if (coding) return <FileDeliveryOverview text={input} />;

  let text = input;
  text = text.replace(/<!--[\s\S]*?-->/g, '');
  text = text.replace(
    /(?:# END OF last30days|Pass through ONLY the PASS-THROUGH|Do not append a trailing|If your response contains)[\s\S]*$/i,
    '',
  );

  const rawSections = text.split(/(^##\s+[^\n]*$)/m);
  const headed: { heading: string; body: string }[] = [];
  let i = 0;
  if (rawSections[0] && !rawSections[0].startsWith('##')) {
    i = 1;
  }
  for (; i < rawSections.length - 1; i += 2) {
    const heading = (rawSections[i] || '').replace(/^##\s+/, '').trim();
    const body = (rawSections[i + 1] || '').trim();
    if (heading) headed.push({ heading, body });
  }

  const classify = (h: string, b: string) => {
    const hl = h.toLowerCase();
    if (!b.trim()) return null;
    if (
      hl.includes('warning') ||
      hl.includes('degraded') ||
      hl.includes('pre-research') ||
      hl.includes('警告')
    )
      return { icon: '⚠️', label: '警告', collapsible: true, color: 'border-amber-500/30 bg-amber-500/5' };
    if (hl.includes('ranked evidence') || hl.includes('cluster'))
      return { icon: '📊', label: '搜索结果', collapsible: true, color: 'border-blue-500/30 bg-blue-500/5' };
    if (hl.includes('stats') || hl.includes('source coverage') || hl.includes('统计'))
      return { icon: '📈', label: '统计', collapsible: true, color: 'border-emerald-500/30 bg-emerald-500/5' };
    return { icon: '📋', label: h, collapsible: true, color: '' };
  };

  const classified = headed
    .map((h) => ({ ...h, ...(classify(h.heading, h.body) || {}) }))
    .filter((h: any) => h.icon);

  const merged: any[] = [];
  for (const c of classified) {
    const prev = merged[merged.length - 1];
    if (prev && prev.icon === c.icon) {
      prev.body += '\n\n## ' + c.heading + '\n' + c.body;
    } else {
      merged.push({ ...c });
    }
  }

  const firstH2Idx = text.search(/\n##\s+/m);
  const overview =
    firstH2Idx > 0 ? text.slice(0, firstH2Idx).trim() : merged.length === 0 ? text.trim() : '';

  const cards: { icon: string; label: string; body: string; collapsible: boolean; color: string }[] =
    [];

  if (overview) {
    const badgeMatch = overview.match(/^(🌐\s*last30days[^\n]*)/m);
    const dateMatch = overview.match(/Date range:\s*([^\n]+)/);
    const sourcesMatch = overview.match(/- Sources:\s*([^\n]+)/);
    const summaryLines = [badgeMatch?.[1], dateMatch?.[0], sourcesMatch?.[0]].filter(Boolean).join('\n');
    const rest = overview
      .replace(badgeMatch?.[0] || '', '')
      .replace(dateMatch?.[0] || '', '')
      .replace(sourcesMatch?.[0] || '', '')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
    // Never dump PRD JSON into a single "概览" card
    const looksJson = rest.trim().startsWith('{') && rest.includes('"');
    if (!looksJson) {
      cards.push({
        icon: '🌐',
        label: '概览',
        body: summaryLines + (rest ? '\n\n' + rest : ''),
        collapsible: false,
        color: 'border-sky-500/30 bg-sky-500/5',
      });
    }
  }

  for (const c of merged) {
    cards.push({
      icon: c.icon,
      label: c.label,
      body: c.body,
      collapsible: c.collapsible,
      color: c.color,
    });
  }

  const footerMatch = text.match(/^(✅\s*All agents[^\n]*\n(?:[├└─│].*\n?)*)/m);
  if (footerMatch) {
    cards.push({
      icon: '✅',
      label: '汇总',
      body: footerMatch[1].trim(),
      collapsible: true,
      color: 'border-gray-500/30 bg-gray-500/5',
    });
  }

  if (cards.length === 0) {
    return (
      <pre className="text-xs text-gray-300 whitespace-pre-wrap break-words max-h-80 overflow-auto">
        {text.slice(0, 8000)}
      </pre>
    );
  }

  const Card: React.FC<{
    icon: string;
    label: string;
    body: string;
    collapsible: boolean;
    color: string;
  }> = ({ icon, label, body, collapsible, color }) => {
    const [expanded, setExpanded] = useState(!collapsible);
    return (
      <div className={`rounded-lg border ${color || 'border-dark-border'} p-3`}>
        <div
          className="flex items-center gap-2 mb-2"
          onClick={collapsible ? () => setExpanded(!expanded) : undefined}
          style={{ cursor: collapsible ? 'pointer' : 'default' }}
        >
          <span className="text-sm">{icon}</span>
          <span className="text-xs font-semibold text-gray-200">{label}</span>
          {collapsible && (
            <span className="text-xs text-gray-500 ml-auto">{expanded ? '▼' : '▶'}</span>
          )}
        </div>
        {(!collapsible || expanded) && (
          <div className="text-xs text-gray-300 leading-relaxed whitespace-pre-wrap max-h-48 overflow-y-auto">
            {body}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="flex flex-col gap-2 max-h-80 overflow-y-auto">
      {cards.map((c, idx) => (
        <Card key={idx} {...c} />
      ))}
    </div>
  );
};

/**
 * Skill / Agent execute result renderer — schema + structure first:
 * 1. Specialty Overview only when Skill declares x-display-profile / document_type
 * 1b. Coding ``## FILE:`` multi-file delivery → FileDeliveryOverview (before JSON dump)
 * 2. Else any JSON → GenericObjectOverview(schema)  ← default extension path
 * 3. ## FILE multi-file coding → FileDeliveryOverview (before architecture/PRD/JSON dump)
 * 4. Markdown ## → MarkdownCards
 * 5. else → plain text
 *
 * Do NOT add per-Agent field whitelists. New Skill → declare output_schema (+ optional profile).
 */
const StructuredSkillOutput: React.FC<Props> = ({ text = '', raw, schema, displayProfile }) => {
  const generic = useMemo(() => unwrapRenderable(raw, text), [raw, text]);
  const textJson = useMemo(() => (text ? tryParseJson(text) : null), [text]);
  const payload = useMemo(() => {
    const p = generic ?? textJson ?? (typeof raw === 'object' ? coerceSkillEnvelope(raw) : null);
    return p && typeof p === 'object' ? p : null;
  }, [generic, textJson, raw]);

  const profile = useMemo(
    () => resolveDisplayProfile(payload, schema, displayProfile),
    [payload, schema, displayProfile],
  );

  const codingDeliveryText = useMemo(
    // Pass raw even when it is a Python-repr string — extractCodingDeliveryText unwraps it.
    () => extractCodingDeliveryText(text, payload ?? raw),
    [text, payload, raw],
  );

  const persistRoot = useMemo(() => persistRootFromPayload(raw), [raw]);

  if (!text && raw == null) {
    return <div className="text-xs text-gray-500">(空)</div>;
  }

  // Multi-file coding FIRST — never bury ## FILE under 「概览」 / architecture / JSON dump
  if (codingDeliveryText && parseFileDelivery(codingDeliveryText)) {
    return <FileDeliveryOverview text={codingDeliveryText} persistRoot={persistRoot} />;
  }
  if (payload && typeof (payload as any).code === 'string') {
    const nested = String((payload as any).code);
    if (parseFileDelivery(nested)) {
      return <FileDeliveryOverview text={nested} persistRoot={persistRoot} />;
    }
  }
  if (payload && typeof (payload as any).text === 'string') {
    const nested = String((payload as any).text);
    if (parseFileDelivery(nested)) {
      return <FileDeliveryOverview text={nested} persistRoot={persistRoot} />;
    }
  }

  // Specialty: only when Skill/schema/document_type opts in — not by sniffing FR/components keys
  if (profile === 'architecture') {
    const arch = extractArchitecture(raw, text) || (looksLikeArchitecture(payload) ? (payload as Record<string, unknown>) : null);
    if (arch) {
      return <ArchitectureOverview data={arch} />;
    }
  }
  if (profile === 'prd') {
    const prd = extractPrd(raw, text) || (looksLikePrd(payload) ? (payload as Record<string, unknown>) : null);
    if (prd) {
      return <PrdOverview data={prd} />;
    }
  }

  if (text && (text.includes('\n## ') || text.startsWith('## ') || /🌐\s*last30days/i.test(text))) {
    // Prefer structured JSON over markdown-card dump when both present
    if (!payload) return <MarkdownCards text={text} />;
  }

  // Never dump language-locked skill envelopes as generic key/value 「概览」
  if (payload && typeof (payload as { code?: unknown }).code === 'string') {
    const codeBody = String((payload as { code: string }).code);
    if (codeBody.trim()) {
      if (codingDeliveryText && parseFileDelivery(codingDeliveryText)) {
        return <FileDeliveryOverview text={codingDeliveryText} />;
      }
      if (parseFileDelivery(codeBody)) {
        return <FileDeliveryOverview text={codeBody} />;
      }
      return (
        <pre className="text-xs text-gray-300 overflow-auto max-h-[min(70vh,40rem)] bg-dark-card border border-dark-border rounded-lg p-3 whitespace-pre-wrap break-words">
          {codeBody}
        </pre>
      );
    }
  }

  if (payload) {
    return <GenericObjectOverview data={payload} schema={schema} />;
  }

  if (text && (text.includes('\n## ') || text.startsWith('## ') || /🌐\s*last30days/i.test(text))) {
    return <MarkdownCards text={text} />;
  }

  return (
    <pre className="text-xs text-gray-300 overflow-auto max-h-[min(70vh,40rem)] bg-dark-card border border-dark-border rounded-lg p-3 whitespace-pre-wrap break-words">
      {text || String(raw ?? '')}
    </pre>
  );
};

export default StructuredSkillOutput;
