/**
 * ObjectSetWhereExprPanel — N07/N22 `$expr`/`$where` 产品面管理端 UI。
 *
 * 默认走 `/object-sets/product/*`。
 * objectset_where_expr_product_surface=true；$where 仍 unavailable；certified 恒 false。
 */
import React, { useCallback, useState } from 'react';
import { Card, CardContent, CardHeader, Button } from '../../components/ui';
import { Filter } from 'lucide-react';

const API = (path: string) => `/api/platform/apps/fde${path}`;

function detailMessage(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object' && 'reason' in detail) {
    return String((detail as { reason?: unknown }).reason || JSON.stringify(detail));
  }
  return detail ? JSON.stringify(detail) : '请求失败';
}

const ObjectSetWhereExprPanel: React.FC = () => {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  const [gateNote, setGateNote] = useState('');

  const runExpr = useCallback(async () => {
    setBusy(true);
    try {
      const r = await fetch(API('/object-sets/product/where-expr'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          item: { status: 'open', n: 3 },
          filter: { $expr: { $eq: ['$status', 'open'] } },
          max_depth: 4,
        }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(body.detail));
      setNote(
        `status=${String(body.status)} · matched=${String(body.matched)} · via=${String(body.via)} · product=${String(body.objectset_where_expr_product_surface)} · where_js=${String(body.where_js_eval)} · certified=${String(body.certified)}${body.note ? ` · note=${body.note}` : ''}`,
      );
    } catch (e: unknown) {
      setNote((e as Error)?.message || '判定失败');
    } finally {
      setBusy(false);
    }
  }, []);

  const runGate = useCallback(async () => {
    try {
      const r = await fetch(API('/object-sets/product/gate'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(body.detail));
      setGateNote(
        body.ok === true
          ? `product gate ok · surface=${String(body.objectset_where_expr_product_surface)} · where_js=${String(body.where_js_eval)} · certified=${String(body.certified)}`
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
          <Filter className="h-4 w-4 text-sky-400/80" />
          <span>ObjectSet $expr/$where 产品面（N07/N22）</span>
        </div>
        <Button type="button" size="sm" variant="ghost" onClick={() => void runGate()}>
          Gate
        </Button>
      </CardHeader>
      <CardContent className="space-y-3 text-[12px] text-gray-400">
        <p className="text-gray-500">
          默认可用：有界 $expr 结构化回执。objectset_where_expr_product_surface=true；$where
          仍 unavailable（禁 JS）；非 certified。演示：$status ≡ open。
        </p>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={() => void runExpr()}
        >
          判定演示 $expr
        </Button>
        {note ? <p className="font-mono text-[11px] text-gray-500">{note}</p> : null}
        {gateNote ? <p className="text-gray-500">{gateNote}</p> : null}
      </CardContent>
    </Card>
  );
};

export default ObjectSetWhereExprPanel;
