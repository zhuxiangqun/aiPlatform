/**
 * DIAGNOSIS_V1 /diagnosis — C1 D1c MVP list/detail/report.
 * Honesty: engineering diagnosis only; never accuracy / auto-repair / authorize.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { AlertTriangle, RefreshCw, ShieldAlert } from 'lucide-react';
import { apiClient } from '../../services';

type Envelope<T> = { data?: T } & T;

function unwrap<T>(res: Envelope<T>): T {
  return (res?.data ?? res) as T;
}

type DxCase = {
  id: string;
  scenario: string;
  status: string;
  subject_ref: string;
  baseline_ref?: string | null;
  created_at?: string;
};

type ReportBundle = {
  status?: string;
  report?: {
    summary?: string;
    uncertainty?: { unknown?: string[]; stale?: string[]; notes?: string };
    accuracy_claim?: boolean;
  };
  findings?: Array<{ id: string; summary: string; severity: string; confidence: number }>;
  hypotheses?: Array<{ id: string; root_cause: string; confidence: number; rationale?: string }>;
  recommendations?: Array<{ id: string; action: string; auto_execute?: boolean; target_api?: string }>;
};

const HonestyBanner = () => (
  <div
    className="rounded-lg border border-amber-700/50 bg-amber-950/30 px-4 py-3 flex gap-3 items-start"
    role="status"
  >
    <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
    <div className="text-sm space-y-1">
      <div className="font-medium text-amber-200">诚实约束（强制）</div>
      <ul className="list-disc pl-5 text-amber-100/90 space-y-0.5">
        <li>
          <code>accuracy_claim=false</code> — 工程诊断 ≠ 准确率认证
        </li>
        <li>无自动修复 / 无 <code>remediate</code>；建议仅可复制</li>
        <li>证据不足 → unknown；证据过期 → stale；≠ staging / authorize</li>
      </ul>
    </div>
  </div>
);

const DiagnosisList: React.FC = () => {
  const nav = useNavigate();
  const [items, setItems] = useState<DxCase[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [subject, setSubject] = useState('fixture:dx.s1.tool_timeout');
  const [scenario, setScenario] = useState<'run_failure' | 'version_regression'>('run_failure');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await apiClient.get<{ items?: DxCase[]; total?: number; data?: { items?: DxCase[] } }>(
        '/platform/apps/diagnosis/cases?tenant_id=diagnosis-v1',
      );
      const list = (res as any)?.items ?? (res as any)?.data?.items ?? [];
      setItems(Array.isArray(list) ? list : []);
    } catch (e: any) {
      setError(String(e?.message || e));
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const create = async () => {
    setCreating(true);
    setError('');
    try {
      const res = await apiClient.post<Envelope<DxCase>>('/platform/apps/diagnosis/cases', {
        scenario,
        subject_ref: subject,
        tenant_id: 'diagnosis-v1',
        accuracy_claim: false,
      });
      const row = unwrap(res);
      if (row?.id) nav(`/diagnosis/${row.id}`);
      else await load();
    } catch (e: any) {
      setError(String(e?.message || e));
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6 text-gray-200">
      <header className="space-y-2">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <h1 className="text-2xl font-semibold tracking-tight">诊断产品 · C1</h1>
          <button
            type="button"
            onClick={() => void load()}
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded border border-gray-600 text-sm hover:bg-gray-800"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </button>
        </div>
        <p className="text-sm text-gray-400">
          canonical API <code className="text-blue-300">/api/platform/apps/diagnosis</code> · 两场景 · 不自动修复
        </p>
      </header>

      <HonestyBanner />

      <section className="space-y-3 rounded border border-gray-700 p-4">
        <div className="text-sm font-medium">新建 Case</div>
        <div className="flex flex-wrap gap-2 items-center">
          <select
            className="bg-gray-900 border border-gray-600 rounded px-2 py-1.5 text-sm"
            value={scenario}
            onChange={(e) => setScenario(e.target.value as any)}
          >
            <option value="run_failure">run_failure (S1)</option>
            <option value="version_regression">version_regression (S2)</option>
          </select>
          <input
            className="flex-1 min-w-[240px] bg-gray-900 border border-gray-600 rounded px-2 py-1.5 text-sm"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder="subject_ref e.g. fixture:dx.s1.tool_timeout"
          />
          <button
            type="button"
            disabled={creating}
            onClick={() => void create()}
            className="px-3 py-1.5 rounded bg-blue-700 hover:bg-blue-600 text-sm disabled:opacity-50"
          >
            {creating ? '创建中…' : '创建'}
          </button>
        </div>
      </section>

      {error ? (
        <div className="rounded border border-red-800 bg-red-950/40 px-4 py-3 text-sm text-red-200">{error}</div>
      ) : null}

      <div className="overflow-x-auto rounded border border-gray-700">
        <table className="w-full text-sm">
          <thead className="bg-gray-900/80 text-gray-400 text-left">
            <tr>
              <th className="px-3 py-2">Case</th>
              <th className="px-3 py-2">Scenario</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Subject</th>
            </tr>
          </thead>
          <tbody>
            {items.map((c) => (
              <tr key={c.id} className="border-t border-gray-800 hover:bg-gray-900/50">
                <td className="px-3 py-2">
                  <Link className="text-blue-300 hover:underline" to={`/diagnosis/${c.id}`}>
                    {c.id}
                  </Link>
                </td>
                <td className="px-3 py-2">{c.scenario}</td>
                <td className="px-3 py-2">
                  <StatusPill status={c.status} />
                </td>
                <td className="px-3 py-2 font-mono text-xs text-gray-400">{c.subject_ref}</td>
              </tr>
            ))}
            {!loading && items.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-3 py-6 text-center text-gray-500">
                  暂无 case — 可用 fixture:dx.s1.* / dx.s2.* 创建
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
};

function StatusPill({ status }: { status: string }) {
  const tone =
    status === 'blocked_unknown'
      ? 'border-amber-600 text-amber-300'
      : status === 'blocked_stale'
        ? 'border-orange-700 text-orange-300'
        : status === 'reported'
          ? 'border-emerald-700 text-emerald-300'
          : 'border-gray-600 text-gray-300';
  return <span className={`inline-block px-2 py-0.5 rounded border text-xs ${tone}`}>{status}</span>;
}

const DiagnosisDetail: React.FC = () => {
  const { caseId = '' } = useParams();
  const [dxCase, setDxCase] = useState<DxCase | null>(null);
  const [evidence, setEvidence] = useState<any[]>([]);
  const [report, setReport] = useState<ReportBundle | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');

  const load = useCallback(async () => {
    if (!caseId) return;
    setError('');
    try {
      const c = unwrap(
        await apiClient.get<Envelope<DxCase>>(
          `/platform/apps/diagnosis/cases/${caseId}?tenant_id=diagnosis-v1`,
        ),
      );
      setDxCase(c);
      try {
        const ev = unwrap(
          await apiClient.get<Envelope<{ items?: any[] }>>(
            `/platform/apps/diagnosis/cases/${caseId}/evidence?tenant_id=diagnosis-v1`,
          ),
        );
        setEvidence(Array.isArray(ev?.items) ? ev.items : []);
      } catch {
        setEvidence([]);
      }
      try {
        const rp = unwrap(
          await apiClient.get<Envelope<ReportBundle>>(
            `/platform/apps/diagnosis/cases/${caseId}/report?tenant_id=diagnosis-v1`,
          ),
        );
        setReport(rp);
      } catch {
        setReport(null);
      }
    } catch (e: any) {
      setError(String(e?.message || e));
    }
  }, [caseId]);

  useEffect(() => {
    void load();
  }, [load]);

  const collect = async () => {
    setBusy('collect');
    setError('');
    try {
      await apiClient.post(`/platform/apps/diagnosis/cases/${caseId}/collect`, {
        tenant_id: 'diagnosis-v1',
      });
      await load();
    } catch (e: any) {
      setError(String(e?.message || e));
    } finally {
      setBusy('');
    }
  };

  const buildReport = async () => {
    setBusy('report');
    setError('');
    try {
      const rp = unwrap(
        await apiClient.get<Envelope<ReportBundle>>(
          `/platform/apps/diagnosis/cases/${caseId}/report?tenant_id=diagnosis-v1&rebuild=true`,
        ),
      );
      setReport(rp);
      await load();
    } catch (e: any) {
      setError(String(e?.message || e));
    } finally {
      setBusy('');
    }
  };

  const uncertainty = report?.report?.uncertainty || {};
  const unknown = uncertainty.unknown || [];
  const stale = uncertainty.stale || [];
  const top = report?.hypotheses?.[0];

  const banner = useMemo(() => {
    if (unknown.length || report?.status === 'blocked_unknown') {
      return (
        <div className="rounded border border-amber-700 bg-amber-950/40 px-4 py-3 text-sm text-amber-100 flex gap-2">
          <ShieldAlert className="w-4 h-4 mt-0.5" />
          证据不足，结论 unknown — 不展示「根因已确认」
        </div>
      );
    }
    if (stale.length || report?.status === 'blocked_stale') {
      return (
        <div className="rounded border border-orange-700 bg-orange-950/40 px-4 py-3 text-sm text-orange-100 flex gap-2">
          <ShieldAlert className="w-4 h-4 mt-0.5" />
          证据过期 (stale) — 假设可展示但低置信
        </div>
      );
    }
    return null;
  }, [unknown, stale, report?.status]);

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6 text-gray-200">
      <header className="space-y-2">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <Link to="/diagnosis" className="text-sm text-blue-300 hover:underline">
              ← 列表
            </Link>
            <h1 className="text-2xl font-semibold tracking-tight mt-1">{caseId}</h1>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={!!busy}
              onClick={() => void collect()}
              className="px-3 py-1.5 rounded border border-gray-600 text-sm hover:bg-gray-800 disabled:opacity-50"
            >
              {busy === 'collect' ? '采集中…' : 'Collect 证据'}
            </button>
            <button
              type="button"
              disabled={!!busy}
              onClick={() => void buildReport()}
              className="px-3 py-1.5 rounded bg-blue-700 hover:bg-blue-600 text-sm disabled:opacity-50"
            >
              {busy === 'report' ? '生成中…' : '生成报告'}
            </button>
          </div>
        </div>
        {dxCase ? (
          <p className="text-sm text-gray-400">
            {dxCase.scenario} · <StatusPill status={dxCase.status} /> ·{' '}
            <span className="font-mono text-xs">{dxCase.subject_ref}</span>
          </p>
        ) : null}
      </header>

      <HonestyBanner />
      {banner}

      {error ? (
        <div className="rounded border border-red-800 bg-red-950/40 px-4 py-3 text-sm text-red-200">{error}</div>
      ) : null}

      <section className="space-y-2">
        <h2 className="text-lg font-medium">Evidence refs</h2>
        <ul className="text-sm space-y-1 font-mono text-gray-400">
          {evidence.map((e) => (
            <li key={e.id}>
              [{e.source}/{e.kind}] {e.id} · {e.freshness || '—'} · {e.ref}
            </li>
          ))}
          {evidence.length === 0 ? <li className="text-gray-500">尚未 collect</li> : null}
        </ul>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium">Hypotheses (Top-K)</h2>
        {top && !unknown.length && report?.status !== 'blocked_unknown' ? (
          <div className="text-sm text-gray-300">
            Top-1 候选：<code>{top.root_cause}</code>（置信 {top.confidence}）— 非「已确认」徽章
          </div>
        ) : null}
        <ul className="space-y-2">
          {(report?.hypotheses || []).map((h, i) => (
            <li key={h.id} className="rounded border border-gray-700 px-3 py-2 text-sm">
              #{i + 1} <code>{h.root_cause}</code> · {h.confidence}
              {h.rationale ? <div className="text-gray-400 mt-1">{h.rationale}</div> : null}
            </li>
          ))}
          {!report?.hypotheses?.length ? <li className="text-gray-500 text-sm">无假设</li> : null}
        </ul>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium">Findings</h2>
        <ul className="space-y-2">
          {(report?.findings || []).map((f) => (
            <li key={f.id} className="rounded border border-gray-700 px-3 py-2 text-sm">
              [{f.severity}] {f.summary}
            </li>
          ))}
        </ul>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-medium">Recommendations</h2>
        <ul className="space-y-2">
          {(report?.recommendations || []).map((r) => (
            <li key={r.id} className="rounded border border-gray-700 px-3 py-2 text-sm flex justify-between gap-3">
              <span>{r.action}</span>
              <button
                type="button"
                className="shrink-0 text-xs px-2 py-1 border border-gray-600 rounded hover:bg-gray-800"
                onClick={() => void navigator.clipboard.writeText(r.action)}
              >
                复制建议
              </button>
            </li>
          ))}
        </ul>
        <p className="text-xs text-gray-500">无「一键修复」按钮 · auto_execute=false</p>
      </section>

      <footer className="text-xs text-gray-500 border-t border-gray-800 pt-3">
        accuracy_claim={String(report?.report?.accuracy_claim ?? false)} · 工程诊断 ≠ authorize
      </footer>
    </div>
  );
};

const DiagnosisApp: React.FC = () => {
  const { caseId } = useParams();
  return caseId ? <DiagnosisDetail /> : <DiagnosisList />;
};

export default DiagnosisApp;
