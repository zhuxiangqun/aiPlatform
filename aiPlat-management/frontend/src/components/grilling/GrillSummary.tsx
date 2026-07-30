interface AnswerItem {
  id: string;
  label: string;
  answer: string;
}

interface Props {
  answers: AnswerItem[];
  missedRequired?: number;
  open?: boolean;
  onToggle?: () => void;
}

export default function GrillSummary({ answers, missedRequired, open = true, onToggle }: Props) {
  if (!open) {
    return (
      <button
        onClick={onToggle}
        className="w-full text-left px-3 py-2 text-xs text-gray-500 hover:text-gray-400 flex items-center gap-1"
      >
        <span>{answers.length > 0 ? '▶' : '◆'} 澄清摘要 ({answers.length} 项)</span>
      </button>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-gray-400">
          已澄清 ({answers.length} 项)
        </span>
        {onToggle && (
          <button onClick={onToggle} className="text-xs text-gray-600 hover:text-gray-400">
            ▼ 收起
          </button>
        )}
      </div>
      <div className="space-y-1">
        {answers.map((a) => (
          <div key={a.id} className="flex items-start gap-2 text-xs">
            <span className="text-green-400 mt-0.5 shrink-0">&#10003;</span>
            <span className="text-gray-500 shrink-0">{a.label}:</span>
            <span className="text-gray-300 truncate" title={a.answer}>{a.answer}</span>
          </div>
        ))}
      </div>
      {missedRequired != null && missedRequired > 0 && (
        <div className="text-xs text-yellow-400">
          ⚠ {missedRequired} 个必填项未确认
        </div>
      )}
    </div>
  );
}
