/**
 * Agent-eval framework: Layer1 dims+specialties / Layer2 methods / Layer3 conclusions.
 * Honest: coverage status ≠ sufficiency for publish.
 */
import EvalCollapsibleBanner from './EvalCollapsibleBanner';
import {
  EVAL_AGENT_CONCLUSION_NOTES,
  EVAL_AGENT_DIMENSIONS,
  EVAL_AGENT_META,
  EVAL_AGENT_METHOD_NOTES,
  EVAL_AGENT_SPECIALTY_SLICES,
  coverageLabel,
  type EvalAgentDimension,
} from './evalAgentFramework';
import { RUNTIME_TIER_TABLE } from './examRuntimeTier';
import { ListChecks } from 'lucide-react';

function DimTable({ rows, caption }: { rows: EvalAgentDimension[]; caption: string }) {
  return (
    <div className="overflow-x-auto rounded border border-violet-800/40">
      <div className="px-2 py-1 text-[11px] text-violet-300/80 bg-violet-950/40 border-b border-violet-900/50">
        {caption}
      </div>
      <table className="w-full text-left text-[11px] sm:text-xs">
        <thead className="bg-violet-950/50 text-violet-200/80">
          <tr>
            <th className="px-2 py-1.5 font-medium">维度</th>
            <th className="px-2 py-1.5 font-medium">评什么</th>
            <th className="px-2 py-1.5 font-medium">本产品现状（覆盖，非充分性证明）</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((d) => (
            <tr key={d.id} className="border-t border-violet-900/50 align-top">
              <td className="px-2 py-1.5 whitespace-nowrap">
                <div className="font-medium text-violet-50">{d.title}</div>
                <div className="text-violet-300/70 mt-0.5">{coverageLabel(d.coverage)}</div>
              </td>
              <td className="px-2 py-1.5 text-violet-100/80">
                <div>{d.asks}</div>
                <div className="text-violet-300/60 mt-0.5">例：{d.examples}</div>
              </td>
              <td className="px-2 py-1.5 text-violet-200/75">{d.today}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function EvalAgentFrameworkPanel() {
  return (
    <EvalCollapsibleBanner
      storageKey="eval.agent.framework.open"
      testId="eval-agent-framework"
      defaultOpen={false}
      toneClassName="border-violet-800/40 bg-violet-950/15 text-violet-50"
      icon={<ListChecks className="w-5 h-5 text-violet-300" />}
      summary={
        <>
          评测框架三层 · 维度 / 方法 / 结论
          <span className="font-normal text-violet-200/60 text-xs sm:text-sm ml-2">
            8 维较全 · ≠ 发布方案已完整 · ≠ 下方工程分已全覆盖
          </span>
        </>
      }
    >
      <div className="space-y-3 text-xs sm:text-sm text-violet-100/90 leading-relaxed">
        <p>
          评测对象是「模型 + Prompt + 工具/Skill + 记忆 + 环境 + 工作流」，不是只看最终一句话。
          下方 Central 工程分只是其中一部分；管道自检更不是成果物评测。
        </p>

        <div
          className="rounded border border-amber-700/40 bg-amber-950/25 px-3 py-2 text-[11px] sm:text-xs text-amber-100/90 space-y-1"
          data-testid="eval-agent-framework-meta"
        >
          <p>{EVAL_AGENT_META.checklistOk}</p>
          <p>{EVAL_AGENT_META.schemeIncomplete}</p>
        </div>

        <div>
          <div className="text-violet-200/80 font-medium mb-1">第 1 层 · 评测维度</div>
          <DimTable rows={EVAL_AGENT_DIMENSIONS} caption="核心 8 维（讨论「评什么」）" />
          <div className="mt-2">
            <DimTable
              rows={EVAL_AGENT_SPECIALTY_SLICES}
              caption="专项切片（可执行发布方案还需补足）"
            />
          </div>
        </div>

        <div data-testid="eval-runtime-tier-table">
          <div className="text-violet-200/80 font-medium mb-1">评测深度 → 运行时（runtime_tier）</div>
          <p className="text-[11px] text-violet-300/70 mb-1">
            契约见 docs/architecture/plans/eval-exam-runtime-tiers.md · accuracy_claim 与 runtime 正交
          </p>
          <div className="overflow-x-auto rounded border border-violet-800/40">
            <table className="w-full text-left text-[11px] sm:text-xs">
              <thead className="bg-violet-950/50 text-violet-200/80">
                <tr>
                  <th className="px-2 py-1.5 font-medium">tier</th>
                  <th className="px-2 py-1.5 font-medium">用途</th>
                  <th className="px-2 py-1.5 font-medium">诚实边界</th>
                </tr>
              </thead>
              <tbody>
                {RUNTIME_TIER_TABLE.map((r) => (
                  <tr key={r.id} className="border-t border-violet-900/50 align-top">
                    <td className="px-2 py-1.5 font-mono text-violet-50 whitespace-nowrap">{r.id}</td>
                    <td className="px-2 py-1.5 text-violet-100/80">{r.use}</td>
                    <td className="px-2 py-1.5 text-violet-200/75">{r.boundary}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div>
          <div className="text-violet-200/80 font-medium mb-1">第 2 层 · 评测方法</div>
          <ul className="list-disc pl-5 space-y-0.5 text-violet-100/80">
            {EVAL_AGENT_METHOD_NOTES.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </div>

        <div>
          <div className="text-violet-200/80 font-medium mb-1">第 3 层 · 评测结论（发布决策用）</div>
          <ul className="list-disc pl-5 space-y-0.5 text-violet-100/80">
            {EVAL_AGENT_CONCLUSION_NOTES.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </div>

        <p className="text-amber-100/80">
          落地顺序：先夯实任务结果 / 事实证据 / 工具轨迹 / 安全硬门槛（含拒绝校准）/ 成本与失败归因，
          再扩记忆长程、评测集可靠性与线上抽样；安全关键失败必须能 veto，不能只靠总分扣分。
        </p>
      </div>
    </EvalCollapsibleBanner>
  );
}
