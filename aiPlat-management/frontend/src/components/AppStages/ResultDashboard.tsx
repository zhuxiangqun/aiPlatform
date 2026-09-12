import React, { useState, useEffect, useMemo } from 'react';
import { Card, Badge } from '../ui';
import { Copy } from 'lucide-react';

type SectionType =
  | 'tag_cloud'
  | 'text_block'
  | 'markdown'
  | 'timeline'
  | 'table'
  | 'key_value'
  | 'image_timeline'
  | 'subtitle_timeline';

interface SectionConfig {
  key: string;
  label: string;
  type: SectionType | string;
}

interface ResultConfig {
  sections?: SectionConfig[];
  input?: Record<string, string>;
}

interface Props {
  config: ResultConfig;
  onExecute: (skill: string, params: Record<string, any>) => Promise<any>;
  skill: string;
  stageInput?: Record<string, any>;
  projectId?: string;
}

const KEY_ALIASES: Record<string, string[]> = {
  metadata: ['metadata', 'video_metadata'],
  keyframes: ['keyframes', 'frames', 'frame_analysis'],
  scene_changes: ['scene_changes', 'scenes'],
  subtitle: ['subtitle', 'subtitle_analysis', 'subtitles'],
  speech: ['speech', 'speech_analysis', 'audio'],
  vad: ['vad', 'vad_segments'],
  transcript: ['transcript_segments', 'transcript', 'transcript_text', 'speech_analysis'],
  summary: ['summary', 'ai_summary', 'report_summary'],
};

function pickValue(data: Record<string, any>, key: string): any {
  if (data[key] !== undefined && data[key] !== null) return data[key];
  for (const alt of KEY_ALIASES[key] || []) {
    if (data[alt] !== undefined && data[alt] !== null) return data[alt];
  }
  return undefined;
}

/** Map absolute ~/.aiplat/apps/{app}/media/{task}/... → /app/media/{app}/{task}/... */
function mediaUrlFromLocalPath(localPath: string): string | null {
  if (!localPath) return null;
  if (/^https?:\/\//i.test(localPath) || localPath.startsWith('/app/')) return localPath;
  const m = String(localPath).replace(/\\/g, '/').match(
    /\/(?:\.aiplat\/)?apps\/([^/]+)\/media\/([^/]+)\/(.+)$/,
  );
  if (!m) return null;
  return `/app/media/${encodeURIComponent(m[1])}/${encodeURIComponent(m[2])}/${m[3]
    .split('/')
    .map(encodeURIComponent)
    .join('/')}`;
}

function formatSec(v: any): string {
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v ?? '');
  if (n >= 60) {
    const m = Math.floor(n / 60);
    const s = (n % 60).toFixed(n % 60 < 10 && m > 0 ? 1 : 1);
    return `${m}:${s.padStart(4, '0')}`;
  }
  return `${n.toFixed(n < 10 ? 2 : 1)}s`;
}

function isPlainObject(v: any): v is Record<string, any> {
  return !!v && typeof v === 'object' && !Array.isArray(v);
}

const FIELD_LABELS: Record<string, string> = {
  width: '宽度',
  height: '高度',
  duration_sec: '时长(秒)',
  duration: '时长',
  fps: '帧率',
  codec: '编码',
  resolution: '分辨率',
  language: '语种',
  speaker_count: '说话人数',
  emotion: '情绪',
  syllable_density: '音节密度',
  has_audio_track: '有音轨',
  has_subtitle_track: '有字幕轨',
  status: '状态',
  scene: '场景',
  subject: '主体',
  action: '动作',
};

function labelForKey(k: string): string {
  return FIELD_LABELS[k] || k;
}

/** Parse "scene=… subject=… action=…" captions into readable fields. */
function parseFrameCaption(raw: string): {
  scene?: string;
  subject?: string;
  action?: string;
  rest?: string;
} {
  const text = String(raw || '').trim();
  if (!text) return {};
  const re =
    /(scene|subject|action)\s*[=:：]\s*([\s\S]*?)(?=\s*(?:scene|subject|action)\s*[=:：]|$)/gi;
  const out: { scene?: string; subject?: string; action?: string; rest?: string } = {};
  let matched = false;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    matched = true;
    const key = m[1].toLowerCase();
    const val = m[2].trim().replace(/[|｜]\s*$/, '');
    if (key === 'scene') out.scene = val;
    else if (key === 'subject') out.subject = val;
    else if (key === 'action') out.action = val;
  }
  if (!matched) return { rest: text };
  return out;
}

