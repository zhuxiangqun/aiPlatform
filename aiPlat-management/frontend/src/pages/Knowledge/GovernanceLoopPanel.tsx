/**
 * GovernanceLoopPanel — Xingye-shaped 8-step data-governance map (honest status).
 * Steps ⑥ OCS/actions + ⑦ GraphIndex locate are interactive vertical slices.
 */
import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Card, CardContent, CardHeader, Button } from '../../components/ui';
import { RefreshCw, Search } from 'lucide-react';

const API = (path: string) => `/api/platform/apps/fde${path}`;

type Step = {
  step: number;
  title: string;
  material?: string;
  aiplat?: string;
  status: string;
  status_label: string;
  href: string;
  href_label: string;
  api?: string;
};

type QualitySnap = {
  ocs?: number;
  ocs_level?: string;
  actions?: { action_id: string; label: string }[];
  links?: { label: string; href: string }[];
  authority_note?: string;
};

type LocateHit = {
  entity_id: string;
  entity_name: string;
  class_name: string;
  state?: string;
  score: number;
};

type FetchSnap = {
  status?: string;
  mode?: string;
  sandbox?: Record<string, unknown>;
  graph?: { entity_name?: string; class_name?: string; state?: string };
  authority_note?: string;
};

const statusTone = (s: string) => {
  if (s === 'vertical' || s === 'entry') return 'text-emerald-400 bg-emerald-500/10 border-emerald-700/40';
  if (s === 'suggestion') return 'text-amber-300 bg-amber-500/10 border-amber-700/40';
  return 'text-sky-300 bg-sky-500/10 border-sky-700/40';
};

