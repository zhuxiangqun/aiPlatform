/**
 * 评测 Agent — 成果物评测入口：选用例集 → 预检 / 正式评测；
 * 下方历史仅跟当前所选 Agent + 命名工作区（非全站评分榜）。
 * 管道自检（Code-review / Session / Skill / suites）不在本页。
 */
import { useState } from 'react';
import DiagnosticsEvalDashboard from '../Diagnostics/EvalDashboard';
import EvalAgentExamPanel from './EvalAgentExamPanel';
import EvalAgentFrameworkPanel from './EvalAgentFrameworkPanel';
import EvalCollapsibleBanner from './EvalCollapsibleBanner';
import EvalExternalExamPanel from './EvalExternalExamPanel';
import EvalNamedWorkspacePicker from './EvalNamedWorkspacePicker';

type Props = {
  tenantId?: string;
};

type ObjectMode = 'local' | 'external';

export default function EvalAgentsPanel(_props: Props) {
  const [examAgent, setExamAgent] = useState('');
  const [examSetId, setExamSetId] = useState('default/normal');
  const [dashKey, setDashKey] = useState(0);
  const [wsKey, setWsKey] = useState(0);
  const [mode, setMode] = useState<ObjectMode>('local');

  const onWorkspaceChange = () => {
    setExamAgent('');
    setDashKey((k) => k + 1);
    setWsKey((k) => k + 1);
  };

  return (
    <div className="space-y-3" data-testid="eval-agents-panel">
      <p
        className="rounded-lg border border-violet-700/40 bg-violet-950/20 px-3 py-2 text-xs text-violet-100/90"
        data-testid="eval-agents-object"
      >
        <strong className="text-violet-50">这里评的是 Agent 本身</strong>
        （本机或外部对话目标）。先选对象，再单套题或连跑冒烟看哪里没过。得分是体检参考，不能当「准确率 / 已可上线」证明。管道联调请到「验管道」。
      </p>
      <EvalNamedWorkspacePicker onChange={() => onWorkspaceChange()} />
      <div className="flex flex-wrap gap-2" data-testid="eval-agents-mode">
        <button
          type="button"
          className={`px-3 py-1.5 rounded text-xs border ${
            mode === 'local'
              ? 'border-violet-500/70 bg-violet-950/40 text-violet-50'
              : 'border-gray-600 text-gray-300'
          }`}
          onClick={() => setMode('local')}
        >
          本机 Agent
        </button>
        <button
          type="button"
          className={`px-3 py-1.5 rounded text-xs border ${
            mode === 'external'
              ? 'border-sky-500/70 bg-sky-950/40 text-sky-50'
              : 'border-gray-600 text-gray-300'
          }`}
          onClick={() => setMode('external')}
        >
          外部目标
        </button>
      </div>
      <EvalAgentFrameworkPanel />
      {mode === 'local' ? (
        <EvalAgentExamPanel
          key={`exam-${wsKey}`}
          agentId={examAgent.startsWith('ext:') ? '' : examAgent}
          onAgentChange={setExamAgent}
          onSetChange={setExamSetId}
          onExamDone={() => setDashKey((k) => k + 1)}
        />
      ) : (
        <EvalExternalExamPanel
          key={`ext-${wsKey}`}
          onAgentChange={setExamAgent}
          onSetChange={setExamSetId}
          onExamDone={() => setDashKey((k) => k + 1)}
        />
      )}
      <EvalCollapsibleBanner
        storageKey="aiplat.eval.agents.historyOpen"
        summary={
          examAgent
            ? `评测历史 · ${examAgent}${examSetId ? ` · ${examSetId}` : ''}（点开看趋势与明细）`
            : '评测历史（选 Agent 后展开；默认收起）'
        }
        toneClassName="border-gray-700/80 bg-gray-900/40 text-gray-200"
        testId="eval-agents-history"
        defaultOpen={false}
        bodyClassName="mt-3 space-y-0"
      >
        <DiagnosticsEvalDashboard
          key={`dash-${dashKey}-${wsKey}`}
          embedded
          historyOnly
          initialAgentId={examAgent || undefined}
          initialSetId={examSetId || undefined}
        />
      </EvalCollapsibleBanner>
    </div>
  );
}