function splitTranscriptParagraphs(text: string): string[] {
  const t = String(text || '').trim();
  if (!t) return [];
  const parts = t
    .split(/(?<=[。！？!?．\n])|(?<=です|ます|でした|ました)\s+/)
    .map((s) => s.trim())
    .filter(Boolean);
  if (parts.length >= 2) return parts;
  const soft: string[] = [];
  let buf = '';
  for (const ch of t) {
    buf += ch;
    if (buf.length >= 42 && /[\s、，,]/.test(ch)) {
      soft.push(buf.trim());
      buf = '';
    }
  }
  if (buf.trim()) soft.push(buf.trim());
  return soft.length ? soft : [t];
}

function KeyValueView({ value }: { value: any }) {
  if (value == null) return <p className="text-sm text-gray-500">无数据</p>;
  if (typeof value === 'string') {
    return <p className="text-sm text-gray-300 whitespace-pre-wrap">{value}</p>;
  }
  // Prefer nested acoustic_labels / flattened media probe
  let obj = value;
  if (isPlainObject(value)) {
    if (value.status === 'degraded' || value.status === 'failed') {
      return (
        <div className="text-sm space-y-1">
          <Badge variant="default" className="text-xs">
            {String(value.status)}
          </Badge>
          <p className="text-amber-300/90">
            {value.error_message || value.message || '该维度不可用或已降级'}
          </p>
          {value.has_audio_track === false && (
            <p className="text-gray-500 text-xs">未检测到音轨</p>
          )}
          {value.no_subtitle_track && (
            <p className="text-gray-500 text-xs">未检测到内嵌字幕轨道（本期不生成硬字幕）</p>
          )}
        </div>
      );
    }
    if (isPlainObject(value.acoustic_labels)) {
      obj = {
        language: value.acoustic_labels.language,
        speaker_count: value.acoustic_labels.speaker_count,
        emotion: value.acoustic_labels.emotion,
        syllable_density: value.syllable_density,
        has_audio_track: value.has_audio_track,
        status: value.status,
      };
    }
  }
  if (!isPlainObject(obj)) {
    return (
      <p className="text-sm text-gray-300 whitespace-pre-wrap">
        {JSON.stringify(obj, null, 2)}
      </p>
    );
  }
  const entries = Object.entries(obj).filter(
    ([k, v]) =>
      v !== undefined &&
      v !== null &&
      v !== '' &&
      !['task_id', 'local_path', 'video_path', 'report_path', 'export_json'].includes(k) &&
      typeof v !== 'object',
  );
  if (!entries.length) {
    return <p className="text-sm text-gray-500">无展示字段</p>;
  }
  return (
    <dl className="grid grid-cols-1 sm:grid-cols-[7.5rem_1fr] gap-x-3 gap-y-2.5 text-sm">
      {entries.map(([k, v]) => (
        <React.Fragment key={k}>
          <dt className="text-gray-500 shrink-0">{labelForKey(k)}</dt>
          <dd className="text-gray-100 break-words">{String(v)}</dd>
        </React.Fragment>
      ))}
    </dl>
  );
}

function TimelineView({ value }: { value: any }) {
  let items: any[] = [];
  if (Array.isArray(value)) items = value;
  else if (isPlainObject(value) && Array.isArray(value.segments)) items = value.segments;
  else if (isPlainObject(value) && Array.isArray(value.vad_segments)) items = value.vad_segments;
  else if (typeof value === 'number') items = [value];

  // Soft-merge adjacent numeric ranges for readability (VAD often returns 50+ scraps)
  if (
    items.length > 24 &&
    items.every(
      (it) =>
        isPlainObject(it) &&
        (it.start != null || it.time_sec != null) &&
        it.end != null,
    )
  ) {
    const merged: any[] = [];
    for (const it of items) {
      const start = Number(it.start ?? it.time_sec);
      const end = Number(it.end);
      if (!Number.isFinite(start) || !Number.isFinite(end)) continue;
      if (merged.length && start - Number(merged[merged.length - 1].end) <= 0.4) {
        merged[merged.length - 1].end = Math.max(Number(merged[merged.length - 1].end), end);
      } else {
        merged.push({ start, end });
      }
    }
    if (merged.length) items = merged;
  }

  if (!items.length) {
    return <p className="text-sm text-gray-500">无时间点</p>;
  }

  const maxShow = 40;
  return (
    <div className="flex flex-wrap gap-2">
      {items.slice(0, maxShow).map((it, i) => {
        let label = '';
        if (typeof it === 'number' || typeof it === 'string') label = formatSec(it);
        else if (isPlainObject(it)) {
          const start = it.start ?? it.time_sec ?? it.timestamp ?? it.t;
          const end = it.end;
          label =
            end != null ? `${formatSec(start)} – ${formatSec(end)}` : formatSec(start);
          if (it.label || it.text) label += ` · ${it.label || it.text}`;
        } else label = String(it);
        return (
          <Badge key={i} variant="default" className="text-xs font-mono">
            {label}
          </Badge>
        );
      })}
      {items.length > maxShow && (
        <span className="text-xs text-gray-500">+{items.length - maxShow} 更多</span>
      )}
    </div>
  );
}

