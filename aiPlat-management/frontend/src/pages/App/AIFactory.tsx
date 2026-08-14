import React, { useState, Suspense, lazy, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Sparkles, MessageCircle, Settings } from 'lucide-react';

const FactoryPage = lazy(() => import('./Factory'));
const StudioPage = lazy(() => import('../Studio/StudioPage'));
const UserWorkbench = lazy(() => import('../ValueCenter/UserWorkbench'));

const TABS = [
  { key: 'quick', label: '快速开始', icon: Sparkles, desc: '选能力、填描述，一键启动' },
  { key: 'chat', label: '对话式', icon: MessageCircle, desc: '和 AI 聊天澄清需求，自动组队执行' },
  { key: 'advanced', label: '高级配置', icon: Settings, desc: '手动配置 Agent、阶段、审批流程' },
] as const;

const AIFactory: React.FC = () => {
  const [searchParams] = useSearchParams();
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
      {/* Tab bar */}
      <div style={{
        display: 'flex', gap: 0, marginBottom: 0,
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
      </div>

      {/* Tab content */}
      <Suspense fallback={<div style={{ padding: 40, color: '#94a3b8' }}>加载中...</div>}>
        {tab === 'quick' && <UserWorkbench />}
        {tab === 'chat' && <StudioPage />}
        {tab === 'advanced' && <FactoryPage />}
      </Suspense>
    </div>
  );
};

export default AIFactory;
