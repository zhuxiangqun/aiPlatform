import React, { useEffect, useState } from 'react';
import { Zap, Cpu, Loader2, ChevronDown, ChevronUp } from 'lucide-react';
import { apiClient } from '../../services';
import { Card, CardContent } from '../../components/ui';
import toast from '../../components/ui/toast';

interface TierInfo {
  label: string;
  model: string;
  fallback_models: string[];
  complexity_range: number[];
  status: string;
}

interface ModelTierData {
  status: { current_tier: string; current_model: string; last_complexity: string; override_active: boolean };
  tiers: Record<string, TierInfo>;
  cost?: Record<string, { model: string; prompt_per_1m: number; estimated_monthly: number }>;
  health?: Record<string, { model: string; latency_p95_s: number; failure_rate: number; status: string }>;
}

const TIER_COLORS: Record<string, string> = {
  T1: 'bg-green-500/20 text-green-400 border-green-500/30',
  T2: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  T3: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  T4: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  T5: 'bg-red-500/20 text-red-400 border-red-500/30',
};

const TIER_ICONS: Record<string, string> = {
  T1: '⚡',
  T2: '💬',
  T3: '✏️',
  T4: '🧠',
  T5: '🔥',
};

export default function ModelTierPanel() {
  const [data, setData] = useState<ModelTierData | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);
  const [switching, setSwitching] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      const resp = await apiClient.get<any>('/diagnostics/model-tier');
      setData(resp.data);
    } catch {
      // silently fail
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []);

  const handleTierSwitch = async (tierId: string, modelName: string) => {
    setSwitching(tierId);
    try {
      await apiClient.post<any>('/model-override', { model_name: modelName });
      toast?.success?.(`Switched to ${modelName} (${data?.tiers[tierId]?.label})`) ||
        console.log(`Switched to ${modelName}`);
      fetchData();
    } catch (e: any) {
      toast?.error?.(`Switch failed: ${e?.message || 'unknown'}`) ||
        console.error('Switch failed', e);
    } finally {
      setSwitching(null);
    }
  };

  const handleClearOverride = async () => {
    try {
      await apiClient.post<any>('/model-override', { model_name: '' });
      toast?.success?.('Model override cleared — back to auto-routing') ||
        console.log('Override cleared');
      fetchData();
    } catch (e: any) {
      toast?.error?.(`Clear failed: ${e?.message || 'unknown'}`);
    }
  };

  if (loading) return <Loader2 className="w-4 h-4 animate-spin text-gray-400" />;
  if (!data) return <span className="text-xs text-gray-500">Model tier unavailable</span>;

  const tiers = Object.entries(data.tiers || {}).sort();

  return (
    <div className="bg-dark-card border border-dark-border rounded-lg p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-3 cursor-pointer" onClick={() => setExpanded(!expanded)}>
        <div className="flex items-center gap-2">
          <Cpu className="w-4 h-4 text-blue-400" />
          <span className="text-sm font-semibold text-gray-200">Model Tiers</span>
          {data.status.override_active && (
            <span className="text-xs px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-400 border border-purple-500/30">
              Override: {data.status.overridden_model || 'active'}
            </span>
          )}
        </div>
        {expanded ? <ChevronUp className="w-4 h-4 text-gray-500" /> : <ChevronDown className="w-4 h-4 text-gray-500" />}
      </div>

      {expanded && (
        <>
          {/* Auto-routing status */}
          {data.status.override_active && (
            <button
              onClick={handleClearOverride}
              className="w-full text-xs text-gray-400 hover:text-gray-200 mb-2 py-1 rounded bg-gray-800 hover:bg-gray-700 transition-colors"
            >
              Clear override — resume auto-routing
            </button>
          )}

          {/* Tier list */}
          <div className="space-y-1.5">
            {tiers.map(([tierId, tier]) => (
              <div
                key={tierId}
                className={`flex items-center justify-between px-2 py-1.5 rounded border cursor-pointer transition-colors
                  ${TIER_COLORS[tierId] || 'bg-gray-800 text-gray-400 border-gray-700'}
                  ${switching === tierId ? 'opacity-50' : ''}
                  ${tier.status === 'degraded' ? 'opacity-60' : ''}
                  hover:brightness-110`}
                onClick={() => tier.status === 'available' && handleTierSwitch(tierId, tier.model)}
                title={`${tier.label}: ${tier.model} (${tier.complexity_range[0]}-${tier.complexity_range[1]})`}
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-xs">{TIER_ICONS[tierId] || '•'}</span>
                  <div className="min-w-0">
                    <div className="text-xs font-medium truncate">{tierId} — {tier.label}</div>
                    <div className="text-[10px] opacity-70 truncate">{tier.model}</div>
                  </div>
                </div>
                <div className="flex items-center gap-1 flex-shrink-0 ml-2">
                  {tier.status === 'degraded' && (
                    <span className="text-[10px] text-yellow-400">⚠️</span>
                  )}
                  {switching === tierId ? (
                    <Loader2 className="w-3 h-3 animate-spin" />
                  ) : (
                    <Zap className="w-3 h-3 opacity-50" />
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* Cost savings (B) */}
          {data.cost && Object.keys(data.cost).length > 0 && (
            <div className="mt-3 pt-2 border-t border-dark-border">
              <div className="text-[10px] text-gray-500 mb-1">Estimated cost ($/1M prompt tokens)</div>
              <div className="grid grid-cols-5 gap-1">
                {Object.entries(data.cost).map(([tierId, c]) => (
                  <div key={tierId} className="text-center text-[10px]">
                    <div className="text-gray-400">{tierId}</div>
                    <div className="text-gray-300 font-mono">${c.prompt_per_1m.toFixed(2)}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Health status (C) */}
          {data.health && Object.keys(data.health).length > 0 && (
            <div className="mt-2 pt-2 border-t border-dark-border">
              <div className="text-[10px] text-gray-500 mb-1">Health (P95 / failure rate)</div>
              <div className="grid grid-cols-5 gap-1">
                {Object.entries(data.health).map(([tierId, h]) => (
                  <div key={tierId} className="text-center text-[10px]">
                    <div className={`font-medium ${
                      h.status === 'healthy' ? 'text-green-400' :
                      h.status === 'degraded' ? 'text-yellow-400' : 'text-red-400'
                    }`}>
                      {h.latency_p95_s > 0 ? `${h.latency_p95_s}s` : '--'}
                    </div>
                    <div className="text-gray-500">
                      {h.failure_rate > 0 ? `${(h.failure_rate * 100).toFixed(0)}%` : '0%'}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Footer */}
          <div className="mt-3 pt-2 border-t border-dark-border text-[10px] text-gray-500">
            Auto-routing: simple→T1, medium→T3, complex→T4/T5
          </div>
        </>
      )}
    </div>
  );
}