function ImageTimelineView({ value }: { value: any }) {
  const [expanded, setExpanded] = useState(false);
  const [broken, setBroken] = useState<Record<number, boolean>>({});
  const frames = useMemo(() => {
    if (!Array.isArray(value)) return [];
    return value.map((f, i) => {
      if (typeof f === 'string') {
        return { key: i, src: mediaUrlFromLocalPath(f) || f, caption: `#${i + 1}`, tags: {} as ReturnType<typeof parseFrameCaption> };
      }
      const local = f?.local_path || f?.image_path || f?.path || f?.file_path || '';
      const src =
        f?.public_url ||
        f?.url ||
        f?.src ||
        mediaUrlFromLocalPath(String(local)) ||
        (typeof local === 'string' && local.startsWith('/app/') ? local : null);
      const t = f?.time_sec ?? f?.timestamp ?? f?.time_ms;
      const timeLabel =
        t != null
          ? formatSec(typeof t === 'number' && t > 1000 && !f?.time_sec ? t / 1000 : t)
          : `#${i + 1}`;
      const desc = String(f?.description || f?.caption || '').trim();
      const tags =
        f?.scene || f?.subject || f?.action
          ? {
              scene: f.scene ? String(f.scene) : undefined,
              subject: f.subject ? String(f.subject) : undefined,
              action: f.action ? String(f.action) : undefined,
            }
          : parseFrameCaption(desc);
      return { key: i, src, caption: timeLabel, tags };
    });
  }, [value]);

  if (!frames.length) return <p className="text-sm text-gray-500">无关键帧</p>;

  const shown = expanded ? frames : frames.slice(0, 8);

  return (
    <div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {shown.map((f) => (
          <div
            key={f.key}
            className="rounded-lg border border-dark-border overflow-hidden bg-dark-bg/50 flex gap-3 p-2"
          >
            <div className="w-36 shrink-0">
              {f.src && !broken[f.key] ? (
                <img
                  src={f.src}
                  alt=""
                  className="w-full h-24 object-cover rounded bg-black/40"
                  loading="lazy"
                  onError={() => setBroken((b) => ({ ...b, [f.key]: true }))}
                />
              ) : (
                <div className="w-full h-24 flex items-center justify-center text-xs text-gray-600 rounded bg-black/30">
                  无预览
                </div>
              )}
              <div className="mt-1 text-[11px] text-gray-400 font-mono text-center">{f.caption}</div>
            </div>
            <div className="min-w-0 flex-1 flex flex-col gap-1.5 justify-center py-0.5">
              {(['scene', 'subject', 'action'] as const).map((k) =>
                f.tags[k] ? (
                  <div key={k} className="text-xs leading-snug">
                    <span className="text-gray-500 mr-1.5">{labelForKey(k)}</span>
                    <span className="text-gray-200">{f.tags[k]}</span>
                  </div>
                ) : null,
              )}
              {f.tags.rest ? (
                <p className="text-xs text-gray-300 leading-relaxed line-clamp-3">{f.tags.rest}</p>
              ) : null}
              {!f.tags.scene && !f.tags.subject && !f.tags.action && !f.tags.rest ? (
                <p className="text-xs text-gray-600">暂无画面描述</p>
              ) : null}
            </div>
          </div>
        ))}
      </div>
      {frames.length > 8 && (
        <button
          type="button"
          className="mt-3 text-xs text-primary hover:underline"
          onClick={() => setExpanded((e) => !e)}
        >
          {expanded ? '收起' : `显示全部 ${frames.length} 帧`}
        </button>
      )}
    </div>
  );
}

function CueList({ items, maxH = 'max-h-80' }: { items: any[]; maxH?: string }) {
  return (
    <ul className={`space-y-2 ${maxH} overflow-y-auto pr-1`}>
      {items.slice(0, 200).map((c: any, i: number) => (
        <li
          key={i}
          className="rounded-md bg-dark-bg/40 border border-dark-border/60 px-3 py-2 flex gap-3"
        >
          <span className="text-gray-500 font-mono text-[11px] shrink-0 w-28 pt-0.5 tabular-nums">
            {formatSec(c.start ?? c.time_sec ?? c.t ?? '')}
            {c.end != null ? ` – ${formatSec(c.end)}` : ''}
          </span>
          <span className="text-sm text-gray-100 leading-relaxed">
            {c.text || c.content || String(c)}
          </span>
        </li>
      ))}
    </ul>
  );
}

