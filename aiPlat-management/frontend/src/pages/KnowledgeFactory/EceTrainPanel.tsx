/**
 * EceTrainPanel — N13 样本 ECE 训练产品面管理端 UI。
 *
 * 默认走 `/confidence-calibrations/product/*`（无 residual env 门）。
 * ece_train_product_surface=true；accuracy_claim / certified 恒 false。
 */
import React, { useCallback, useState } from 'react';
import { Card, CardContent, CardHeader, Button } from '../../components/ui';
import { Gauge } from 'lucide-react';

const API = (path: string) => `/api/platform/apps/fde${path}`;

function detailMessage(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object' && 'reason' in detail) {
    return String((detail as { reason?: unknown }).reason || JSON.stringify(detail));
  }
  return detail ? JSON.stringify(detail) : '请求失败';
}

/** 默认演示样本：单箱 conf=acc≈0.7 → ECE≈0（非准确率宣称）。 */
function demoSamples(): Array<{ confidence: number; correct: boolean }> {
  const rows: Array<{ confidence: number; correct: boolean }> = [];
  for (let i = 0; i < 70; i += 1) rows.push({ confidence: 0.7, correct: true });
  for (let i = 0; i < 30; i += 1) rows.push({ confidence: 0.7, correct: false });
  return rows;
}

const EceTrainPanel: React.FC = () => {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  const [gateNote, setGateNote] = useState('');

  const runTrain = useCallback(async () => {
    setBusy(true);
    try {
      const r = await fetch(API('/confidence-calibrations/product/ece-train'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          samples: demoSamples(),
          n_bins: 10,
          high_threshold: 0.8,
        }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(body.detail));
      setNote(
        `status=${String(body.status)} · ece=${String(body.ece)} · brier=${String(body.brier)} · n=${String(body.sample_size)} · via=${String(body.via)} · product=${String(body.ece_train_product_surface)} · accuracy=${String(body.accuracy_claim)} · certified=${String(body.certified)}${body.note ? ` · note=${body.note}` : ''}`,
      );
    } catch (e: unknown) {
      setNote((e as Error)?.message || '训练失败');
    } finally {
      setBusy(false);
    }
  }, []);

  const runGate = useCallback(async () => {
    try {
      const r = await fetch(API('/confidence-calibrations/product/gate'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(body.detail));
      setGateNote(
        body.ok === true
          ? `product gate ok · surface=${String(body.ece_train_product_surface)} · accuracy=${String(body.accuracy_claim)} · certified=${String(body.certified)}`
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
          <Gauge className="h-4 w-4 text-sky-400/80" />
          <span>样本 ECE 训练产品面（N13）</span>
        </div>
        <Button type="button" size="sm" variant="ghost" onClick={() => void runGate()}>
          Gate
        </Button>
      </CardHeader>
      <CardContent className="space-y-3 text-[12px] text-gray-400">
        <p className="text-gray-500">
          默认可用：有界样本 ECE/Brier。ece_train_product_surface=true；非 accuracy_claim /
          非 certified。空样本诚实 unavailable。演示样本 n=100、conf=0.7。
        </p>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={() => void runTrain()}
        >
          训练演示样本
        </Button>
        {note ? <p className="font-mono text-[11px] text-gray-500">{note}</p> : null}
        {gateNote ? <p className="text-gray-500">{gateNote}</p> : null}
      </CardContent>
    </Card>
  );
};

export default EceTrainPanel;
