/**
 * Per-tab plain-language explainer for Eval Center.
 */
import { HelpCircle } from 'lucide-react';
import { EVAL_TAB_GUIDES } from './evalTabGuides';

type Props = {
  tabId: string;
};

export default function EvalTabGuide({ tabId }: Props) {
  const g = EVAL_TAB_GUIDES[tabId];
  if (!g) return null;

  return (
    <aside
      className="rounded-lg border border-slate-600/50 bg-slate-900/40 px-4 py-3 flex gap-3 items-start"
      data-testid="eval-tab-guide"
      aria-label={`${g.title}说明`}
    >
      <HelpCircle className="w-5 h-5 text-slate-300 shrink-0 mt-0.5" />
      <div className="text-sm space-y-1.5 min-w-0">
        <div className="font-medium text-slate-100">
          这是什么 · {g.title}
        </div>
        <p className="text-slate-200/90">{g.what}</p>
        <ul className="list-disc pl-5 text-slate-300/90 space-y-0.5 text-xs sm:text-sm">
          <li>
            <span className="text-slate-400">可以：</span>
            {g.can}
          </li>
          <li>
            <span className="text-amber-200/90">不能当成：</span>
            {g.not}
          </li>
        </ul>
      </div>
    </aside>
  );
}
