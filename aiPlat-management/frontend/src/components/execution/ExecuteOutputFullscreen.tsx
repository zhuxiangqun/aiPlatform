import React, { useEffect, useMemo, useState } from 'react';
import { Button } from '../ui';
import StructuredSkillOutput, { FileDeliveryOverview } from './StructuredSkillOutput';
import { extractCodingDeliveryText, parseFileDelivery, persistRootFromPayload } from './fileDelivery';
import { ArtifactDownloadBar } from './artifactDownloads';

type TabKey = 'files' | 'plan' | 'full';

type Props = {
  open: boolean;
  title?: string;
  text: string;
  raw?: unknown;
  schema?: Record<string, unknown> | null;
  onClose: () => void;
  /** Optional: jump to execution-flow fullscreen. */
  onOpenFlow?: () => void;
};

/**
 * Full-viewport deliverable viewer — coding ## FILE tabs fill the screen;
 * planning prose and raw text are separate tabs so nothing is truncated by the modal card.
 */
const ExecuteOutputFullscreen: React.FC<Props> = ({
  open,
  title = '执行产出',
  text,
  raw,
  schema,
  onClose,
  onOpenFlow,
}) => {
  const codingText = useMemo(() => {
    const extracted = extractCodingDeliveryText(text, raw);
    return extracted || text;
  }, [text, raw]);
  const persistRoot = useMemo(() => persistRootFromPayload(raw), [raw]);
  const parsed = useMemo(() => parseFileDelivery(codingText), [codingText]);
  const hasFiles = !!(parsed && parsed.files.length > 0);
  const showUnwrapped = codingText.trim() !== String(text || '').trim();
  const [tab, setTab] = useState<TabKey>('files');

  useEffect(() => {
    if (!open) return;
    setTab(hasFiles ? 'files' : 'full');
  }, [open, hasFiles, codingText.slice(0, 80)]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  const tabs: { key: TabKey; label: string; show: boolean }[] = [
    { key: 'files', label: hasFiles ? `交付文件 (${parsed!.files.length})` : '交付文件', show: hasFiles },
    { key: 'plan', label: '规划 / 分析', show: !!(parsed?.overview) },
    { key: 'full', label: '完整原文', show: true },
  ];

  return (
    <div className="fixed inset-0 z-[70] bg-dark-bg flex flex-col">
      <div className="h-11 flex items-center justify-between px-4 border-b border-dark-border bg-dark-card flex-shrink-0 gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <span className="text-sm font-medium text-gray-200 truncate">📄 {title}</span>
          <div className="flex items-center gap-1">
            {tabs
              .filter((t) => t.show)
              .map((t) => (
                <button
                  key={t.key}
                  type="button"
                  onClick={() => setTab(t.key)}
                  className={
                    tab === t.key
                      ? 'px-2.5 py-1 text-[11px] font-medium text-white bg-dark-bg border border-dark-border rounded-md'
                      : 'px-2.5 py-1 text-[11px] text-gray-400 hover:text-gray-200 rounded-md'
                  }
                >
                  {t.label}
                </button>
              ))}
          </div>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {onOpenFlow ? (
            <Button variant="secondary" size="sm" onClick={onOpenFlow}>
              ▶ 执行流程
            </Button>
          ) : null}
          <Button variant="secondary" onClick={onClose}>
            ✕ 关闭
          </Button>
        </div>
      </div>

      <div className="flex-1 min-h-0 flex flex-col p-3 gap-2">
        <ArtifactDownloadBar raw={raw} />
        <div className="flex-1 min-h-0 rounded-lg border border-dark-border bg-dark-card/40 p-3 overflow-hidden flex flex-col">
          {tab === 'files' && hasFiles ? (
            <FileDeliveryOverview text={codingText} layout="fill" persistRoot={persistRoot} />
          ) : null}
          {tab === 'plan' && parsed?.overview ? (
            <div className="h-full min-h-0 overflow-auto">
              <div className="text-[11px] font-medium text-sky-300/90 mb-2">
                规划 / 分析（非最终代码）
              </div>
              <pre className="text-[12px] text-gray-200 whitespace-pre-wrap break-words leading-relaxed font-sans">
                {parsed.overview}
              </pre>
            </div>
          ) : null}
          {tab === 'full' ? (
            <div className="h-full min-h-0 overflow-auto">
              {hasFiles || showUnwrapped ? (
                <pre className="text-[12px] text-gray-200 font-mono whitespace-pre leading-relaxed">
                  {codingText}
                </pre>
              ) : (
                <StructuredSkillOutput text={codingText || text} raw={raw} schema={schema} />
              )}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
};

export default ExecuteOutputFullscreen;
