import React from 'react';

export type KnowledgeTrack = 'business' | 'library';

const COPY: Record<KnowledgeTrack, { title: string; body: string }> = {
  business: {
    title: '业务本体轨（权威）',
    body: '域 YAML + GraphIndex 决定 Action / 审计 / 业务 GraphRAG。配置 Evolve 与本体提案分门；Wiki 不在此冒充业务权威。',
  },
  library: {
    title: '知识检索轨（非业务权威）',
    body: '向量索引 + Wiki 页面服务 RAG 与人读资料。冲突时域本体胜出；不得用 Wiki/向量片段顶替 GraphIndex 实体。',
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
      <div className="font-semibold text-[11px] uppercase tracking-wide opacity-90">{c.title}</div>
      <p className="mt-0.5 text-gray-300/90 leading-relaxed">{c.body}</p>
    </div>
  );
};

export default DualTrackBanner;
