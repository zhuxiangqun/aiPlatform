import React, { useEffect, useState } from 'react';
import { Cpu, Loader2, ChevronDown, ChevronUp, Zap, Shield, AlertTriangle } from 'lucide-react';
import { apiClient } from '../../services';
import { Card, CardContent } from '../../components/ui';

interface ProfileData {
  model_tier: string;
  temperature: number;
  orchestration_mode: string;
  compression_strictness: number;
  gate_strictness: number;
  context_layers: number;
  context_max_sources: number;
  episodic_injection: boolean;
  semantic_injection: boolean;
  require_schema_validation: boolean;
  temperature_profile: string;
  max_parallel_agents: number;
  tool_whitelist: string[] | null;
  tool_rank_by: string;
}

interface ProfileStatus {
  active: ProfileData;
  presets: string[];
  session_override: Record<string, string>;
  last_failure_domain: string | null;
}

const PROFILE_COLORS: Record<string, string> = {
  safety_critical: 'bg-red-500/15 text-red-400 border-red-500/30',
  code_generation: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
  creative_exploration: 'bg-purple-500/15 text-purple-400 border-purple-500/30',
  quick_fact_lookup: 'bg-green-500/15 text-green-400 border-green-500/30',
  default: 'bg-gray-500/15 text-gray-400 border-gray-500/30',
};

const TIER_COLORS: Record<string, string> = {
  T1: 'bg-green-500/20 text-green-400 border-green-500/30',
  T2: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  T3: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  T4: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
  T5: 'bg-red-500/20 text-red-400 border-red-500/30',
  auto: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
};

