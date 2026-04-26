import React, { Suspense, useEffect, useMemo, useRef, useState } from 'react';
import PageHeader from '../../../components/common/PageHeader';
import { Badge, Button, Card, CardContent, CardHeader, Input, Modal, Select } from '../../../components/ui';
import { skillApi, workspaceSkillApi } from '../../../services';
import { toastGateError } from '../../../utils/governanceError';
import * as echarts from 'echarts';

const LazyECharts: any = React.lazy(() => import('echarts-for-react'));

type PinKind = 'scalar' | 'hist';

type RoutingPin = {
  id: string;
  title: string;
  // New schema (expert workflow): kind+tag (like TensorBoard tags)
  kind?: PinKind;
  tag?: string; // primary tag
  tags?: string[]; // multi-tag overlay (scalar only)
  // Legacy schema compatibility:
  metric?: string;
  since_hours: number;
  bucket_minutes: number;
  skill_id?: string;
  compare_profiles: boolean;
  compare_scopes: boolean;
  smoothing: number;
  // layout
  col_span?: number; // 1..cols
  size?: 's' | 'm' | 'l'; // height preset
  // y-axis mode for scalar charts
  y_mode?: 'single' | 'dual' | 'normalize';
  // series selection (expert): if set, only these legend names are shown (others are disabled)
  visible_series?: string[];
  // presets (expert): named series selections
  presets?: Array<{ name: string; visible_series: string[] }>;
};

const PINS_KEY = 'routing_dashboard_pins_v1';
const LAYOUT_KEY = 'routing_dashboard_layout_v1';

const normalizePin = (p: any): RoutingPin | null => {
  if (!p) return null;
  const id = String(p.id || '');
  if (!id) return null;
  const metric = String(p.metric || '');
  let kind: PinKind | undefined = p.kind === 'hist' ? 'hist' : p.kind === 'scalar' ? 'scalar' : undefined;
  let tag = p.tag ? String(p.tag) : '';
  const tagsArr0 = Array.isArray(p.tags) ? p.tags.map((x: any) => String(x || '')).filter(Boolean) : [];
  if (!kind || !tag) {
    if (metric) {
      kind = metric === 'selected_rank' ? 'hist' : 'scalar';
      tag = metric;
    }
  }
  if (!kind || !tag) return null;
  const tagsArr = tagsArr0.length ? tagsArr0 : [tag];
  return {
    id,
    title: String(p.title || tag),
    kind,
    tag,
    tags: kind === 'scalar' ? tagsArr : undefined,
    metric: metric || undefined,
    since_hours: Number(p.since_hours || 24),
    bucket_minutes: Number(p.bucket_minutes || 60),
    skill_id: p.skill_id ? String(p.skill_id) : undefined,
    compare_profiles: !!p.compare_profiles,
    compare_scopes: !!p.compare_scopes,
    smoothing: Number(p.smoothing || 0),
    col_span: Math.max(1, Number(p.col_span || 1)),
    size: (p.size === 'l' || p.size === 'm' || p.size === 's') ? p.size : 'm',
    y_mode: (p.y_mode === 'dual' || p.y_mode === 'normalize' || p.y_mode === 'single') ? p.y_mode : 'single',
    visible_series: Array.isArray(p.visible_series) ? p.visible_series.map((x: any) => String(x || '')).filter(Boolean) : undefined,
    presets: Array.isArray(p.presets)
      ? p.presets
          .map((x: any) => ({
            name: String(x?.name || ''),
            visible_series: Array.isArray(x?.visible_series) ? x.visible_series.map((y: any) => String(y || '')).filter(Boolean) : [],
          }))
          .filter((x: any) => x.name && x.visible_series)
      : undefined,
  };
};

// SLO thresholds (MVP): tune over time
const SLO = {
  strict_miss_rate: { green: 0.05, yellow: 0.15, direction: 'lower' },
  strict_misroute_rate: { green: 0.03, yellow: 0.1, direction: 'lower' },
  strict_miss_tool_rate: { green: 0.02, yellow: 0.08, direction: 'lower' },
  strict_miss_no_action_rate: { green: 0.02, yellow: 0.08, direction: 'lower' },
  score_gap_avg: { green: 2.0, yellow: 1.0, direction: 'higher' }, // gap too small => unstable routing
};

const sloBadge = (tag: string, value: number | null | undefined) => {
  if (value == null || Number.isNaN(Number(value))) return <Badge variant="default">n/a</Badge>;
  const v = Number(value);
  const cfg: any = (SLO as any)[tag];
  if (!cfg) return <Badge variant="default">SLO:n/a</Badge>;
  if (cfg.direction === 'higher') {
    if (v >= cfg.green) return <Badge variant="success">SLO:OK</Badge>;
    if (v >= cfg.yellow) return <Badge variant="warning">SLO:WARN</Badge>;
    return <Badge variant="error">SLO:BAD</Badge>;
  } else {
    if (v <= cfg.green) return <Badge variant="success">SLO:OK</Badge>;
    if (v <= cfg.yellow) return <Badge variant="warning">SLO:WARN</Badge>;
    return <Badge variant="error">SLO:BAD</Badge>;
  }
  return <Badge variant="default">n/a</Badge>;
};

