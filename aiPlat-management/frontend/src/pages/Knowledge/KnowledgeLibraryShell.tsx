import React, { Suspense, lazy } from 'react';
import { Loader2 } from 'lucide-react';
import DualTrackBanner from '../../components/knowledge/DualTrackBanner';

const KnowledgeBasePage = lazy(() => import('../Platform/KnowledgeBase'));

const Loading = () => (
  <div className="flex items-center justify-center py-24 text-gray-500">
    <Loader2 className="w-6 h-6 animate-spin mr-2" />
    加载中…
  </div>
);

/** Shell: 知识检索轨 — 向量 | Wiki | Vault（及评估/健康等） */
const KnowledgeLibraryShell: React.FC = () => {
  return (
    <div className="min-h-full flex flex-col">
      <DualTrackBanner track="library" />
      <div className="px-6 pt-1">
        <p className="text-[11px] text-gray-500 mb-1">
          日常只用三个页签：<b className="text-gray-400 font-medium">检索资料</b>
          （向量）· <b className="text-gray-400 font-medium">阅读资料</b>
          （Wiki 页）· <b className="text-gray-400 font-medium">原始文件</b>
          （Vault）。右侧「更多」里是质量检查 / 评估，不是业务本体。
        </p>
      </div>
      <div className="flex-1 px-3 pb-4">
        <Suspense fallback={<Loading />}>
          <KnowledgeBasePage />
        </Suspense>
      </div>
    </div>
  );
};

export default KnowledgeLibraryShell;
