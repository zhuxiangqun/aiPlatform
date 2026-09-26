import React, { Suspense, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import DualTrackBanner from '../../components/knowledge/DualTrackBanner';
import { lazyWithRetry } from '../../utils/lazyWithRetry';

const KnowledgeFactoryPage = lazyWithRetry(() => import('../KnowledgeFactory/KnowledgeFactoryPage'));
const OntologyManager = lazyWithRetry(() => import('../Infra/Ontology/OntologyManager'));
const OntologyEditor = lazyWithRetry(() => import('../OntologyEditor'));

type TabId = 'factory' | 'domains' | 'editor';

const TABS: { id: TabId; label: string; hint: string; recommended?: boolean }[] = [
  {
    id: 'factory',
    label: '从文档生成',
    hint: '日常：上传 → 分析 → 确认（写知识图）。「写入说明书」只改类定义，可跳过。',
    recommended: true,
  },
  {
    id: 'domains',
    label: '手动画类',
    hint: '看结构、删脏类、改关系。不负责从文档灌知识图。',
  },
  {
    id: 'editor',
    label: '高级编辑',
    hint: '直接改域 YAML。类名显示为「英文（中文）」。日常请用「从文档生成」；本页一般可跳过。',
  },
];

const Loading = () => (
  <div className="flex items-center justify-center py-24 text-gray-500">
    <Loader2 className="w-6 h-6 animate-spin mr-2" />
    加载中…
  </div>
);

/** Shell: 业务本体轨 — 工厂 | 域管理 | 编辑器 */
const BusinessOntologyShell: React.FC = () => {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const tab = useMemo(() => {
    const raw = (params.get('tab') || 'factory') as TabId;
    return TABS.some((t) => t.id === raw) ? raw : 'factory';
  }, [params]);

  const setTab = (id: TabId) => {
    const next = new URLSearchParams(params);
    next.set('tab', id);
    navigate(`/knowledge/business?${next.toString()}`, { replace: true });
  };

  const active = TABS.find((t) => t.id === tab) || TABS[0];

  return (
    <div className="min-h-full flex flex-col">
      <DualTrackBanner track="business" />
      <div className="px-6 pt-2 space-y-3">
        <div className="flex items-center gap-3 flex-wrap">
          <h1 className="text-lg font-semibold text-gray-100">业务说明书</h1>
          <div className="flex gap-1.5 p-0.5 rounded-lg bg-gray-900/60 border border-gray-800">
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => setTab(t.id)}
                title={t.hint}
                className={`px-3 py-1.5 rounded-md text-sm transition-colors flex items-center gap-1.5 ${
                  tab === t.id
                    ? 'bg-sky-600/25 text-sky-100 shadow-sm'
                    : 'text-gray-400 hover:text-gray-200'
                }`}
              >
                {t.label}
                {t.recommended && (
                  <span className={`text-[9px] px-1 py-0.5 rounded ${
                    tab === t.id ? 'bg-sky-500/30 text-sky-200' : 'bg-gray-800 text-gray-500'
                  }`}>
                    推荐
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>
        <p className="text-sm text-gray-400 max-w-2xl leading-relaxed">{active.hint}</p>
      </div>
      <div className="flex-1">
        <Suspense fallback={<Loading />}>
          {tab === 'factory' && <KnowledgeFactoryPage />}
          {tab === 'domains' && <OntologyManager />}
          {tab === 'editor' && <OntologyEditor />}
        </Suspense>
      </div>
    </div>
  );
};

export default BusinessOntologyShell;
