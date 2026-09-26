import React from 'react';

export type KnowledgeTrack = 'business' | 'library';

const COPY: Record<KnowledgeTrack, { title: string; body: string }> = {
  business: {
    title: '业务说明书',
    body: '两类东西别混：说明书=有哪些类/关系（结构图）；知识图=具体实体怎么连（实例边）。日常优先「从文档生成 → 确认」写知识图。',
  },
  library: {
    title: '知识库（查资料）',
    body: '给人读、给检索用。和业务说明书冲突时，以业务说明书为准。',
  },
};

/** Fixed dual-track authority banner for knowledge shell pages. */
export const DualTrackBanner: React.FC<{ track: KnowledgeTrack }> = ({ track }) => {
  const c = COPY[track];
  const tone =
    track === 'business'
      ? 'border-emerald-800/40 bg-emerald-950/20 text-emerald-200/90'
      : 'border-sky-800/40 bg-sky-950/20 text-sky-200/90';
  return (
    <div className={`mx-6 mt-4 mb-2 rounded-lg border px-3 py-2 text-xs ${tone}`}>
      <div className="font-semibold text-[12px] tracking-wide">{c.title}</div>
      <p className="mt-0.5 text-gray-300/90 leading-relaxed">{c.body}</p>
    </div>
  );
};

export default DualTrackBanner;
