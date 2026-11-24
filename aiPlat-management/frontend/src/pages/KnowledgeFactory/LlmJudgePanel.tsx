/**
 * LlmJudgePanel — N10 Gold LLM judge 产品面管理端 UI。
 *
 * 默认走 `/knowledge-gold/product/*`（无 residual env 门）。
 * llm_judge_product_surface=true；accuracy_claim / certified 恒 false。
 */
import React, { useCallback, useState } from 'react';
import { Card, CardContent, CardHeader, Button } from '../../components/ui';
import { Scale } from 'lucide-react';

const API = (path: string) => `/api/platform/apps/fde${path}`;

function detailMessage(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object' && 'reason' in detail) {
    return String((detail as { reason?: unknown }).reason || JSON.stringify(detail));
  }
  return detail ? JSON.stringify(detail) : '请求失败';
}

const LlmJudgePanel: React.FC = () => {
  const [expected, setExpected] = useState('opened');
  const [actual, setActual] = useState('open');
  const [subject, setSubject] = useState('InstallOrder:WO-1');
  const [predicate, setPredicate] = useState('status');
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  const [gateNote, setGateNote] = useState('');

  const runJudge = useCallback(async () => {
    if (!expected.trim() || !actual.trim()) return;
    setBusy(true);
    try {
      const r = await fetch(API('/knowledge-gold/product/llm-judge'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          expected: expected.trim(),
          actual: actual.trim(),
          subject: subject.trim(),
          predicate: predicate.trim(),
        }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(body.detail));
      setNote(
        `status=${String(body.status)} · matched=${String(body.matched)} · via=${String(body.via)} · product=${String(body.llm_judge_product_surface)} · accuracy=${String(body.accuracy_claim)} · certified=${String(body.certified)}${body.note ? ` · note=${body.note}` : ''}`,
      );
    } catch (e: unknown) {
      setNote((e as Error)?.message || '判定失败');
    } finally {
      setBusy(false);
    }
  }, [expected, actual, subject, predicate]);

  const runGate = useCallback(async () => {
    try {
      const r = await fetch(API('/knowledge-gold/product/gate'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(body.detail));
      setGateNote(
        body.ok === true
          ? `product gate ok · surface=${String(body.llm_judge_product_surface)} · accuracy=${String(body.accuracy_claim)} · certified=${String(body.certified)}`
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
          <Scale className="h-4 w-4 text-emerald-400/80" />
          <span>Gold LLM judge 产品面（N10）</span>
        </div>
        <Button type="button" size="sm" variant="ghost" onClick={() => void runGate()}>
          Gate
        </Button>
      </CardHeader>
      <CardContent className="space-y-3 text-[12px] text-gray-400">
        <p className="text-gray-500">
          默认可用：有界 object 语义等价。llm_judge_product_surface=true；非 accuracy_claim /
          非 certified。无模型时诚实 unavailable。
        </p>
        <div className="flex flex-wrap gap-2 items-end">
          <label className="flex flex-col gap-1">
            <span>expected</span>
            <input
              className="rounded border border-gray-700 bg-gray-900 px-2 py-1 text-gray-200"
              value={expected}
              onChange={(e) => setExpected(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span>actual</span>
            <input
              className="rounded border border-gray-700 bg-gray-900 px-2 py-1 text-gray-200"
              value={actual}
              onChange={(e) => setActual(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span>subject</span>
            <input
              className="rounded border border-gray-700 bg-gray-900 px-2 py-1 text-gray-200"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span>predicate</span>
            <input
              className="rounded border border-gray-700 bg-gray-900 px-2 py-1 text-gray-200"
              value={predicate}
              onChange={(e) => setPredicate(e.target.value)}
            />
          </label>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={busy || !expected.trim() || !actual.trim()}
            onClick={() => void runJudge()}
          >
            判定
          </Button>
        </div>
        {note ? <p className="font-mono text-[11px] text-gray-500">{note}</p> : null}
        {gateNote ? <p className="text-gray-500">{gateNote}</p> : null}
      </CardContent>
    </Card>
  );
};

export default LlmJudgePanel;
