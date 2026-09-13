import React, { useEffect, useState, Suspense, lazy } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Sparkles, MessageCircle, Settings } from 'lucide-react';

const FactoryPage = lazy(() => import('./Factory'));
const StudioPage = lazy(() => import('../Studio/StudioPage'));
const UserWorkbench = lazy(() => import('../ValueCenter/UserWorkbench'));

const TABS = [
  { key: 'quick', label: '快速开始', icon: Sparkles, desc: '描述需求并创建工厂项目' },
  { key: 'chat', label: '对话式', icon: MessageCircle, desc: '在工厂内澄清需求并组队' },
  { key: 'advanced', label: '高级配置', icon: Settings, desc: '全量工厂：阶段、审批、部署' },
] as const;

/** F1 feature flag factory_ia_v2 — default ~10% bucket; force via localStorage or ?factory_ia_v2=1 */
export function isFactoryIaV2Enabled(): boolean {
  if (typeof window === 'undefined') return false;
  const params = new URLSearchParams(window.location.search);
  const q = params.get('factory_ia_v2');
  if (q === '1' || q === 'true') return true;
  if (q === '0' || q === 'false') return false;
  const forced = localStorage.getItem('factory_ia_v2');
  if (forced === '1' || forced === 'true') return true;
  if (forced === '0' || forced === 'false') return false;
  let bucket = localStorage.getItem('factory_ia_v2_bucket');
  if (bucket == null || bucket === '') {
    bucket = String(Math.floor(Math.random() * 100));
    localStorage.setItem('factory_ia_v2_bucket', bucket);
  }
  return parseInt(bucket, 10) < 10;
}

const AIFactory: React.FC = () => {
  const [searchParams] = useSearchParams();
  const iaV2 = isFactoryIaV2Enabled();
  const savedTab = localStorage.getItem('ai_factory_tab');
  const defaultTab = searchParams.get('tab') || savedTab || 'quick';
  const [tab, setTab] = useState<string>(TABS.find(t => t.key === defaultTab) ? defaultTab : 'quick');

  useEffect(() => {
    const urlTab = searchParams.get('tab');
    if (urlTab && TABS.find(t => t.key === urlTab)) {
      setTab(urlTab);
    }
  }, [searchParams]);

  const handleTabChange = (key: string) => {
    setTab(key);
    localStorage.setItem('ai_factory_tab', key);
  };

  return (
    <div style={{ padding: '0' }}>
      <div style={{
        display: 'flex', gap: 0, marginBottom: 0, alignItems: 'center',
        borderBottom: '1px solid #374151', background: '#0f172a',
        position: 'sticky', top: 0, zIndex: 10,
      }}>
        {TABS.map(t => {
          const active = tab === t.key;
          const Icon = t.icon;
          return (
            <button
              key={t.key}
              onClick={() => handleTabChange(t.key)}
              title={t.desc}
              style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '12px 20px', border: 'none', background: active ? '#1e293b' : 'transparent',
                color: active ? '#e2e8f0' : '#94a3b8', cursor: 'pointer',
                fontSize: 13, fontWeight: active ? 600 : 400,
                borderBottom: active ? '2px solid #3b82f6' : '2px solid transparent',
                transition: 'all 0.15s',
              }}
            >
              <Icon size={16} />
              {t.label}
            </button>
          );
        })}
        <div style={{ marginLeft: 'auto', paddingRight: 16, display: '#64748b', fontSize: 11 }}>
          {iaV2 ? 'factory_ia_v2: on' : 'factory_ia_v2: off'}
          {!iaV2 && (
            <button
              type="button"
              onClick={() => {
                localStorage.setItem('factory_ia_v2', '1');
                window.location.reload();
              }}
              style={{ marginLeft: 8, color: '#93c5fd', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}
            >
              启用新入口
            </button>
          )}
          {iaV2 && (
            <button
              type="button"
              onClick={() => {
                localStorage.setItem('factory_ia_v2', '0');
                window.location.reload();
              }}
              style={{ marginLeft: 8, color: '#94a3b8', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}
            >
              回滚旧入口
            </button>
          )}
        </div>
      </div>

      <Suspense fallback={<div style={{ padding: 40, color: '#94a3b8' }}>加载中...</div>}>
        {iaV2 ? (
          <>
            {tab === 'quick' && <FactoryPage entryMode="quick" />}
            {tab === 'chat' && <FactoryPage entryMode="chat" />}
            {tab === 'advanced' && <FactoryPage entryMode="advanced" />}
          </>
        ) : (
          <>
            {tab === 'quick' && <UserWorkbench />}
            {tab === 'chat' && <StudioPage />}
            {tab === 'advanced' && <FactoryPage entryMode="advanced" />}
          </>
        )}
      </Suspense>
    </div>
  );
};

export default AIFactory;
