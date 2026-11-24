/**
 * SloAlertPanel — SLO 告警候选产品面管理端 UI。
 *
 * 默认走 `/slo/product/*`（无 residual env 门）。
 * slo_alert_product_surface=true；attainment_ok / certified 恒 false；非 pager 投递。
 */
import React, { useCallback, useState } from 'react';
import { Card, CardContent, CardHeader, Button } from '../../components/ui';
import { Bell } from 'lucide-react';

const API = (path: string) => `/api/platform/apps/fde${path}`;

function detailMessage(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object' && 'reason' in detail) {
    return String((detail as { reason?: unknown }).reason || JSON.stringify(detail));
  }
  return detail ? JSON.stringify(detail) : '请求失败';
}

const SloAlertPanel: React.FC = () => {
  const [tenantId, setTenantId] = useState('lock-service');
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  const [gateNote, setGateNote] = useState('');

  const runAlerts = useCallback(async () => {
    if (!tenantId.trim()) return;
    setBusy(true);
    try {
      const r = await fetch(API('/slo/product/evaluate-alerts'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tenant_id: tenantId.trim(),
          window_hours: 24,
          include_live: true,
        }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(body.detail));
      setNote(
        `status=${String(body.status)} · alerts=${String(body.alert_count)} · via=${String(body.via)} · product=${String(body.slo_alert_product_surface)} · attainment=${String(body.attainment_ok)} · certified=${String(body.certified)}${body.note ? ` · note=${body.note}` : ''}`,
      );
    } catch (e: unknown) {
      setNote((e as Error)?.message || '评估失败');
    } finally {
      setBusy(false);
    }
  }, [tenantId]);

  const runGate = useCallback(async () => {
    try {
      const r = await fetch(API('/slo/product/gate'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(detailMessage(body.detail));
      setGateNote(
        body.ok === true
          ? `product gate ok · surface=${String(body.slo_alert_product_surface)} · certified=${String(body.certified)}`
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
          <Bell className="h-4 w-4 text-sky-400/80" />
          <span>SLO 告警候选产品面</span>
        </div>
        <Button type="button" size="sm" variant="ghost" onClick={() => void runGate()}>
          Gate
        </Button>
      </CardHeader>
      <CardContent className="space-y-3 text-[12px] text-gray-400">
        <p className="text-gray-500">
          默认可用：结构化告警候选。slo_alert_product_surface=true；非 pager 投递 /
          非 attainment_ok / 非 certified。
        </p>
        <label className="block space-y-1">
          <span className="text-gray-500">tenant_id</span>
          <input
            className="w-full rounded border border-gray-800 bg-gray-950 px-2 py-1 text-gray-200"
            value={tenantId}
            onChange={(e) => setTenantId(e.target.value)}
          />
        </label>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={busy || !tenantId.trim()}
          onClick={() => void runAlerts()}
        >
          评估告警候选
        </Button>
        {note ? <p className="font-mono text-[11px] text-gray-500">{note}</p> : null}
        {gateNote ? <p className="text-gray-500">{gateNote}</p> : null}
      </CardContent>
    </Card>
  );
};

export default SloAlertPanel;
