import React, { Suspense, lazy, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import DualTrackBanner from '../../components/knowledge/DualTrackBanner';

const KnowledgeFactoryPage = lazy(() => import('../KnowledgeFactory/KnowledgeFactoryPage'));
const OntologyManager = lazy(() => import('../Infra/Ontology/OntologyManager'));
const OntologyEditor = lazy(() => import('../OntologyEditor'));

type TabId = 'factory' | 'domains' | 'editor';

const TABS: { id: TabId; label: string }[] = [
  { id: 'factory', label: '工厂流水线' },
  { id: 'domains', label: '域管理' },
  { id: 'editor', label: '编辑器' },
];

const Loading = () => (
  <div className="flex items-center justify-center py-24 text-gray-500">
    <Loader2 className="w-6 h-6 animate-spin mr-2" />
    加载中…
  </div>
);

/** Shell: 业务本体轨 — 工厂流水线 | 域管理 | 编辑器 */
const BusinessOntologyShell: React.FC = () => {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const tab = useMemo(() => {
    const raw = (params.get('tab') || 'factory') as TabId;
    return TABS.some((t) => t.id === raw) ? raw : 'factory';
  }, [params]);

  const setTab = (id: TabId) => {
    navigate(`/knowledge/business?tab=${id}`, { replace: true });
  };

  return (
    <div className="min-h-full flex flex-col">
      <DualTrackBanner track="business" />
      <div className="px-6 pt-2 flex items-center gap-3 flex-wrap">
        <h1 className="text-lg font-semibold text-gray-100">业务本体</h1>
        <div className="flex gap-1">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`px-3 py-1 rounded text-sm transition-colors ${
                tab === t.id ? 'bg-primary/20 text-primary' : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
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
