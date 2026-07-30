import { useState } from 'react';
import { useGrilling } from '../../hooks/useGrilling';
import GrillQuestion from './GrillQuestion';
import GrillSummary from './GrillSummary';

type GrillMode = 'modal' | 'sidebar' | 'inline';

interface Props {
  mode?: GrillMode;
  entryPoint: string;
  domainId?: string;
  context?: Record<string, unknown>;
  onComplete?: (output: Record<string, unknown>) => void;
  onClose?: () => void;
  title?: string;
}

export default function GrillPanel({
  mode = 'modal',
  entryPoint,
  domainId = '',
  context,
  onComplete,
  onClose,
  title,
}: Props) {
  const { session, loading, answers, answer, skip, finalize } = useGrilling(entryPoint, domainId);
  const [summaryOpen, setSummaryOpen] = useState(true);
  const [done, setDone] = useState(false);

  const handleAnswer = async (ans: string) => {
    const res = await answer(ans);
    if (res?.status === 'completed') {
      setDone(true);
    }
  };

  const handleFinalize = async () => {
    const res = await finalize();
    if (res?.status === 'completed') {
      onComplete?.({
        answers: res.answers_flat,
        summary: res.summary_markdown,
        conversation: (res as Record<string, unknown>).conversation,
      });
      setDone(true);
    }
  };

  const displayTitle = title || '需求澄清';

  // Completed state
  if (done || session?.status === 'completed') {
    return (
      <div className="space-y-4 p-4">
        <div className="text-center space-y-2">
          <div className="text-2xl">&#10003;</div>
          <div className="text-sm text-gray-300 font-medium">澄清完成</div>
          <div className="text-xs text-gray-500">
            {session?.answered != null ? `${session.answered} 个维度已确认` : ''}
          </div>
        </div>
        {session?.answers_flat && (
          <GrillSummary
            answers={Object.entries(session.answers_flat).map(([label, answer]) => ({
              id: label, label, answer: String(answer),
            }))}
          />
        )}
        <button
          onClick={() => onClose?.()}
          className="w-full py-2 rounded bg-blue-900/30 border border-blue-700/50 text-blue-400 text-sm hover:bg-blue-900/50"
        >
          关闭
        </button>
      </div>
    );
  }

  // No dimensions
  if (session?.status === 'no_dimensions') {
    return (
      <div className="p-4 text-center text-sm text-gray-500">
        {session.message || '无需额外澄清'}
      </div>
    );
  }

  // Loading / asking state
  const q = session?.question;
  const progress = session?.progress;

  const containerClasses = mode === 'sidebar'
    ? 'h-full flex flex-col bg-gray-900 border-l border-gray-800'
    : mode === 'inline'
    ? 'bg-gray-900 border border-gray-800 rounded-lg'
    : 'bg-gray-900 border border-gray-800 rounded-lg max-w-lg w-full'; // modal

  const content = (
    <div className={containerClasses}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-gray-200">📋 {displayTitle}</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleFinalize}
            disabled={loading}
            className="text-xs px-2 py-1 rounded border border-green-800/50 text-green-400 bg-green-900/20 hover:bg-green-900/30 disabled:opacity-30"
          >
            可以开始了
          </button>
          {onClose && (
            <button onClick={onClose} className="text-gray-500 hover:text-gray-400 text-sm">
              ✕
            </button>
          )}
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-auto p-4 space-y-4">
        {q && (
          <GrillQuestion
            question={q}
            onAnswer={handleAnswer}
            onSkip={() => skip()}
            loading={loading}
            currentRound={progress?.current || 1}
            totalRounds={progress?.total || 5}
          />
        )}

        {/* Summary section */}
        <div className="border-t border-gray-800 pt-3">
          <GrillSummary
            answers={answers}
            open={summaryOpen}
            onToggle={() => setSummaryOpen(!summaryOpen)}
          />
        </div>
      </div>
    </div>
  );

  // Modal mode: backdrop + centered
  if (mode === 'modal' && !session?.question) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
        <div className="text-gray-400 text-sm">加载中...</div>
      </div>
    );
  }

  if (mode === 'modal') {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
        {content}
      </div>
    );
  }

  return content;
}