function TranscriptParagraphs({ text }: { text: string }) {
  const paras = splitTranscriptParagraphs(text);
  return (
    <div className="max-h-80 overflow-y-auto space-y-2.5 pr-1">
      {paras.map((p, i) => (
        <p key={i} className="text-sm text-gray-100 leading-relaxed">
          {p}
        </p>
      ))}
    </div>
  );
}

function SubtitleTimelineView({ value }: { value: any }) {
  if (value == null || value === '') return <p className="text-sm text-gray-500">无内容</p>;

  if (isPlainObject(value)) {
    const asrSegs =
      value.transcript_segments ||
      (Array.isArray(value.segments) && value.segments[0]?.text != null ? value.segments : null);
    const asrText = value.transcript || value.transcript_text || value.text;
    if (Array.isArray(asrSegs) && asrSegs.length) {
      return <CueList items={asrSegs} />;
    }
    if (typeof asrText === 'string' && asrText.trim() && value.has_transcript !== false) {
      if (value.asr_enabled || value.asr_method || value.has_transcript || 'transcript' in value) {
        return <TranscriptParagraphs text={asrText} />;
      }
    }
    if (value.no_subtitle_track || value.has_subtitle_track === false || value.status === 'degraded') {
      if (value.asr_enabled || value.asr_method || 'transcript' in value) {
        return (
          <div className="text-sm text-amber-300/90 space-y-1">
            <p>{value.error_message || '未识别到可用语音转写'}</p>
            <p className="text-xs text-gray-500">请确认视频含清晰人声；可稍后重试分析</p>
          </div>
        );
      }
      return (
        <div className="text-sm text-amber-300/90 space-y-1">
          <p>{value.error_message || '未检测到内嵌字幕轨道'}</p>
          <p className="text-xs text-gray-500">软字幕提取失败时仍可查看下方「语音转写」</p>
        </div>
      );
    }
    const cues = value.cues || value.segments || value.lines || value.subtitles;
    if (Array.isArray(cues) && cues.length) {
      return <CueList items={cues} maxH="max-h-64" />;
    }
    if (typeof value.text === 'string') {
      return <TranscriptParagraphs text={value.text} />;
    }
  }
  if (typeof value === 'string') {
    return <TranscriptParagraphs text={value} />;
  }
  if (Array.isArray(value)) {
    if (value[0] && typeof value[0] === 'object' && (value[0].text || value[0].content)) {
      return <CueList items={value} />;
    }
    return <TimelineView value={value} />;
  }
  return <KeyValueView value={value} />;
}

