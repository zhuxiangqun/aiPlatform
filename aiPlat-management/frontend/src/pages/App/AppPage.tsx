import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { Loader2, ChevronRight, Check } from 'lucide-react';
import { Card, Button } from '../../components/ui';
import { FileUploadStage } from '../../components/AppStages/FileUploadStage';
import { ProgressPoller } from '../../components/AppStages/ProgressPoller';
import { ResultDashboard } from '../../components/AppStages/ResultDashboard';
import { DataFormStage } from '../../components/AppStages/DataFormStage';
import { DataTableStage } from '../../components/AppStages/DataTableStage';
import { ChatWidget } from '../../components/ui/ChatWidget';
import { projectApi } from '../../services';

interface StageConfig {
  id: string;
  title: string;
  skill: string;
  component: string;
  config: Record<string, any>;
  next?: string;
}

interface AppPageConfig {
  app_name: string;
  app_title: string;
  project_id: string;
  mode: 'wizard' | 'dashboard' | 'chat' | 'form';
  stages: StageConfig[];
  side_chat?: { enabled: boolean; hint?: string };
}

type StageResult = Record<string, Record<string, any>>;

export const AppPage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const [config, setConfig] = useState<AppPageConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [currentStage, setCurrentStage] = useState(0);
  const [stageResults, setStageResults] = useState<StageResult>({});

  useEffect(() => {
    (async () => {
      try {
        const st = await projectApi.getState(projectId!);
        const state = (st as any)?.state || {};

        // Try frontend_pages first, then agent_app for embedded config
        let raw = '';
        const fp = state.frontend_pages || state['agent_app'] || {};
        if (fp?.raw_output) raw = fp.raw_output;
        else if (state.agent_app?.raw_output) raw = state.agent_app.raw_output;

        // Fallback: fetch app_page.json from deployed app server
        if (!raw || !raw.includes('"app_name"')) {
          try {
            const appRes = await fetch(`http://localhost:8004/app/sessions/${projectId}/app_page.json`);
            if (appRes.ok) raw = await appRes.text();
          } catch {}
        }

        // Extract JSON from markdown or raw
        const jsonMatch = raw.match(/\{[\s\S]*"app_name"[\s\S]*\}/);
        if (jsonMatch) {
          const parsed = JSON.parse(jsonMatch[0]);
          parsed.project_id = projectId;
          setConfig(parsed);
        } else {
          setError('页面配置未生成。请等待前端程序员阶段完成。');
        }
      } catch (e: any) {
        setError(e?.message || '加载失败');
      } finally {
        setLoading(false);
      }
    })();
  }, [projectId]);

  const executeSkill = async (skillName: string, params: Record<string, any>) => {
    const resp = await fetch(`/api/platform/builder/projects/${projectId}/execute/${skillName}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    return resp.json();
  };

  const resolveInput = (input: Record<string, string> | undefined, results: StageResult) => {
    if (!input) return {};
    const resolved: Record<string, any> = {};
    for (const [k, v] of Object.entries(input)) {
      // Resolve {{stageId.fieldName}} references
      const m = v.match(/^\{\{(.+)\.(.+)\}\}$/);
      if (m) {
        resolved[k] = results[m[1]]?.[m[2]] ?? v;
      } else {
        resolved[k] = v;
      }
    }
    return resolved;
  };

  const handleStageComplete = (stageId: string, result: any) => {
    setStageResults(prev => ({ ...prev, [stageId]: result }));
    const idx = config?.stages.findIndex(s => s.id === stageId) ?? -1;
    if (idx >= 0 && idx < (config?.stages.length || 0) - 1) {
      setCurrentStage(idx + 1);
    }
  };

  const renderStage = (stage: StageConfig, idx: number, isActive: boolean) => {
    const input = resolveInput(stage.config?.input, stageResults);
    const props = { config: stage.config, onExecute: executeSkill, skill: stage.skill, stageInput: input, projectId };

    const Component =
      stage.component === 'file_upload' ? FileUploadStage :
      stage.component === 'progress_poller' ? ProgressPoller :
      stage.component === 'result_dashboard' ? ResultDashboard :
      stage.component === 'data_form' ? DataFormStage :
      stage.component === 'data_table' ? DataTableStage :
      null;

    if (!Component) return <Card className="p-4"><p className="text-sm text-gray-400">未知组件: {stage.component}</p></Card>;

    return (
      <div key={stage.id} className={isActive ? '' : 'hidden'}>
        <Component {...props as any} />
      </div>
    );
  };

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="w-6 h-6 animate-spin text-primary" /><span className="ml-2 text-gray-400">加载应用...</span></div>;
  if (error) return <Card className="p-6 max-w-lg mx-auto mt-10"><p className="text-red-400">{error}</p></Card>;
  if (!config) return null;

  const isWizard = config.mode === 'wizard';

  return (
    <div className="flex h-full">
      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-3xl mx-auto">
          <h1 className="text-xl font-bold text-gray-100 mb-2">{config.app_title}</h1>

          {isWizard && (
            <div className="flex items-center gap-1 mb-6 text-xs">
              {config.stages.map((s, i) => (
                <React.Fragment key={s.id}>
                  <span className={`px-2 py-1 rounded ${i === currentStage ? 'bg-primary/20 text-primary' : i < currentStage ? 'text-green-400' : 'text-gray-600'}`}>
                    {i < currentStage ? <Check className="w-3 h-3 inline mr-1" /> : null}
                    {s.title}
                  </span>
                  {i < config.stages.length - 1 && <ChevronRight className="w-3 h-3 text-gray-600" />}
                </React.Fragment>
              ))}
            </div>
          )}

          <div className="space-y-4">
            {config.stages.map((s, i) => renderStage(s, i, isWizard ? i === currentStage : true))}
          </div>
        </div>
      </div>

      {config.side_chat?.enabled && (
        <div className="w-80 border-l border-dark-border flex-shrink-0">
          <ChatWidget
            title={config.app_title}
            placeholder={config.side_chat.hint || '输入消息...'}
            onSend={async (msg) => {
              const res = await executeSkill('__chat__', { message: msg });
              return res?.reply || res?.error || '(无回复)';
            }}
          />
        </div>
      )}
    </div>
  );
};

export default AppPage;