export const GovernanceLoopPanel: React.FC<{ compact?: boolean }> = ({ compact }) => {
  const [steps, setSteps] = useState<Step[]>([]);
  const [note, setNote] = useState('');
  const [loading, setLoading] = useState(false);
  const [quality, setQuality] = useState<QualitySnap | null>(null);
  const [locateQ, setLocateQ] = useState('积分流水');
  const [locateHits, setLocateHits] = useState<LocateHit[]>([]);
  const [locateNote, setLocateNote] = useState('');
  const [locateBusy, setLocateBusy] = useState(false);
  const [fetchSnap, setFetchSnap] = useState<FetchSnap | null>(null);
  const [fetchBusy, setFetchBusy] = useState(false);
  const [fetchDomain, setFetchDomain] = useState('data-gov');

  const load = async () => {
    setLoading(true);
    try {
      const [loopR, qR] = await Promise.all([
        fetch(API('/ontology/governance-loop')),
        fetch(API('/ontology/governance/quality?domain_id=data-gov')),
      ]);
      const loopD = await loopR.json();
      if (loopR.ok) {
        setSteps(loopD.steps || []);
        setNote(loopD.authority_note || '');
      }
      if (qR.ok) {
        setQuality(await qR.json());
      }
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  };

  const runLocate = async () => {
    setLocateBusy(true);
    setFetchSnap(null);
    try {
      const r = await fetch(API('/ontology/governance/locate'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ domain_id: fetchDomain, query: locateQ, top_k: 8 }),
      });
      const d = await r.json();
      if (r.ok) {
        setLocateHits(d.hits || []);
        setLocateNote(d.authority_note || d.status || '');
      } else {
        setLocateHits([]);
        setLocateNote(d.detail || '定位失败');
      }
    } catch {
      setLocateHits([]);
      setLocateNote('网络错误');
    } finally {
      setLocateBusy(false);
    }
  };

  const runFetch = async (entityId: string) => {
    setFetchBusy(true);
    try {
      const r = await fetch('/api/platform/apps/org/connectors/fetch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          domain_id: fetchDomain,
          entity_id: entityId,
          purpose: 'org_pilot',
        }),
      });
      const d = await r.json();
      setFetchSnap(d);
    } catch {
      setFetchSnap({ status: 'error', authority_note: '网络错误' });
    } finally {
      setFetchBusy(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <Card className="border-violet-500/20" id="governance-loop-8">
      <CardHeader>
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div>
            <span className="text-sm font-medium text-gray-100">对照材料：数据治理 8 步（演示用）</span>
            <p className="text-[11px] text-gray-500 mt-1 font-normal">
              说明「和对外方案怎么对齐」。日常建说明书请用下方①→③，不必先做完这 8 步。
            </p>
          </div>
          <Button variant="ghost" size="sm" loading={loading} onClick={load}>
            <RefreshCw className="w-3 h-3" />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className={`grid gap-2 ${compact ? 'grid-cols-2 md:grid-cols-4' : 'grid-cols-1 md:grid-cols-2'}`}>
          {steps.map((s) => (
            <div
              key={s.step}
              className={`rounded border p-2 text-[11px] ${statusTone(s.status)}`}
            >
              <div className="flex items-center justify-between gap-1 mb-1">
                <span className="font-medium text-gray-100">
                  {s.step}. {s.title}
                </span>
                <span className="text-[10px] opacity-90">{s.status_label}</span>
              </div>
              {!compact && (
                <div className="text-gray-400 mb-1 line-clamp-2">{s.aiplat || s.material}</div>
              )}
              <Link to={s.href} className="text-sky-400 hover:underline">
                {s.href_label} →
              </Link>
            </div>
          ))}
        </div>

        {/* ⑥ deepen */}
        <div className="rounded border border-emerald-800/40 bg-emerald-950/20 p-3 space-y-2">
          <div className="text-xs font-medium text-emerald-300">⑥ 质量竖切 · OCS + 闸2</div>
          {quality ? (
            <>
              <div className="text-[11px] text-gray-300">
                OCS{' '}
                <span className="text-emerald-400 font-mono">
                  {typeof quality.ocs === 'number' ? quality.ocs.toFixed(1) : '—'}
                </span>
                {quality.ocs_level ? (
                  <span className="ml-2 text-gray-500">({quality.ocs_level})</span>
                ) : null}
              </div>
              {(quality.actions || []).length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {quality.actions!.map((a) => (
                    <span
                      key={a.action_id}
                      className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700"
                      title={a.action_id}
                    >
                      {a.label}
                    </span>
                  ))}
                </div>
              )}
              <div className="flex flex-wrap gap-3 text-[11px]">
                {(quality.links || []).map((l) => (
                  <Link key={l.href + l.label} to={l.href} className="text-sky-400 hover:underline">
                    {l.label} →
                  </Link>
                ))}
              </div>
              {quality.authority_note && (
                <div className="text-[10px] text-amber-500/70">{quality.authority_note}</div>
              )}
            </>
          ) : (
            <div className="text-[11px] text-gray-500">加载 OCS…</div>
          )}
        </div>

        {/* ⑦ deepen */}
        <div className="rounded border border-sky-800/40 bg-sky-950/20 p-3 space-y-2">
          <div className="text-xs font-medium text-sky-300">
            ⑦ 定位 + 沙箱取数 · Org L5 Phase 1（非 live）
          </div>
          <div className="flex gap-2 items-center flex-wrap">
            <select
              className="text-[11px] bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-gray-200"
              value={fetchDomain}
              onChange={(e) => setFetchDomain(e.target.value)}
            >
              <option value="data-gov">data-gov</option>
              <option value="it-ops">it-ops</option>
            </select>
            <input
              className="flex-1 min-w-[8rem] text-[11px] bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-gray-200"
              value={locateQ}
              onChange={(e) => setLocateQ(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && runLocate()}
              placeholder="业务关键词，如：积分流水 / 告警"
            />
            <Button size="sm" loading={locateBusy} onClick={runLocate}>
              <Search className="w-3 h-3 mr-1" />
              定位
            </Button>
          </div>
          {locateHits.length > 0 ? (
            <ul className="space-y-1 max-h-36 overflow-auto">
              {locateHits.map((h) => (
                <li
                  key={h.entity_id}
                  className="text-[11px] text-gray-300 flex justify-between gap-2 border-b border-slate-800/60 pb-0.5 items-center"
                >
                  <button
                    type="button"
                    className="text-left hover:text-sky-300"
                    disabled={fetchBusy}
                    onClick={() => runFetch(h.entity_id)}
                    title="沙箱 fetch"
                  >
                    <span className="text-sky-300">{h.entity_name || h.entity_id}</span>
                    <span className="text-gray-500 ml-1">{h.class_name}</span>
                    {h.state ? <span className="text-gray-600 ml-1">·{h.state}</span> : null}
                  </button>
                  <span className="font-mono text-gray-500">{h.score.toFixed(2)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <div className="text-[10px] text-gray-500">
              {locateNote || '先 FDE⑦ 种图，再定位；点击命中项做沙箱 fetch'}
            </div>
          )}
          {fetchSnap && (
            <div className="text-[10px] rounded bg-slate-900/80 border border-slate-700 p-2 text-gray-300 space-y-1">
              <div>
                fetch <span className="text-emerald-400">{fetchSnap.status}</span>
                {fetchSnap.mode ? (
                  <span className="text-gray-500 ml-2">mode={fetchSnap.mode}</span>
                ) : null}
              </div>
              {fetchSnap.sandbox && (
                <pre className="overflow-auto max-h-24 text-[10px] text-slate-400">
                  {JSON.stringify(fetchSnap.sandbox, null, 0)}
                </pre>
              )}
              {fetchSnap.authority_note && (
                <div className="text-amber-500/70">{fetchSnap.authority_note}</div>
              )}
            </div>
          )}
          {locateHits.length > 0 && locateNote && (
            <div className="text-[10px] text-amber-500/70">{locateNote}</div>
          )}
        </div>

        {note && <div className="text-[10px] text-amber-500/80">{note}</div>}
      </CardContent>
    </Card>
  );
};

export default GovernanceLoopPanel;