export const ResultDashboard: React.FC<Props> = ({ config, onExecute, skill, stageInput }) => {
  const [data, setData] = useState<Record<string, any> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const inputKey = JSON.stringify({ ...(config.input || {}), ...(stageInput || {}) });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setLoading(true);
        setError('');
        const params = { ...(config.input || {}), ...(stageInput || {}) };
        for (const [k, v] of Object.entries(params)) {
          if (typeof v === 'string' && /^\{\{.+\}\}$/.test(v)) delete (params as any)[k];
        }
        const hasRef =
          Boolean(params.task_id) ||
          Boolean(params.video_path) ||
          Boolean(params.file_path) ||
          Boolean(params.local_path) ||
          Boolean(params.path);
        if (!hasRef) {
          if (!cancelled) {
            setError('缺少任务引用（task_id / video_path）。请从上传或 URL 步骤重新开始。');
            setLoading(false);
          }
          return;
        }
        const res = await onExecute(skill, params);
        if (cancelled) return;
        if (res?.ok === false || res?.error) {
          setError(String(res?.error || res?.detail || res?.message || '加载失败'));
          setLoading(false);
          return;
        }
        let nested =
          res?.result && typeof res.result === 'object' && !Array.isArray(res.result)
            ? res.result
            : {};
        if ((!nested || Object.keys(nested).length === 0) && typeof res?.reply === 'string') {
          try {
            const parsedReply = JSON.parse(res.reply);
            if (parsedReply && typeof parsedReply === 'object' && !Array.isArray(parsedReply)) {
              nested = parsedReply;
            }
          } catch {
            /* reply may be plain text */
          }
        }
        const parsed =
          typeof res === 'string'
            ? (() => {
                try {
                  return JSON.parse(res);
                } catch {
                  return { reply: res };
                }
              })()
            : { ...nested, ...res, ...nested };
        const {
          status: _s,
          ok: _o,
          detail: _d,
          message: _m,
          mode: _mode,
          agent: _a,
          reply: _r,
          platform_effects: _pe,
          skill: _sk,
          ...rest
        } = parsed as Record<string, any>;
        const business =
          Object.keys(nested).length > 0
            ? nested
            : Object.keys(rest).length > 0
              ? rest
              : parsed;
        setData(business);
      } catch (e: any) {
        if (!cancelled) setError(e?.message || '加载失败');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- inputKey fingerprints config/stageInput
  }, [skill, inputKey, onExecute]);

  if (loading)
    return (
      <Card className="p-6">
        <div className="text-sm text-gray-400">加载结果中...</div>
      </Card>
    );
  if (error)
    return (
      <Card className="p-6">
        <div className="text-sm text-red-400">{error}</div>
      </Card>
    );
  if (!data) return null;

  const sections =
    config.sections ||
    Object.keys(data).map((k) => ({ key: k, label: k, type: 'text_block' as const }));

  const renderSection = (s: SectionConfig, val: any) => {
    if (val === undefined) {
      return <p className="text-sm text-gray-500">无此字段</p>;
    }
    switch (s.type) {
      case 'tag_cloud': {
        const tags = Array.isArray(val)
          ? val
          : typeof val === 'string'
            ? val.split(',').map((t) => t.trim())
            : [];
        return (
          <div className="flex flex-wrap gap-2">
            {tags.map((t: string, i: number) => (
              <Badge key={i} variant="default" className="text-xs">
                {String(t)}
              </Badge>
            ))}
          </div>
        );
      }
      case 'text_block':
        return (
          <p className="text-sm text-gray-300 whitespace-pre-wrap">
            {typeof val === 'string' ? val : JSON.stringify(val, null, 2)}
          </p>
        );
      case 'markdown':
        return (
          <div
            className="text-sm text-gray-300 prose prose-invert max-w-none"
            dangerouslySetInnerHTML={{
              __html: String(val ?? '').replace(/\n/g, '<br/>'),
            }}
          />
        );
      case 'table': {
        const rows = Array.isArray(val) ? val : [];
        const cols = rows.length > 0 && isPlainObject(rows[0]) ? Object.keys(rows[0]) : [];
        return (
          <table className="w-full text-sm">
            <thead>
              <tr>
                {cols.map((c) => (
                  <th key={c} className="text-left text-gray-400 py-1">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r: any, i: number) => (
                <tr key={i}>
                  {cols.map((c) => (
                    <td key={c} className="py-1 text-gray-300">
                      {String(r[c] ?? '')}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        );
      }
      case 'key_value':
        return <KeyValueView value={val} />;
      case 'timeline':
        return <TimelineView value={val} />;
      case 'image_timeline':
        return <ImageTimelineView value={val} />;
      case 'subtitle_timeline':
        return <SubtitleTimelineView value={val} />;
      default:
        // Unknown type from generated app_page — still try smart render
        if (Array.isArray(val)) {
          if (val[0] && (val[0].local_path || val[0].url || val[0].time_sec != null)) {
            return <ImageTimelineView value={val} />;
          }
          return <TimelineView value={val} />;
        }
        if (isPlainObject(val)) return <KeyValueView value={val} />;
        return <p className="text-sm text-gray-300">{String(val)}</p>;
    }
  };

  return (
    <Card className="p-5 sm:p-6">
      <h2 className="text-lg font-semibold mb-5 text-gray-100">分析结果</h2>
      <div className="space-y-4">
        {sections.map((s) => {
          const val = pickValue(data, s.key);
          return (
            <section
              key={s.key}
              className="rounded-xl border border-dark-border/80 bg-dark-bg/30 px-4 py-3.5"
            >
              <h3 className="text-sm font-medium text-gray-300 mb-3">{s.label}</h3>
              {renderSection(s, val)}
            </section>
          );
        })}
      </div>
      <div className="flex gap-2 mt-5 pt-3 border-t border-dark-border">
        <button
          type="button"
          onClick={() => navigator.clipboard.writeText(JSON.stringify(data, null, 2))}
          className="text-xs text-gray-500 hover:text-gray-300 flex items-center gap-1"
        >
          <Copy className="w-3 h-3" />
          复制 JSON
        </button>
      </div>
    </Card>
  );
};
