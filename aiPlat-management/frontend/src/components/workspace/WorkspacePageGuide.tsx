import React from 'react';

export type GuideStep = { title: string; detail: string };

/** Compact how-to strip for workspace asset library pages. */
export const WorkspacePageGuide: React.FC<{
  steps: GuideStep[];
  tip?: string;
}> = ({ steps, tip }) => (
  <div className="rounded-xl border border-dark-border bg-dark-card px-4 py-3 text-xs text-gray-400">
    <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
      <span className="text-gray-200 font-medium shrink-0">怎么用</span>
      {steps.map((s, i) => (
        <span key={i} className="inline-flex items-baseline gap-1">
          <span className="text-primary font-medium">{i + 1}. {s.title}</span>
          <span className="text-gray-500">— {s.detail}</span>
        </span>
      ))}
    </div>
    {tip ? <div className="mt-1.5 text-gray-500">{tip}</div> : null}
  </div>
);

export default WorkspacePageGuide;