export default function ControlProfilePanel() {
  const [data, setData] = useState<ProfileStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);
  const [switching, setSwitching] = useState<string | null>(null);
  const [error, setError] = useState<string>('');

  const fetchData = async () => {
    try {
      const resp = await apiClient.get<any>('/diagnostics/profile/status');
      setData(resp.data);
      setError('');
    } catch (e: any) {
      setError(e?.message || 'failed to load');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []);

  const handleSwitch = async (name: string) => {
    setSwitching(name);
    try {
      await apiClient.post<any>('/diagnostics/profile/switch', { name });
      fetchData();
    } catch (e: any) {
      console.error('Profile switch failed:', e);
    } finally {
      setSwitching(null);
    }
  };

  const handleReset = async () => {
    setSwitching('reset');
    try {
      await apiClient.post<any>('/diagnostics/profile/switch', { name: 'reset' });
      fetchData();
    } catch (e: any) {
      console.error('Reset failed:', e);
    } finally {
      setSwitching(null);
    }
  };

  if (loading) {
    return (
      <Card className="bg-dark-card border-dark-border">
        <CardContent className="p-4 flex items-center gap-2">
          <Loader2 className="w-4 h-4 animate-spin text-gray-400" />
          <span className="text-xs text-gray-500">Loading profile status...</span>
        </CardContent>
      </Card>
    );
  }

  if (error || !data) {
    return (
      <Card className="bg-dark-card border-dark-border">
        <CardContent className="p-4">
          <span className="text-xs text-gray-500">Profile status unavailable</span>
        </CardContent>
      </Card>
    );
  }

  const { active, presets, session_override, last_failure_domain } = data;
  const overrideName = session_override?._global || '';
  const isOverride = overrideName && !overrideName.startsWith('_auto_bump_');

  return (
    <Card className={`bg-dark-card border-dark-border ${expanded ? '' : ''}`}>
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3 cursor-pointer select-none"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-2">
          <Cpu className="w-4 h-4 text-blue-400" />
          <span className="text-sm font-semibold text-gray-200">控制画像</span>
          {isOverride && (
            <span className="text-xs px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-400 border border-purple-500/30">
              {overrideName}
            </span>
          )}
          {last_failure_domain && (
            <span className="text-xs px-1.5 py-0.5 rounded bg-red-500/20 text-red-400 border border-red-500/30 flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" />
              {last_failure_domain}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-[10px] px-1.5 py-0.5 rounded border ${TIER_COLORS[active.model_tier] || TIER_COLORS.auto}`}>
            {active.model_tier}
          </span>
          {expanded ? (
            <ChevronUp className="w-4 h-4 text-gray-500" />
          ) : (
            <ChevronDown className="w-4 h-4 text-gray-500" />
          )}
        </div>
      </div>

      {expanded && (
        <CardContent className="px-4 pb-4 pt-0 space-y-4">
          {/* D1-D6 6-dimension grid */}
          <div className="grid grid-cols-2 gap-2">
            {/* D1: Context */}
            <div className="bg-dark-hover rounded-lg p-2.5">
              <div className="text-[10px] text-gray-500 uppercase mb-1">🧠 上下文 D1</div>
              <div className="text-xs text-gray-300">layers: {active.context_layers}</div>
              <div className="text-xs text-gray-300">sources: {active.context_max_sources}</div>
            </div>
            {/* D2: Tools */}
            <div className="bg-dark-hover rounded-lg p-2.5">
              <div className="text-[10px] text-gray-500 uppercase mb-1">🔧 工具 D2</div>
              <div className="text-xs text-gray-300">
                {active.tool_whitelist ? `${active.tool_whitelist.length} tools` : 'all open'}
              </div>
              <div className="text-xs text-gray-300">rank: {active.tool_rank_by}</div>
            </div>
            {/* D3: Generation */}
            <div className="bg-dark-hover rounded-lg p-2.5">
              <div className="text-[10px] text-gray-500 uppercase mb-1">⚡ 模型 D3</div>
              <div className="text-xs text-gray-300">tier: {active.model_tier}</div>
              <div className="text-xs text-gray-300">temp: {active.temperature.toFixed(2)}</div>
              <div className="text-xs text-gray-300">mode: {active.temperature_profile}</div>
            </div>
            {/* D4: Orchestration */}
            <div className="bg-dark-hover rounded-lg p-2.5">
              <div className="text-[10px] text-gray-500 uppercase mb-1">🔄 编排 D4</div>
              <div className="text-xs text-gray-300">mode: {active.orchestration_mode}</div>
              <div className="text-xs text-gray-300">parallel: {active.max_parallel_agents}</div>
            </div>
            {/* D5: Memory */}
            <div className="bg-dark-hover rounded-lg p-2.5">
              <div className="text-[10px] text-gray-500 uppercase mb-1">💾 记忆 D5</div>
              <div className="text-xs text-gray-300">compress: {active.compression_strictness.toFixed(1)}x</div>
              <div className="text-xs text-gray-300">
                episodic: {active.episodic_injection ? '✓' : '✗'} semantic: {active.semantic_injection ? '✓' : '✗'}
              </div>
            </div>
            {/* D6: Output */}
            <div className="bg-dark-hover rounded-lg p-2.5">
              <div className="text-[10px] text-gray-500 uppercase mb-1">✓ 输出 D6</div>
              <div className="text-xs text-gray-300">gate: {active.gate_strictness.toFixed(1)}x</div>
              <div className="text-xs text-gray-300">schema: {active.require_schema_validation ? '✓' : '✗'}</div>
            </div>
          </div>

          {/* Preset profile list */}
          <div>
            <div className="text-[10px] text-gray-500 uppercase mb-1.5">预设画像</div>
            <div className="flex flex-wrap gap-1.5">
              {presets.map((name) => (
                <button
                  key={name}
                  onClick={() => handleSwitch(name)}
                  disabled={switching === name}
                  className={`text-xs px-2 py-1 rounded border transition-colors
                    ${isOverride && overrideName === name
                      ? 'border-primary text-primary bg-primary/10'
                      : (PROFILE_COLORS[name] || 'bg-gray-800 text-gray-400 border-gray-700')}
                    ${switching === name ? 'opacity-50' : 'hover:brightness-110'}
                    cursor-pointer`}
                >
                  {switching === name ? (
                    <Loader2 className="w-3 h-3 animate-spin inline mr-1" />
                  ) : null}
                  {name}
                </button>
              ))}
            </div>
          </div>

          {/* Session override */}
          {isOverride && (
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-gray-500">
                会话覆盖: {overrideName}
              </span>
              <button
                onClick={handleReset}
                disabled={switching === 'reset'}
                className="text-[10px] text-blue-400 hover:text-blue-300"
              >
                {switching === 'reset' ? '重置中...' : '恢复默认'}
              </button>
            </div>
          )}

          {/* Footer */}
          <div className="pt-2 border-t border-dark-border text-[10px] text-gray-600">
            5 presets · 6-dimension adaptive control · /profile to switch
          </div>
        </CardContent>
      )}
    </Card>
  );
}