const emaSmooth = (vals: Array<number | null | undefined>, s: number) => {
  const alpha = Math.max(0, Math.min(Number(s || 0), 0.99));
  if (!alpha) return vals.map((v) => (v == null ? null : Number(v)));
  let last: number | null = null;
  return vals.map((v) => {
    if (v == null) return null;
    const x = Number(v);
    if (last == null) {
      last = x;
      return x;
    }
    last = alpha * last + (1 - alpha) * x;
    return last;
  });
};

const loadPins = (): RoutingPin[] => {
  try {
    const s = localStorage.getItem(PINS_KEY);
    const v = s ? JSON.parse(s) : [];
    const arr = Array.isArray(v) ? (v as any[]) : [];
    return arr.map(normalizePin).filter(Boolean) as RoutingPin[];
  } catch {
    return [];
  }
};

const savePins = (pins: RoutingPin[]) => {
  try {
    localStorage.setItem(PINS_KEY, JSON.stringify(pins));
  } catch {
    // ignore
  }
};

const loadLayoutCols = (): number => {
  try {
    const s = localStorage.getItem(LAYOUT_KEY);
    const v = s ? JSON.parse(s) : null;
    const c = Number(v?.cols || 2);
    if (c === 1 || c === 2 || c === 3) return c;
    return 2;
  } catch {
    return 2;
  }
};

const saveLayoutCols = (cols: number) => {
  try {
    localStorage.setItem(LAYOUT_KEY, JSON.stringify({ cols }));
  } catch {
    // ignore
  }
};

