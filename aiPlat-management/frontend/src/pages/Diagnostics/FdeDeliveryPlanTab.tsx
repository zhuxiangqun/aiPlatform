/**
 * FDE 交付计划 Tab — 粘贴需求生成实施计划，并与 pipeline 联动检查进度。
 * 完成度仅反映本计划 checklist，≠ ⑦签收 / ≠ 顶部八步全部完成。
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Button, toast } from '../../components/ui';
import { ChevronDown, ChevronRight, ClipboardList, ExternalLink, RefreshCw } from 'lucide-react';

const API = (path: string) => `/api/platform/apps/fde${path}`;

export type DeliveryPlanTabKey =
  | 'customers'
  | 'capability'
  | 'assess'
  | 'poc'
  | 'deploy'
  | 'canary'
  | 'accept'
  | 'evolution'
  | string;

export type PipelineSnapshot = {
  customer: boolean;
  domain: boolean;
  diagnosis: boolean;
  pocProfile: boolean;
  deployVersion: boolean;
  canaryResult: boolean;
  adopted: boolean;
};

type PlanStep = {
  id: string;
  title: string;
  ops?: string[];
  auto_check?: string | null;
  manual_done?: boolean;
  status?: string;
};

type PlanPhase = {
  id: string;
  title: string;
  fde_tab?: string;
  steps?: PlanStep[];
};

type DeliveryPlan = {
  plan_id?: string;
  customer_namespace?: string;
  source?: { title?: string; text_sha256?: string; created_at?: string };
  summary?: {
    delivery_type?: string;
    phase0_days?: number;
    honesty_locks?: string[];
    summary_note?: string;
  };
  phases?: PlanPhase[];
  progress?: { done?: number; total?: number; pct?: number; updated_at?: string };
  llm_ok?: boolean;
  llm_error?: string;
  plan?: null;
};

function unwrapPlan(payload: any): DeliveryPlan | null {
  const d = payload?.data ?? payload;
  if (!d || d.plan === null) return null;
  if (d.phases || d.plan_id) return d as DeliveryPlan;
  if (d.plan && (d.plan.phases || d.plan.plan_id)) return d.plan as DeliveryPlan;
  return null;
}

type Props = {
  customerNamespace: string | null;
  customerName?: string;
  pipeline: PipelineSnapshot;
  onGotoTab: (tab: DeliveryPlanTabKey) => void;
};

const FdeDeliveryPlanTab: React.FC<Props> = ({
  customerNamespace,
  customerName,
  pipeline,
  onGotoTab,
}) => {
  const [title, setTitle] = useState('');
  const [requirementText, setRequirementText] = useState('');
  const [plan, setPlan] = useState<DeliveryPlan | null>(null);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const ns = (customerNamespace || '').trim();

  const loadPlan = useCallback(async () => {
    if (!ns) {
      setPlan(null);
      return;
    }
    setLoading(true);
    try {
      const r = await fetch(API(`/delivery-plan?customer_namespace=${encodeURIComponent(ns)}`));
      const j = await r.json();
      setPlan(unwrapPlan(j));
    } catch (e: any) {
      toast?.error?.(`加载计划失败: ${(e?.message || String(e)).slice(0, 80)}`);
    } finally {
      setLoading(false);
    }
  }, [ns]);

  useEffect(() => {
    void loadPlan();
  }, [loadPlan]);

  useEffect(() => {
    if (!title && customerName) setTitle(`${customerName} 交付计划`);
  }, [customerName, title]);

  const pct = plan?.progress?.pct ?? 0;
  const progressLabel = useMemo(() => {
    const d = plan?.progress?.done ?? 0;
    const t = plan?.progress?.total ?? 0;
    return `实施计划完成度 ${pct}%（${d}/${t}）— ≠ ⑦签收 / ≠ 顶部八步全部完成`;
  }, [plan, pct]);

  const onPickFile = (file: File | null) => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const text = String(reader.result || '');
      setRequirementText(text);
      if (!title) setTitle(file.name.replace(/\.md$/i, ''));
    };
    reader.readAsText(file);
  };

  const generate = async () => {
    if (!ns) return;
    if (requirementText.trim().length < 20) {
      toast?.error?.('需求文本至少 20 字');
      return;
    }
    setGenerating(true);
    try {
      const r = await fetch(API('/delivery-plan/generate'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          customer_namespace: ns,
          title: title.trim() || '未命名交付计划',
          requirement_text: requirementText,
          pipeline_snapshot: pipeline,
        }),
      });
      const j = await r.json();
      if (!r.ok) {
        toast?.error?.(j?.detail || `生成失败 HTTP ${r.status}`);
        return;
      }
      const p = unwrapPlan(j);
      setPlan(p);
      if (p?.llm_ok === false) {
        toast?.error?.(p.llm_error ? `已返回骨架（LLM 未填空）: ${p.llm_error}` : '已返回骨架（LLM 未填空）');
      } else {
        toast?.success?.('交付计划已生成');
      }
      const open: Record<string, boolean> = {};
      (p?.phases || []).forEach((ph, i) => {
        open[ph.id] = i < 2;
      });
      setExpanded(open);
    } catch (e: any) {
      toast?.error?.(`生成失败: ${(e?.message || String(e)).slice(0, 100)}`);
    } finally {
      setGenerating(false);
    }
  };

  const refresh = async () => {
    if (!ns) return;
    setLoading(true);
    try {
      const r = await fetch(API('/delivery-plan/refresh'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ customer_namespace: ns, pipeline_snapshot: pipeline }),
      });
      const j = await r.json();
      if (!r.ok) {
        toast?.error?.(j?.detail || `刷新失败 HTTP ${r.status}`);
        return;
      }
      setPlan(unwrapPlan(j));
    } catch (e: any) {
      toast?.error?.(`刷新失败: ${(e?.message || String(e)).slice(0, 80)}`);
    } finally {
      setLoading(false);
    }
  };

  const toggleManual = async (step: PlanStep, done: boolean) => {
    if (!ns || step.auto_check) return;
    try {
      const r = await fetch(API(`/delivery-plan/steps/${encodeURIComponent(step.id)}`), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          customer_namespace: ns,
          manual_done: done,
          pipeline_snapshot: pipeline,
        }),
      });
      const j = await r.json();
      if (!r.ok) {
        toast?.error?.(j?.detail || `勾选失败 HTTP ${r.status}`);
        return;
      }
      setPlan(unwrapPlan(j));
    } catch (e: any) {
      toast?.error?.(`勾选失败: ${(e?.message || String(e)).slice(0, 80)}`);
    }
  };

  if (!ns) {
    return (
      <div className="rounded-lg border border-gray-700/60 bg-gray-900/40 p-6 text-sm text-gray-400">
        请先在①业务认知中选择或创建客户，再生成交付计划。
        <div className="mt-3">
          <Button size="sm" variant="default" onClick={() => onGotoTab('customers')}>
            前往①业务认知
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-gray-700/60 bg-gray-900/40 p-4 space-y-3">
        <div className="flex items-center gap-2 text-sm text-gray-200 font-medium">
          <ClipboardList className="w-4 h-4 text-blue-400" />
          交付计划 — 需求 → 实施步骤与进度
        </div>
        <p className="text-xs text-gray-500">
          客户：{customerName || ns}（{ns}）。骨架固定为 FDE 八步+新建域插段；LLM 仅填空。不落盘需求原文。
        </p>
        <div className="grid gap-2 md:grid-cols-[1fr_auto] items-end">
          <label className="text-xs text-gray-400 block">
            计划标题
            <input
              className="mt-1 w-full rounded border border-gray-700 bg-gray-800 px-2 py-1.5 text-sm text-gray-100"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="例如：AI面试官 PoC"
            />
          </label>
          <label className="text-xs text-gray-400">
            本地 .md
            <input
              type="file"
              accept=".md,.txt,text/markdown,text/plain"
              className="mt-1 block w-full text-xs text-gray-400"
              onChange={(e) => onPickFile(e.target.files?.[0] || null)}
            />
          </label>
        </div>
        <label className="text-xs text-gray-400 block">
          客户需求（粘贴 SRS / 访谈纪要）
          <textarea
            className="mt-1 w-full h-36 rounded border border-gray-700 bg-gray-800 p-2 text-xs text-gray-200 font-mono resize-y"
            value={requirementText}
            onChange={(e) => setRequirementText(e.target.value)}
            placeholder="粘贴客户需求规格或关键摘要（至少 20 字）…"
          />
        </label>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="default" disabled={generating} onClick={() => void generate()}>
            {generating ? '生成中…' : '生成计划'}
          </Button>
          <Button size="sm" variant="outline" disabled={loading || !plan} onClick={() => void refresh()}>
            <RefreshCw className={`w-3.5 h-3.5 mr-1 ${loading ? 'animate-spin' : ''}`} />
            刷新进度
          </Button>
        </div>
      </div>

      {plan && (
        <div className="rounded-lg border border-gray-700/60 bg-gray-900/40 p-4 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-sm text-gray-200">
              {plan.source?.title || '交付计划'}
              <span className="ml-2 text-xs text-gray-500">
                {plan.summary?.delivery_type === 'new_domain' ? '新建域交付' : '标准交付'}
                {typeof plan.summary?.phase0_days === 'number' ? ` · 建议 ${plan.summary.phase0_days} 人日` : ''}
                {plan.llm_ok === false ? ' · 骨架模式' : plan.llm_ok ? ' · LLM 已填空' : ''}
              </span>
            </div>
            <div className="text-xs text-amber-300/90">{progressLabel}</div>
          </div>
          <div className="h-2 rounded bg-gray-800 overflow-hidden">
            <div className="h-full bg-blue-500 transition-all" style={{ width: `${Math.min(100, Math.max(0, pct))}%` }} />
          </div>
          {plan.summary?.summary_note && (
            <p className="text-xs text-gray-400">{plan.summary.summary_note}</p>
          )}
          {(plan.summary?.honesty_locks || []).length > 0 && (
            <ul className="text-xs text-amber-200/80 list-disc pl-5 space-y-0.5">
              {plan.summary!.honesty_locks!.map((x, i) => (
                <li key={i}>{x}</li>
              ))}
            </ul>
          )}

          <div className="space-y-2">
            {(plan.phases || []).map((ph) => {
              const open = expanded[ph.id] ?? false;
              const steps = ph.steps || [];
              const doneCount = steps.filter((s) => s.status === 'done').length;
              const skipped = steps.every((s) => s.status === 'skipped');
              return (
                <div key={ph.id} className={`rounded border border-gray-700/50 ${skipped ? 'opacity-50' : ''}`}>
                  <button
                    type="button"
                    className="w-full flex items-center gap-2 px-3 py-2 text-left text-sm text-gray-200 hover:bg-gray-800/50"
                    onClick={() => setExpanded((m) => ({ ...m, [ph.id]: !open }))}
                  >
                    {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                    <span className="flex-1">{ph.title}</span>
                    <span className="text-xs text-gray-500">
                      {skipped ? 'skipped' : `${doneCount}/${steps.length}`}
                    </span>
                    {ph.fde_tab && (
                      <span
                        className="text-xs text-blue-400 hover:underline"
                        onClick={(e) => {
                          e.stopPropagation();
                          if (ph.id === 'factory') {
                            window.open('/app/factory', '_blank');
                            return;
                          }
                          onGotoTab(ph.fde_tab as DeliveryPlanTabKey);
                        }}
                      >
                        前往
                      </span>
                    )}
                  </button>
                  {open && (
                    <div className="border-t border-gray-700/40 px-3 py-2 space-y-2">
                      {steps.map((st) => {
                        const isAuto = !!st.auto_check;
                        const isDone = st.status === 'done';
                        const isSkipped = st.status === 'skipped';
                        return (
                          <div key={st.id} className="rounded bg-gray-800/40 px-2 py-1.5">
                            <div className="flex items-start gap-2 text-xs">
                              {isAuto || isSkipped ? (
                                <span className={`mt-0.5 ${isDone ? 'text-green-400' : 'text-gray-500'}`}>
                                  {isSkipped ? '—' : isDone ? '✓' : '○'}
                                </span>
                              ) : (
                                <input
                                  type="checkbox"
                                  className="mt-0.5"
                                  checked={!!st.manual_done || isDone}
                                  onChange={(e) => void toggleManual(st, e.target.checked)}
                                />
                              )}
                              <div className="flex-1">
                                <div className="text-gray-200">
                                  {st.title}
                                  {isAuto && (
                                    <span className="ml-1 text-gray-500">auto:{st.auto_check}</span>
                                  )}
                                </div>
                                {(st.ops || []).length > 0 && (
                                  <ul className="mt-1 text-gray-500 list-disc pl-4 space-y-0.5">
                                    {st.ops!.map((op, i) => (
                                      <li key={i}>{op}</li>
                                    ))}
                                  </ul>
                                )}
                                {ph.id === 'factory' && (
                                  <a
                                    href="/app/factory"
                                    target="_blank"
                                    rel="noreferrer"
                                    className="inline-flex items-center gap-1 mt-1 text-blue-400 hover:underline"
                                  >
                                    打开应用工厂 <ExternalLink className="w-3 h-3" />
                                  </a>
                                )}
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {!plan && !loading && (
        <div className="text-xs text-gray-500 px-1">尚未生成计划。粘贴需求后点击「生成计划」。</div>
      )}
    </div>
  );
};

export default FdeDeliveryPlanTab;
