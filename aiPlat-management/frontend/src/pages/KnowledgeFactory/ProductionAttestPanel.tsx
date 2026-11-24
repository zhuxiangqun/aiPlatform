/**
 * ProductionAttestPanel — N11/N14 生产切写就绪产品面管理端 UI。
 *
 * 默认走 `/knowledge-migrations/product/*`（无 residual env 门）。
 * prod_attest_product_surface=true；production_cutover_certified / certified 恒 false。
 */
import React, { useCallback, useState } from 'react';
import { Card, CardContent, CardHeader, Button } from '../../components/ui';
import { ClipboardCheck } from 'lucide-react';

const API = (path: string) => `/api/platform/apps/fde${path}`;

function detailMessage(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object' && 'reason' in detail) {
    return String((detail as { reason?: unknown }).reason || JSON.stringify(detail));
  }
  return detail ? JSON.stringify(detail) : '请求失败';
}

const ProductionAttestPanel: React.FC = () => {
  const [tenantId, setTenantId] = useState('lock-service');
  const [jobId, setJobId] = useState('');
  const [actor, setActor] = useState('ops');
  const [reason, setReason] = useState('product readiness');
  const [rawOk, setRawOk] = useState(true);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  const [gateNote, setGateNote] = useState('');

  const runAttest = useCallback(async () => {
    if (!tenantId.trim() || !jobId.trim() || !actor.trim() || !reason.trim()) return;
    setBusy(true);
    try {
      const r = await fetch(API('/knowledge-migrations/product/production-attest'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tenant_id: tenantId.trim(),
          job_id: jobId.trim(),
          actor: actor.trim(),
          reason: reason.trim(),
          raw_fact_index_ok: rawOk,
        }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(body.detail));
      setNote(
        `status=${String(body.status)} · via=${String(body.via)} · product=${String(body.prod_attest_product_surface)} · certified=${String(body.certified)} · prod_certified=${String(body.production_cutover_certified)}${body.attestation_id ? ` · id=${body.attestation_id}` : ''}${body.error ? ` · error=${body.error}` : ''}`,
      );
    } catch (e: unknown) {
      setNote((e as Error)?.message || '签署失败');
    } finally {
      setBusy(false);
    }
  }, [tenantId, jobId, actor, reason, rawOk]);

  const runGate = useCallback(async () => {
    try {
      const r = await fetch(API('/knowledge-migrations/product/gate'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(body.detail));
      setGateNote(
        body.ok === true
          ? `product gate ok · surface=${String(body.prod_attest_product_surface)} · certified=${String(body.certified)}`
          : `product gate fail · ${(body.issues || []).join(',') || 'unknown'}`,
      );
    } catch (e: unknown) {
      setGateNote((e as Error)?.message || 'gate 失败');
    }
  }, []);

  return (
    <Card className="border-gray-800 bg-gray-950/40">
      <CardHeader className="flex flex-row items-center justify-between gap-2 py-3">
        <div className="flex items-center gap-2 text-[13px] text-gray-200">
          <ClipboardCheck className="h-4 w-4 text-emerald-400/80" />
          <span>生产切写就绪产品面（N11/N14）</span>
        </div>
        <Button type="button" size="sm" variant="ghost" onClick={() => void runGate()}>
          Gate
        </Button>
      </CardHeader>
      <CardContent className="space-y-3 text-[12px] text-gray-400">
        <p className="text-gray-500">
          默认可用：作业已授权 + 对账干净即可签署就绪回执。prod_attest_product_surface=true；非
          production_cutover_certified / 非 certified。
        </p>
        <div className="flex flex-wrap gap-2 items-end">
          <label className="flex flex-col gap-1">
            <span>tenant</span>
            <input
              className="rounded border border-gray-700 bg-gray-900 px-2 py-1 text-gray-200"
              value={tenantId}
              onChange={(e) => setTenantId(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span>job_id</span>
            <input
              className="rounded border border-gray-700 bg-gray-900 px-2 py-1 text-gray-200"
              value={jobId}
              onChange={(e) => setJobId(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span>actor</span>
            <input
              className="rounded border border-gray-700 bg-gray-900 px-2 py-1 text-gray-200"
              value={actor}
              onChange={(e) => setActor(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span>reason</span>
            <input
              className="rounded border border-gray-700 bg-gray-900 px-2 py-1 text-gray-200"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={rawOk}
              onChange={(e) => setRawOk(e.target.checked)}
            />
            <span>raw_fact_index_ok</span>
          </label>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={busy || !jobId.trim()}
            onClick={() => void runAttest()}
          >
            签署就绪回执
          </Button>
        </div>
        {note ? <p className="font-mono text-[11px] text-gray-500">{note}</p> : null}
        {gateNote ? <p className="text-gray-500">{gateNote}</p> : null}
      </CardContent>
    </Card>
  );
};

export default ProductionAttestPanel;
