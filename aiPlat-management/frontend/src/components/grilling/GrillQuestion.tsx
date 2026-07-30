import { useState } from 'react';
import type { GrillQuestion as GrillQuestionType } from '../../hooks/useGrilling';

interface Props {
  question: GrillQuestionType;
  onAnswer: (answer: string) => void;
  onSkip?: () => void;
  loading?: boolean;
  currentRound: number;
  totalRounds: number;
}

const OPTION_LABELS = ['A', 'B', 'C', 'D', 'E'];

export default function GrillQuestion({ question, onAnswer, onSkip, loading, currentRound, totalRounds }: Props) {
  const [custom, setCustom] = useState('');

  const handleOption = (option: string) => {
    onAnswer(option);
  };

  const handleCustom = () => {
    if (custom.trim()) {
      onAnswer(custom.trim());
      setCustom('');
    }
  };

  return (
    <div className="space-y-4">
      {/* Progress bar */}
      <div className="flex items-center gap-2">
        <span className="text-xs text-gray-500">
          第 {currentRound}/{totalRounds} 轮
        </span>
        <div className="flex-1 h-1.5 bg-gray-800 rounded-full overflow-hidden">
          <div
            className="h-full bg-blue-500 rounded-full transition-all duration-300"
            style={{ width: `${(currentRound / totalRounds) * 100}%` }}
          />
        </div>
        {question.required && (
          <span className="text-xs text-red-400 px-1.5 py-0.5 rounded bg-red-900/30">必填</span>
        )}
      </div>

      {/* Question */}
      <div className="text-gray-100 text-sm font-medium">
        ❓ {question.text}
      </div>

      {/* Options */}
      {question.options.length > 0 && (
        <div className="space-y-1.5">
          {question.options.map((opt, idx) => (
            <button
              key={opt}
              onClick={() => handleOption(opt)}
              disabled={loading}
              className="w-full text-left px-3 py-2 rounded border border-gray-700/50 bg-gray-800/50 hover:bg-blue-900/30 hover:border-blue-700/50 text-gray-300 text-sm transition-colors disabled:opacity-50 flex items-center gap-2"
            >
              <span className="text-xs font-mono text-blue-400 bg-blue-900/30 px-1.5 py-0.5 rounded">
                {OPTION_LABELS[idx]}
              </span>
              {opt}
            </button>
          ))}
        </div>
      )}

      {/* Custom answer input */}
      <div className="flex gap-2">
        <input
          type="text"
          value={custom}
          onChange={(e) => setCustom(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleCustom()}
          placeholder="或输入自定义答案..."
          className="flex-1 px-3 py-2 rounded border border-gray-700/50 bg-gray-800/50 text-gray-300 text-sm placeholder-gray-600 focus:outline-none focus:border-blue-700/50"
          disabled={loading}
        />
        <button
          onClick={handleCustom}
          disabled={loading || !custom.trim()}
          className="px-3 py-2 rounded bg-blue-900/30 border border-blue-700/50 text-blue-400 text-sm hover:bg-blue-900/50 disabled:opacity-30 disabled:cursor-not-allowed"
        >
          提交
        </button>
      </div>

      {/* Skip */}
      {!question.required && onSkip && (
        <button
          onClick={onSkip}
          disabled={loading}
          className="text-xs text-gray-500 hover:text-gray-400 disabled:opacity-30"
        >
          跳过此问 →
        </button>
      )}
    </div>
  );
}
