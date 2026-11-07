/**
 * Per-tab plain-language explainer — collapsible, default collapsed.
 */
import { HelpCircle } from 'lucide-react';
import EvalCollapsibleBanner from './EvalCollapsibleBanner';
import { EVAL_TAB_GUIDES } from './evalTabGuides';

type Props = {
  tabId: string;
};

export default function EvalTabGuide({ tabId }: Props) {
  const g = EVAL_TAB_GUIDES[tabId];
  if (!g) return null;

  return (
    <EvalCollapsibleBanner
      storageKey={`eval.tabguide.${tabId}.open`}
      testId="eval-tab-guide"
      defaultOpen={false}
      toneClassName="border-slate-600/50 bg-slate-900/40 text-slate-100"
      icon={<HelpCircle className="w-5 h-5 text-slate-300" />}
      summary={
        <>
          这是什么 · {g.title}
          <span className="font-normal text-slate-400 text-xs sm:text-sm ml-2">
            点击展开说明
          </span>
        </>
      }
    >
      <div className="space-y-2 text-xs sm:text-sm text-slate-300/95 leading-relaxed">
        <p>
          <span className="text-slate-400">是什么：</span>
          <span className="text-slate-100">{g.what}</span>
        </p>
        {g.why ? (
          <p>
            <span className="text-slate-400">为什么要：</span>
            <span className="text-slate-100">{g.why}</span>
          </p>
        ) : null}
        <p>
          <span className="text-slate-400">怎么用：</span>
          <span className="text-slate-100">{g.can}</span>
        </p>
        <p>
          <span className="text-amber-200/90">别误会：</span>
          <span className="text-slate-100">{g.not}</span>
        </p>
      </div>
    </EvalCollapsibleBanner>
  );
}
