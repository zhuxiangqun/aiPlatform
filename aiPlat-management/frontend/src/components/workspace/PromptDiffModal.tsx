import React, { useState } from 'react';
import { Button, Modal, toast } from '../ui';
import { promptOptimizeApi } from '../../services';

const wordDiff = (oldStr: string, newStr: string) => {
  const oldWords = oldStr.split(/(\s+)/);
  const newWords = newStr.split(/(\s+)/);
  const m = oldWords.length, n = newWords.length;
  const dp: number[][] = Array.from({ length: m + 1 }, () => Array(n + 1).fill(0));
  for (let i = 1; i <= m; i++)
    for (let j = 1; j <= n; j++)
      dp[i][j] = oldWords[i - 1] === newWords[j - 1] ? dp[i - 1][j - 1] + 1 : Math.max(dp[i - 1][j], dp[i][j - 1]);
  const result: Array<{ text: string; type: 'same' | 'add' | 'del' }> = [];
  let i = m, j = n;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && oldWords[i - 1] === newWords[j - 1]) {
      result.unshift({ text: oldWords[i - 1], type: 'same' });
      i--; j--;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      result.unshift({ text: newWords[j - 1], type: 'add' });
      j--;
    } else {
      result.unshift({ text: oldWords[i - 1], type: 'del' });
      i--;
    }
  }
  return result;
};

interface Props {
  open: boolean;
  title?: string;
  original: string;
  onClose: () => void;
  onApply: (optimized: string) => void;
}

const PromptDiffModal: React.FC<Props> = ({ open, title = 'AI 优化', original, onClose, onApply }) => {
  const [loading, setLoading] = useState(false);
  const [optimized, setOptimized] = useState('');
  const [changes, setChanges] = useState<string[]>([]);
  const [scoreBefore, setScoreBefore] = useState(0);
  const [scoreAfter, setScoreAfter] = useState(0);

  // Auto-optimize when modal opens
  React.useEffect(() => {
    if (!open || !original) return;
    setLoading(true);
    setOptimized('');
    setChanges([]);
    (async () => {
      try {
        const r = await promptOptimizeApi.run({ prompt: original, model: 'deepseek-chat' });
        const data = r as any;
        setOptimized(data.optimized || '');
        setChanges(data.changes || []);
        setScoreBefore(data.score_before || 0);
        setScoreAfter(data.score_after || 0);
      } catch (e: any) {
        toast.error('优化失败', e?.message);
        onClose();
      } finally {
        setLoading(false);
      }
    })();
  }, [open, original]);

  const diffs = original && optimized ? wordDiff(original, optimized) : [];

  const handleApply = () => {
    if (!optimized) return;
    onApply(optimized);
    onClose();
  };

  return (
    <Modal open={open} onClose={onClose} title={title} width={1100}>
      <div className="flex flex-col gap-4" style={{ minHeight: '400px' }}>
        {loading ? (
          <div className="flex-1 flex items-center justify-center text-gray-400">
            <div className="text-center">
              <div className="animate-spin text-3xl mb-3">⚙</div>
              <p className="text-sm">AI 分析中...</p>
              <p className="text-[10px] text-gray-600 mt-1">正在理解上下文并生成优化建议</p>
            </div>
          </div>
        ) : (
          <>
            {/* Score bar */}
            {scoreAfter > 0 && (
              <div className="flex items-center gap-4 bg-dark-bg rounded-lg p-2.5">
                <div className="flex-1">
                  <span className="text-[10px] text-gray-500">优化前</span>
                  <div className="flex items-center gap-2">
                    <div className="flex-1 bg-gray-800 rounded-full h-1.5">
                      <div className="bg-yellow-500 h-1.5 rounded-full" style={{ width: `${scoreBefore * 10}%` }} />
                    </div>
                    <span className="text-xs text-yellow-400">{scoreBefore}/10</span>
                  </div>
                </div>
                <span className="text-gray-600">→</span>
                <div className="flex-1">
                  <span className="text-[10px] text-gray-500">优化后</span>
                  <div className="flex items-center gap-2">
                    <div className="flex-1 bg-gray-800 rounded-full h-1.5">
                      <div className="bg-green-500 h-1.5 rounded-full" style={{ width: `${scoreAfter * 10}%` }} />
                    </div>
                    <span className="text-xs text-green-400">{scoreAfter}/10</span>
                  </div>
                </div>
              </div>
            )}

            {/* Dual-panel diff */}
            <div className="grid grid-cols-2 gap-4 flex-1 min-h-0">
              <div className="flex flex-col min-h-0">
                <div className="text-xs text-gray-400 uppercase tracking-wider font-medium mb-1.5">原始版本</div>
                <div className="flex-1 overflow-y-auto bg-dark-bg border border-dark-border rounded-lg p-3 text-xs leading-relaxed max-h-[350px]">
                  {diffs.map((d, di) => (
                    <span key={di} className={
                      d.type === 'add' ? 'hidden'
                      : d.type === 'del' ? 'bg-red-500/20 text-red-300 line-through rounded-sm px-0.5'
                      : 'text-gray-300'
                    }>{d.text}</span>
                  ))}
                </div>
              </div>
              <div className="flex flex-col min-h-0">
                <div className="text-xs text-green-400 uppercase tracking-wider font-medium mb-1.5">优化版本</div>
                <div className="flex-1 overflow-y-auto bg-dark-bg border border-dark-border rounded-lg p-3 text-xs leading-relaxed max-h-[350px]">
                  {diffs.map((d, di) => (
                    <span key={di} className={
                      d.type === 'del' ? 'hidden'
                      : d.type === 'add' ? 'bg-green-500/20 text-green-300 rounded-sm px-0.5'
                      : 'text-gray-300'
                    }>{d.text}</span>
                  ))}
                </div>
              </div>
            </div>

            {/* Changes list */}
            {changes.length > 0 && (
              <div className="text-[11px] space-y-0.5 bg-dark-bg rounded-lg p-2.5">
                <div className="text-[10px] text-gray-500 mb-1">改动说明</div>
                {changes.map((c: string, ci: number) => (
                  <div key={ci} className="text-gray-400 flex items-start gap-1.5">
                    <span className="text-green-400 shrink-0">✓</span>
                    <span>{c}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Actions */}
            <div className="flex justify-end gap-2 pt-2 border-t border-dark-border">
              <Button variant="ghost" onClick={onClose}>放弃</Button>
              <Button onClick={handleApply} disabled={!optimized} className="bg-green-600 hover:bg-green-700">应用优化版本</Button>
            </div>
          </>
        )}
      </div>
    </Modal>
  );
};

export default PromptDiffModal;
