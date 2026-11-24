/**
 * Lv4AutoClosePanel — N08 有界 Lv4 auto-close 产品面管理端 UI。
 *
 * 默认走 `/lv4-auto-close/product/*`（无 residual env 门）。
 * lv4_product_surface=true；full_action_lv4 / certified 恒 false。
 */
import React, { useCallback, useState } from 'react';
import { Card, CardContent, CardHeader, Button } from '../../components/ui';
import { ShieldCheck } from 'lucide-react';

const API = (path: string) => `/api/platform/apps/fde${path}`;

function detailMessage(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object' && 'reason' in detail) {
    return String((detail as { reason?: unknown }).reason || JSON.stringify(detail));
  }
  return detail ? JSON.stringify(detail) : '请求失败';
}

const Lv4AutoClosePanel: React.FC = () => {
  const [actionId, setActionId] = useState('demo-action');
  const [rollbackId, setRollbackId] = useState('demo-rollback');
  const [total, setTotal] = useState(100);
  const [falsePositives, setFalsePositives] = useState(0);
  const [riskLevel, setRiskLevel] = useState('low');
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  const [gateNote, setGateNote] = useState('');

  const runEval = useCallback(async () => {
    if (!actionId.trim()) return;
    setBusy(true);
    try {
      const r = await fetch(API('/lv4-auto-close/product/evaluate'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action_id: actionId.trim(),
          total,
          false_positives: falsePositives,
          rollback_action_id: rollbackId.trim(),
          risk_level: riskLevel,
          action_level: 'lv4_auto_close',
          min_samples: 10,
        }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(body.detail));
      setNote(
        `status=${String(body.status)} · via=${String(body.via)} · allowed=${String(body.auto_close_allowed)} · product=${String(body.lv4_product_surface)} · full_lv4=${String(body.full_action_lv4)} · certified=${String(body.certified)}${body.reason ? ` · reason=${body.reason}` : ''}`,
      );
    } catch (e: unknown) {
      setNote((e as Error)?.message || '评估失败');
    } finally {
      setBusy(false);
    }
  }, [actionId, rollbackId, total, falsePositives, riskLevel]);

  const runGate = useCallback(async () => {
    try {
      const r = await fetch(API('/lv4-auto-close/product/gate'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(body.detail));
      setGateNote(
        body.ok === true
          ? `product gate ok · surface=${String(body.lv4_product_surface)} · full=${String(body.full_action_lv4)} · certified=${String(body.certified)}`
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
          <ShieldCheck className="h-4 w-4 text-emerald-400/80" />
          <span>有界 Lv4 auto-close 产品面（N08）</span>
        </div>
        <Button type="button" size="sm" variant="ghost" onClick={() => void runGate()}>
          Gate
        </Button>
      </CardHeader>
      <CardContent className="space-y-3 text-[12px] text-gray-400">
        <p className="text-gray-500">
          默认可用：仅 low 风险 + lv4_auto_close + 误报门 v2。lv4_product_surface=true；非
          full_action_lv4 / 非 certified。
        </p>
        <div className="flex flex-wrap gap-2 items-end">
          <label className="flex flex-col gap-1">
            <span>action_id</span>
            <input
              className="rounded border border-gray-700 bg-gray-900 px-2 py-1 text-gray-200"
              value={actionId}
              onChange={(e) => setActionId(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span>rollback</span>
            <input
              className="rounded border border-gray-700 bg-gray-900 px-2 py-1 text-gray-200"
              value={rollbackId}
              onChange={(e) => setRollbackId(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span>total</span>
            <input
              type="number"
              min={0}
              className="w-24 rounded border border-gray-700 bg-gray-900 px-2 py-1 text-gray-200"
              value={total}
              onChange={(e) => setTotal(Number(e.target.value) || 0)}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span>false_positives</span>
            <input
              type="number"
              min={0}
              className="w-24 rounded border border-gray-700 bg-gray-900 px-2 py-1 text-gray-200"
              value={falsePositives}
              onChange={(e) => setFalsePositives(Number(e.target.value) || 0)}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span>risk</span>
            <select
              className="rounded border border-gray-700 bg-gray-900 px-2 py-1 text-gray-200"
              value={riskLevel}
              onChange={(e) => setRiskLevel(e.target.value)}
            >
              <option value="low">low</option>
              <option value="medium">medium</option>
              <option value="high">high</option>
            </select>
          </label>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={busy || !actionId.trim()}
            onClick={() => void runEval()}
          >
            评估
          </Button>
        </div>
        {note ? <p className="font-mono text-[11px] text-gray-500">{note}</p> : null}
        {gateNote ? <p className="text-gray-500">{gateNote}</p> : null}
      </CardContent>
    </Card>
  );
};

export default Lv4AutoClosePanel;