const RoutingDashboard: React.FC = () => {
  const [pins, setPins] = useState<RoutingPin[]>(() => loadPins());
  const [scope, setScope] = useState<'workspace' | 'engine'>('workspace');
  const [loadingMap, setLoadingMap] = useState<Record<string, boolean>>({});
  const [metricsMap, setMetricsMap] = useState<Record<string, any>>({});
  const [cols, setCols] = useState<number>(() => loadLayoutCols());
  const [tags, setTags] = useState<any>(null);

  const [newKind, setNewKind] = useState<PinKind>('scalar');
  const [newTag, setNewTag] = useState<string>('strict_miss_rate');
  const [newExtraTags, setNewExtraTags] = useState<string>('');
  const [newTitle, setNewTitle] = useState<string>('');
  const [newSkillId, setNewSkillId] = useState<string>('');
  const [newSinceHours, setNewSinceHours] = useState<number>(24);
  const [newBucketMinutes, setNewBucketMinutes] = useState<number>(60);
  const [newSmoothing, setNewSmoothing] = useState<number>(0.0);
  const [newCompareProfiles, setNewCompareProfiles] = useState<boolean>(true);
  const [newCompareScopes, setNewCompareScopes] = useState<boolean>(false);
  const [newYMode, setNewYMode] = useState<'single' | 'dual' | 'normalize'>('single');
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [globalPresetOpen, setGlobalPresetOpen] = useState(false);
  const chartRefMap = useRef<Record<string, any>>({});
  const zoomDebounce = useRef<Record<string, any>>({});
  const zoomSyncLock = useRef<boolean>(false);
  const zoomSyncTimer = useRef<any>(null);
  const connectedOnce = useRef<boolean>(false);

  const broadcastZoom = (sourcePinId: string, startValueMs: number) => {
    if (!startValueMs || Number.isNaN(Number(startValueMs))) return;
    if (zoomSyncLock.current) return;
    zoomSyncLock.current = true;
    try {
      Object.entries(chartRefMap.current || {}).forEach(([pid, chart]) => {
        if (!chart || pid === sourcePinId) return;
        try {
          chart.dispatchAction({ type: 'dataZoom', dataZoomIndex: 0, startValue: startValueMs });
        } catch {
          // ignore
        }
      });
    } finally {
      setTimeout(() => {
        zoomSyncLock.current = false;
      }, 60);
    }

    if (zoomSyncTimer.current) clearTimeout(zoomSyncTimer.current);
    zoomSyncTimer.current = setTimeout(() => {
      const fromTs = Number(startValueMs) / 1000;
      const hrs = Math.max(1, Math.min(24 * 30, Math.ceil((Date.now() / 1000 - fromTs) / 3600)));
      setPins((prev) => {
        const next = prev.map((p) => {
          const k: any = (p.kind as any) || (p.metric === 'selected_rank' ? 'hist' : 'scalar');
          if (k !== 'scalar') return p;
          if (Number(p.since_hours) === hrs) return p;
          return { ...p, since_hours: hrs };
        });
        savePins(next);
        next.forEach((p) => {
          const k: any = (p.kind as any) || (p.metric === 'selected_rank' ? 'hist' : 'scalar');
          if (k === 'scalar') void fetchForPin(p);
        });
        return next;
      });
    }, 700);
  };

  const fetchForPin = async (pin: RoutingPin) => {
    const pinId = pin.id;
    setLoadingMap((m) => ({ ...m, [pinId]: true }));
    try {
      const profiles = pin.compare_profiles ? ['off', 'karpathy_v1'] : ['all'];
      const scopes = pin.compare_scopes ? ['workspace', 'engine'] : [scope];
      const reqs: Array<Promise<any>> = [];
      const keys: string[] = [];
      for (const sc of scopes) {
        const api0 = sc === 'engine' ? skillApi : workspaceSkillApi;
        for (const p of profiles) {
          keys.push(`${pinId}:${sc}:${p}`);
          reqs.push(
            (api0 as any).routingMetrics({
              since_hours: pin.since_hours,
              bucket_minutes: pin.bucket_minutes,
              skill_id: pin.skill_id,
              coding_policy_profile: p === 'all' ? undefined : p,
            })
          );
        }
      }
      const resArr = await Promise.all(reqs);
      const next: Record<string, any> = {};
      keys.forEach((k, idx) => (next[k] = resArr[idx]));
      setMetricsMap((mm) => ({ ...mm, ...next }));
    } catch (e: any) {
      toastGateError(e, '加载 routing_metrics 失败');
    } finally {
      setLoadingMap((m) => ({ ...m, [pinId]: false }));
    }
  };

  useEffect(() => {
    // initial fetch
    pins.forEach((p) => void fetchForPin(p));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const loadTags = async () => {
      try {
        // tags are the same for workspace/engine; fetch workspace first.
        const res: any = await (workspaceSkillApi as any).routingMetricTags();
        setTags(res);
        const firstScalar = res?.scalars?.[0]?.tag;
        const firstHist = res?.hists?.[0]?.tag;
        if (firstScalar && newKind === 'scalar') setNewTag(String(firstScalar));
        if (firstHist && newKind === 'hist') setNewTag(String(firstHist));
      } catch (e: any) {
        toastGateError(e, '加载 routing-metrics/tags 失败');
      }
    };
    loadTags();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const removePin = (id: string) => {
    const next = pins.filter((p) => p.id !== id);
    setPins(next);
    savePins(next);
  };

  const movePin = (id: string, dir: -1 | 1) => {
    const idx = pins.findIndex((p) => p.id === id);
    if (idx < 0) return;
    const j = idx + dir;
    if (j < 0 || j >= pins.length) return;
    const next = [...pins];
    const tmp = next[idx];
    next[idx] = next[j];
    next[j] = tmp;
    setPins(next);
    savePins(next);
  };

  const reorderPin = (dragId: string, dropId: string) => {
    if (!dragId || !dropId || dragId === dropId) return;
    const a = pins.findIndex((p) => p.id === dragId);
    const b = pins.findIndex((p) => p.id === dropId);
    if (a < 0 || b < 0) return;
    const next = [...pins];
    const [x] = next.splice(a, 1);
    next.splice(b, 0, x);
    setPins(next);
    savePins(next);
  };

  const setPinLayout = (id: string, patch: Partial<RoutingPin>) => {
    const next = pins.map((p) => (p.id === id ? { ...p, ...patch } : p));
    setPins(next);
    savePins(next);
  };

  const setPinVisibleSeries = (id: string, visible: string[] | undefined) => {
    const next = pins.map((p) => (p.id === id ? { ...p, visible_series: visible && visible.length ? visible : undefined } : p));
    setPins(next);
    savePins(next);
  };

  const applyGlobalPreset = (preset: string) => {
    const p = String(preset || '');
    setPins((prev) => {
      const next = prev.map((pin) => {
        const kind: any = (pin.kind as any) || (pin.metric === 'selected_rank' ? 'hist' : 'scalar');
        if (kind !== 'scalar') return pin;
        const tags0 = Array.isArray(pin.tags) && pin.tags.length ? pin.tags : [String(pin.tag || pin.metric || '')].filter(Boolean);
        const profiles = pin.compare_profiles ? ['off', 'karpathy_v1'] : ['all'];
        const scopes = pin.compare_scopes ? ['workspace', 'engine'] : [scope];
        const keys = scopes.flatMap((sc) => profiles.map((pr) => `${pin.id}:${sc}:${pr}`));
        const allLegendNames = tags0.flatMap((tg) => keys.map((k) => `${tg} | ${k.replace(`${pin.id}:`, '')}`));
        let visible: string[] | undefined = allLegendNames;
        if (p === 'workspace') visible = allLegendNames.filter((x) => x.includes('workspace:'));
        else if (p === 'engine') visible = allLegendNames.filter((x) => x.includes('engine:'));
        else if (p === 'off') visible = allLegendNames.filter((x) => x.endsWith(':off'));
        else if (p === 'karpathy_v1') visible = allLegendNames.filter((x) => x.endsWith(':karpathy_v1'));
        else if (p === 'strict_*') visible = allLegendNames.filter((x) => x.startsWith('strict_'));
        return { ...pin, visible_series: visible && visible.length ? visible : undefined };
      });
      savePins(next);
      return next;
    });
  };

  const addPreset = (id: string, name: string) => {
    const nm = (name || '').trim();
    if (!nm) return;
    const next = pins.map((p) => {
      if (p.id !== id) return p;
      const vis = Array.isArray(p.visible_series) && p.visible_series.length ? p.visible_series : [];
      const presets = Array.isArray(p.presets) ? [...p.presets] : [];
      const idx = presets.findIndex((x) => x.name === nm);
      const item = { name: nm, visible_series: vis };
      if (idx >= 0) presets[idx] = item;
      else presets.unshift(item);
      return { ...p, presets: presets.slice(0, 20) };
    });
    setPins(next);
    savePins(next);
  };

  const applyPreset = (id: string, name: string) => {
    const p0 = pins.find((p) => p.id === id);
    const ps = (p0?.presets || []).find((x) => x.name === name);
    if (!ps) return;
    setPinVisibleSeries(id, ps.visible_series);
  };

  const deletePreset = (id: string, name: string) => {
    const next = pins.map((p) => {
      if (p.id !== id) return p;
      const presets = (p.presets || []).filter((x) => x.name !== name);
      return { ...p, presets: presets.length ? presets : undefined };
    });
    setPins(next);
    savePins(next);
  };

  const exportPins = () => {
    const blob = new Blob([JSON.stringify({ pins, layout: { cols } }, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'routing_dashboard_pins.json';
    a.click();
    URL.revokeObjectURL(url);
  };

  const shareLink = () => {
    const payload = encodeURIComponent(btoa(unescape(encodeURIComponent(JSON.stringify({ pins, layout: { cols } })))));
    const url = `${window.location.origin}${window.location.pathname}#/diagnostics/routing-dashboard?p=${payload}`;
    navigator.clipboard?.writeText(url);
  };

  const importFromLink = (encoded: string) => {
    try {
      const payload = JSON.parse(decodeURIComponent(escape(atob(decodeURIComponent(encoded)))));
      const pins2raw = Array.isArray(payload) ? payload : payload?.pins;
      const pins2 = Array.isArray(pins2raw) ? (pins2raw as any[]).map(normalizePin).filter(Boolean) : [];
      const cols2 = Number(payload?.layout?.cols || cols);
      if (pins2.length >= 0) {
        setPins(pins2 as any);
        savePins(pins2 as any);
        if (cols2 === 1 || cols2 === 2 || cols2 === 3) {
          setCols(cols2);
          saveLayoutCols(cols2);
        }
        (pins2 as any[]).forEach((p: any) => void fetchForPin(p));
      }
    } catch {
      // ignore
    }
  };

  // support ?p=... share param
  useEffect(() => {
    try {
      const sp = new URLSearchParams(window.location.search);
      const p = sp.get('p');
      if (p) importFromLink(p);
    } catch {
      // ignore
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Keyboard shortcuts (expert)
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const tag = (e.target as any)?.tagName?.toLowerCase?.();
      if (tag === 'input' || tag === 'textarea' || (e.target as any)?.isContentEditable) return;
      if (e.key === '1' || e.key === '2' || e.key === '3') {
        const c = Number(e.key);
        setCols(c);
        saveLayoutCols(c);
        return;
      }
      if (e.key === 'g') {
        setGlobalPresetOpen(true);
        return;
      }
      if (e.key === 'a') {
        applyGlobalPreset('all');
        return;
      }
      if (e.key === 'n') {
        // clear all scalar selections
        setPins((prev) => {
          const next = prev.map((p0) => {
            const k: any = (p0.kind as any) || (p0.metric === 'selected_rank' ? 'hist' : 'scalar');
            if (k !== 'scalar') return p0;
            return { ...p0, visible_series: [] };
          });
          savePins(next);
          return next;
        });
        return;
      }
      if (e.key === 'r') {
        Object.values(chartRefMap.current || {}).forEach((ch) => {
          try {
            ch.dispatchAction({ type: 'restore' });
          } catch {
            // ignore
          }
        });
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope]);

  const availableScalarTags = useMemo(() => (tags?.scalars || []).map((x: any) => ({ label: x.display_name || x.tag, value: x.tag })), [tags]);
  const availableHistTags = useMemo(() => (tags?.hists || []).map((x: any) => ({ label: x.display_name || x.tag, value: x.tag })), [tags]);

  const normalize01 = (vals: Array<number | null | undefined>) => {
    let mn = Infinity;
    let mx = -Infinity;
    for (const v0 of vals) {
      if (v0 == null) continue;
      const v = Number(v0);
      if (Number.isNaN(v)) continue;
      mn = Math.min(mn, v);
      mx = Math.max(mx, v);
    }
    if (!Number.isFinite(mn) || !Number.isFinite(mx) || mx - mn < 1e-12) return vals.map((v) => (v == null ? null : 0.5));
    return vals.map((v0) => (v0 == null ? null : (Number(v0) - mn) / (mx - mn)));
  };

  const addNewPin = () => {
    const id = `pin_${Date.now()}`;
    const extraTags = newExtraTags
      .split(',')
      .map((x) => x.trim())
      .filter(Boolean);
    const tags0 = newKind === 'scalar' ? [newTag, ...extraTags] : undefined;
    const pin: RoutingPin = {
      id,
      title: (newTitle || newTag) + (newSkillId.trim() ? ` · ${newSkillId.trim()}` : ''),
      kind: newKind,
      tag: newTag,
      tags: tags0,
      since_hours: newSinceHours,
      bucket_minutes: newBucketMinutes,
      skill_id: newSkillId.trim() || undefined,
      compare_profiles: newCompareProfiles,
      compare_scopes: newCompareScopes,
      smoothing: newSmoothing,
      col_span: 1,
      size: 'm',
      y_mode: newYMode,
    };
    const next = [pin, ...pins].slice(0, 50);
    setPins(next);
    savePins(next);
    void fetchForPin(pin);
  };

  const gridStyle: React.CSSProperties = {
    display: 'grid',
    gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`,
    gap: '1rem',
  };
  const cardHeight = (sz?: string) => {
    if (sz === 's') return 260;
    if (sz === 'l') return 520;
    return 360;
  };

  return (
    <div className="p-6 space-y-4">
      <PageHeader title="Routing Dashboard" description="Pin 常用图表，形成 TensorBoard 风格的大屏（本地保存 + 可分享链接）。" />

      <Card>
        <CardHeader title="全局设置" />
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-2 items-center">
            <div className="text-sm text-gray-300">
              默认 scope
              <div className="mt-1">
                <Select
                  value={scope}
                  onChange={(v: any) => setScope(v === 'engine' ? 'engine' : 'workspace')}
                  options={[
                    { label: 'workspace', value: 'workspace' },
                    { label: 'engine', value: 'engine' },
                  ]}
                />
              </div>
            </div>
            <div className="text-sm text-gray-300">
              列数
              <div className="mt-1">
                <Select
                  value={String(cols)}
                  onChange={(v: any) => {
                    const c = Number(v);
                    setCols(c);
                    saveLayoutCols(c);
                  }}
                  options={[
                    { label: '1 列', value: '1' },
                    { label: '2 列', value: '2' },
                    { label: '3 列', value: '3' },
                  ]}
                />
              </div>
            </div>
            <Button variant="secondary" onClick={exportPins}>
              导出 pins(JSON)
            </Button>
            <Button variant="secondary" onClick={shareLink}>
              复制分享链接
            </Button>
            <Button variant="secondary" onClick={() => setGlobalPresetOpen(true)}>
              全局预设
            </Button>
          </div>
          <div className="text-xs text-gray-500 mt-2">提示：在 Routing Replay 详情页点 “Pin” 可把图表固定到这里。</div>
          <div className="text-xs text-gray-500 mt-1">快捷键：1/2/3=列数，g=全局预设，a=全选，n=全不选，r=恢复缩放</div>
        </CardContent>
      </Card>

      <Modal open={globalPresetOpen} onClose={() => setGlobalPresetOpen(false)} title="全局预设" width={520}>
        <div className="space-y-2">
          <div className="text-sm text-gray-300">一键对所有 scalar pins 应用曲线过滤（基于 legend 名）。</div>
          <div className="grid grid-cols-2 gap-2">
            <Button variant="secondary" onClick={() => applyGlobalPreset('all')}>
              全部显示
            </Button>
            <Button variant="secondary" onClick={() => applyGlobalPreset('strict_*')}>
              只看 strict_*
            </Button>
            <Button variant="secondary" onClick={() => applyGlobalPreset('workspace')}>
              只看 workspace
            </Button>
            <Button variant="secondary" onClick={() => applyGlobalPreset('engine')}>
              只看 engine
            </Button>
            <Button variant="secondary" onClick={() => applyGlobalPreset('off')}>
              只看 off
            </Button>
            <Button variant="secondary" onClick={() => applyGlobalPreset('karpathy_v1')}>
              只看 karpathy_v1
            </Button>
          </div>
        </div>
      </Modal>

      <Card>
        <CardHeader title="添加图表（Tag 选择器）" />
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-6 gap-2 items-center">
            <Select
              value={newKind}
              onChange={(v: any) => {
                const k = v === 'hist' ? 'hist' : 'scalar';
                setNewKind(k);
                const first = k === 'hist' ? availableHistTags?.[0]?.value : availableScalarTags?.[0]?.value;
                if (first) setNewTag(String(first));
              }}
              options={[
                { label: 'scalar', value: 'scalar' },
                { label: 'hist', value: 'hist' },
              ]}
            />
            <Select value={newTag} onChange={(v: any) => setNewTag(String(v))} options={newKind === 'hist' ? availableHistTags : availableScalarTags} />
            <Input
              value={newExtraTags}
              onChange={(e: any) => setNewExtraTags(String(e.target.value || ''))}
              placeholder={newKind === 'scalar' ? 'extra tags: a,b,c' : '（hist 无需）'}
              disabled={newKind !== 'scalar'}
            />
            <Input value={newTitle} onChange={(e: any) => setNewTitle(String(e.target.value || ''))} placeholder="title（可选）" />
            <Input value={newSkillId} onChange={(e: any) => setNewSkillId(String(e.target.value || ''))} placeholder="skill_id（可选）" />
            <Input value={String(newSinceHours)} onChange={(e: any) => setNewSinceHours(Number(e.target.value || 24))} placeholder="since_hours" />
            <Button variant="primary" onClick={addNewPin}>
              添加到大屏
            </Button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3 items-center mt-3">
            <div className="text-sm text-gray-300">
              分桶：
              <Select
                value={String(newBucketMinutes)}
                onChange={(v: any) => setNewBucketMinutes(Number(v))}
                options={[
                  { label: '15 分钟', value: '15' },
                  { label: '60 分钟', value: '60' },
                  { label: '240 分钟', value: '240' },
                ]}
              />
            </div>
            <div className="text-sm text-gray-300">
              平滑（EMA）：
              <div className="mt-1 flex items-center gap-2">
                <input type="range" min={0} max={0.9} step={0.1} value={newSmoothing} onChange={(e: any) => setNewSmoothing(Number(e.target.value))} />
                <code className="text-xs">{newSmoothing.toFixed(1)}</code>
              </div>
            </div>
            <label className="text-sm text-gray-300 flex items-center gap-2">
              <input type="checkbox" checked={newCompareProfiles} onChange={(e: any) => setNewCompareProfiles(!!e.target.checked)} />
              对比 profile
            </label>
            <label className="text-sm text-gray-300 flex items-center gap-2">
              <input type="checkbox" checked={newCompareScopes} onChange={(e: any) => setNewCompareScopes(!!e.target.checked)} />
              对比 scope
            </label>
            <div className="text-sm text-gray-300">
              Y 轴模式：
              <Select
                value={newYMode}
                onChange={(v: any) => setNewYMode(v === 'dual' ? 'dual' : v === 'normalize' ? 'normalize' : 'single')}
                options={[
                  { label: 'single', value: 'single' },
                  { label: 'dual', value: 'dual' },
                  { label: 'normalize', value: 'normalize' },
                ]}
              />
            </div>
          </div>
          <div className="text-xs text-gray-500 mt-2">Tag 来源于 routing-metrics/tags；这就是 TensorBoard 的“tag → chart”工作流。</div>
        </CardContent>
      </Card>

      <div style={gridStyle}>
        {pins.map((pin) => {
          const pinId = pin.id;
          const kind: PinKind = (pin.kind as any) || (pin.metric === 'selected_rank' ? 'hist' : 'scalar');
          const tag = String(pin.tag || pin.metric || '');
          const tags0 = kind === 'scalar' ? (Array.isArray(pin.tags) && pin.tags.length ? pin.tags : [tag]) : [tag];
          const yMode = (pin.y_mode || 'single') as any;
          const profiles = pin.compare_profiles ? ['off', 'karpathy_v1'] : ['all'];
          const scopes = pin.compare_scopes ? ['workspace', 'engine'] : [scope];
          const keys = scopes.flatMap((sc) => profiles.map((p) => `${pinId}:${sc}:${p}`));
          const allLegendNames = tags0.flatMap((tg) => keys.map((k) => `${tg} | ${k.replace(`${pinId}:`, '')}`));
          const selectedLegend = (() => {
            if (Array.isArray(pin.visible_series) && pin.visible_series.length) return new Set(pin.visible_series);
            return null;
          })();
          const all = keys.map((k) => metricsMap[k]).filter(Boolean);

          const seriesFor = (metricTag: string, key: string) => {
            const arr = ((metricsMap?.[key]?.series || {})?.[metricTag] as any[]) || [];
            const ys0 = emaSmooth(
              arr.map((x: any) => (x ? x?.[1] : null)),
              pin.smoothing
            );
            const ys = yMode === 'normalize' ? normalize01(ys0) : ys0;
            return arr.map((x: any, idx: number) => [Number(x?.[0] || 0) * 1000, ys[idx]]);
          };

          const hist = (() => {
            const first = all[0];
            return (first?.hists || {})?.[tag] || {};
          })();

          const title = `${pin.title}${pin.skill_id ? ` · ${pin.skill_id}` : ''}`;
          const latestVal = (() => {
            if (kind !== 'scalar') return null;
            const k0 = keys[0];
            const arr = ((metricsMap?.[k0]?.series || {})?.[tag] as any[]) || [];
            for (let i = arr.length - 1; i >= 0; i--) {
              const v = arr[i]?.[1];
              if (v != null) return Number(v);
            }
            return null;
          })();

          return (
            <div
              key={pinId}
              draggable
              onDragStart={() => setDraggingId(pinId)}
              onDragEnd={() => setDraggingId(null)}
              onDragOver={(e) => {
                e.preventDefault();
              }}
              onDrop={() => {
                if (draggingId) reorderPin(draggingId, pinId);
                setDraggingId(null);
              }}
              style={{
                gridColumn: `span ${Math.max(1, Math.min(cols, Number(pin.col_span || 1)))} / span ${Math.max(1, Math.min(cols, Number(pin.col_span || 1)))}`,
              }}
            >
              <Card>
              <CardHeader
                title={title}
                extra={
                  kind === 'hist' ? (
                    <Badge variant="default">hist:{tag}</Badge>
                  ) : (
                    <div className="flex items-center gap-2">
                      {sloBadge(tag, latestVal)}
                      <code className="text-xs text-gray-300">{latestVal == null ? '-' : latestVal.toFixed(3)}</code>
                    </div>
                  )
                }
              />
              <CardContent>
                <div className="flex items-center gap-2 mb-2">
                  <Button variant="secondary" onClick={() => void fetchForPin(pin)} loading={!!loadingMap[pinId]}>
                    刷新
                  </Button>
                  <Button variant="secondary" onClick={() => movePin(pinId, -1)}>
                    上移
                  </Button>
                  <Button variant="secondary" onClick={() => movePin(pinId, 1)}>
                    下移
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => setPinLayout(pinId, { col_span: Math.max(1, Number(pin.col_span || 1) - 1) })}
                    disabled={Number(pin.col_span || 1) <= 1}
                  >
                    窄
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => setPinLayout(pinId, { col_span: Math.min(cols, Number(pin.col_span || 1) + 1) })}
                    disabled={Number(pin.col_span || 1) >= cols}
                  >
                    宽
                  </Button>
                  <Button variant="secondary" onClick={() => setPinLayout(pinId, { size: 's' })}>
                    小
                  </Button>
                  <Button variant="secondary" onClick={() => setPinLayout(pinId, { size: 'm' })}>
                    中
                  </Button>
                  <Button variant="secondary" onClick={() => setPinLayout(pinId, { size: 'l' })}>
                    大
                  </Button>
                  {kind === 'scalar' ? (
                    <Select
                      value={String(pin.y_mode || 'single')}
                      onChange={(v: any) => setPinLayout(pinId, { y_mode: v === 'dual' ? 'dual' : v === 'normalize' ? 'normalize' : 'single' })}
                      options={[
                        { label: 'y:single', value: 'single' },
                        { label: 'y:dual', value: 'dual' },
                        { label: 'y:norm', value: 'normalize' },
                      ]}
                    />
                  ) : null}
                  {kind === 'scalar' ? (
                    <>
                      <Button variant="secondary" onClick={() => setPinVisibleSeries(pinId, allLegendNames)}>
                        全选
                      </Button>
                      <Button variant="secondary" onClick={() => setPinVisibleSeries(pinId, [])}>
                        全不选
                      </Button>
                      <Select
                        value={tag}
                        onChange={(v: any) => {
                          const tg = String(v);
                          const vis = keys.map((k) => `${tg} | ${k.replace(`${pinId}:`, '')}`);
                          setPinVisibleSeries(pinId, vis);
                        }}
                        options={tags0.map((x) => ({ label: `只看:${x}`, value: x }))}
                      />
                      <Button
                        variant="secondary"
                        onClick={() => {
                          const nm = window.prompt('预设名称', '');
                          if (!nm) return;
                          addPreset(pinId, nm);
                        }}
                      >
                        保存预设
                      </Button>
                      <Select
                        value=""
                        onChange={(v: any) => applyPreset(pinId, String(v))}
                        options={(pin.presets || []).map((x) => ({ label: `应用:${x.name}`, value: x.name }))}
                      />
                      <Select
                        value=""
                        onChange={(v: any) => deletePreset(pinId, String(v))}
                        options={(pin.presets || []).map((x) => ({ label: `删除:${x.name}`, value: x.name }))}
                      />
                    </>
                  ) : null}
                  <Button variant="secondary" onClick={() => removePin(pinId)}>
                    删除
                  </Button>
                </div>
                <Suspense fallback={<div className="text-sm text-gray-500">加载图表组件...</div>}>
                  {kind === 'hist' ? (
                    <LazyECharts
                      style={{ height: cardHeight(pin.size) }}
                      option={{
                        backgroundColor: 'transparent',
                        tooltip: { trigger: 'axis' },
                        grid: { left: 40, right: 20, top: 20, bottom: 40 },
                        xAxis: { type: 'category', axisLabel: { color: '#9CA3AF' }, data: ['0', '1', '2', '3+'] },
                        yAxis: { type: 'value', axisLabel: { color: '#9CA3AF' } },
                        series: [{ type: 'bar', data: ['0', '1', '2', '3+'].map((k) => Number(hist?.[k] || 0)) }],
                      }}
                    />
                  ) : (
                    <LazyECharts
                      style={{ height: cardHeight(pin.size) }}
                      onChartReady={(chart: any) => {
                        chartRefMap.current[pinId] = chart;
                        chart.group = 'routing_scalars_group';
                        if (!connectedOnce.current) {
                          connectedOnce.current = true;
                          try {
                            echarts.connect('routing_scalars_group');
                          } catch {
                            // ignore
                          }
                        }
                      }}
                      onEvents={{
                        legendselectchanged: (evt: any) => {
                          try {
                            const sel = evt?.selected || {};
                            const vis = Object.entries(sel)
                              .filter(([, v]) => !!v)
                              .map(([k]) => String(k));
                            setPinVisibleSeries(pinId, vis);
                          } catch {
                            // ignore
                          }
                        },
                        datazoom: () => {
                          // Debounced: convert zoomed startValue into since_hours and refetch.
                          const inst = chartRefMap.current[pinId];
                          if (!inst) return;
                          const opt = inst.getOption?.() || {};
                          const dz = Array.isArray(opt.dataZoom) ? opt.dataZoom[0] : null;
                          const startValue = dz?.startValue;
                          if (!startValue) return;
                          broadcastZoom(pinId, Number(startValue));
                          if (zoomDebounce.current[pinId]) clearTimeout(zoomDebounce.current[pinId]);
                          zoomDebounce.current[pinId] = setTimeout(() => {
                            const fromTs = Number(startValue) / 1000;
                            if (!fromTs) return;
                            const hrs = Math.max(1, Math.min(24 * 30, Math.ceil((Date.now() / 1000 - fromTs) / 3600)));
                            if (hrs === Number(pin.since_hours)) return;
                            const nextPin = { ...pin, since_hours: hrs };
                            setPins((prev) => {
                              const next = prev.map((x) => (x.id === pinId ? nextPin : x));
                              savePins(next);
                              return next;
                            });
                            void fetchForPin(nextPin);
                          }, 600);
                        },
                      }}
                      option={{
                        backgroundColor: 'transparent',
                        tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
                        legend: {
                          textStyle: { color: '#9CA3AF' },
                          selected: selectedLegend
                            ? Object.fromEntries(allLegendNames.map((nm) => [nm, selectedLegend.has(nm)]))
                            : undefined,
                        },
                        grid: { left: 40, right: 20, top: 30, bottom: 40 },
                        xAxis: { type: 'time', axisLabel: { color: '#9CA3AF' } },
                        yAxis:
                          yMode === 'dual'
                            ? [
                                { type: 'value', axisLabel: { color: '#9CA3AF' }, min: 0, max: 1 },
                                { type: 'value', axisLabel: { color: '#9CA3AF' } },
                              ]
                            : { type: 'value', axisLabel: { color: '#9CA3AF' }, min: tag.includes('rate') || yMode === 'normalize' ? 0 : undefined, max: tag.includes('rate') || yMode === 'normalize' ? 1 : undefined },
                        dataZoom: [
                          { type: 'inside', throttle: 60 },
                          { type: 'slider', height: 18, bottom: 6 },
                        ],
                        toolbox: {
                          feature: { dataZoom: { yAxisIndex: 'none' }, restore: {} },
                          iconStyle: { borderColor: '#9CA3AF' },
                        },
                        series: tags0.flatMap((tg) =>
                          keys.map((k) => {
                            const rateLike = tg.includes('rate') || tg.includes('miss') || tg.includes('ratio');
                            return {
                              name: `${tg} | ${k.replace(`${pinId}:`, '')}`,
                              type: 'line',
                              smooth: true,
                              showSymbol: false,
                              yAxisIndex: yMode === 'dual' ? (rateLike ? 0 : 1) : 0,
                              data: seriesFor(tg, k),
                            };
                          })
                        ),
                      }}
                    />
                  )}
                </Suspense>
              </CardContent>
            </Card>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default RoutingDashboard;
