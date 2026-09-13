import React, { useState, useEffect } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { Loader2, ChevronRight, Check } from 'lucide-react';
import { Card } from '../../components/ui';
import { resolveStageComponent } from '../../components/AppStages';
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
  const [searchParams] = useSearchParams();
  const embedMode =
    searchParams.get('embed') === '1' || searchParams.get('embed') === 'true';
  const [config, setConfig] = useState<AppPageConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [currentStage, setCurrentStage] = useState(0);
  const [stageResults, setStageResults] = useState<StageResult>({});

  useEffect(() => {
    (async () => {
      try {
        let raw = '';
        // Prefer deployed app_page.json when present (fast path for preview embed)
        try {
          const appRes = await fetch(`/app/sessions/${projectId}/app_page.json`);
          if (appRes.ok) raw = await appRes.text();
        } catch {
          /* fall through to pipeline state */
        }
        if (!raw || !raw.includes('"app_name"')) {
          const st = await projectApi.getState(projectId!);
          const state = (st as any)?.state || {};
          const fp = state.frontend_pages || state.agent_app || {};
          if (fp?.raw_output) raw = fp.raw_output;
          else if (state.agent_app?.raw_output) raw = state.agent_app.raw_output;
        }

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

  const executeSkill = React.useCallback(async (skillName: string, params: Record<string, any>) => {
    const resp = await fetch(`/api/platform/builder/projects/${projectId}/execute/${skillName}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    return resp.json();
  }, [projectId]);

  const resolveInput = (input: Record<string, string> | undefined, results: StageResult) => {
    if (!input) return {};
    const resolved: Record<string, any> = {};
    for (const [k, v] of Object.entries(input)) {
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
    const stages = config?.stages || [];
    const idx = stages.findIndex((s) => s.id === stageId);
    const stage = idx >= 0 ? stages[idx] : undefined;
    const sourceType = String(
      result?.source_type || result?.result?.source_type || '',
    ).toLowerCase();
    const taskId =
      result?.task_id ||
      result?.result?.task_id ||
      (typeof result?.result === 'object' ? result?.result?.task_id : undefined);
    const nested =
      result?.result && typeof result.result === 'object' ? result.result : {};
    const videoPath =
      result?.video_path ||
      nested?.video_path ||
      nested?.file_path ||
      nested?.local_path ||
      result?.file_path;

    // URL 路径：来源阶段已触发下载/分析，跳过 file_upload，并把 task_id 镜像到 upload
    // 以便 progress 的 {{upload.task_id}} 能解析。
    let nextId = stage?.next;
    const patch: StageResult = {
      [stageId]: {
        ...result,
        ...nested,
        task_id: taskId || result?.task_id,
        video_path: videoPath,
        file_path: result?.file_path || nested?.file_path || videoPath,
      },
    };
    if (
      stageId === 'source' &&
      (sourceType === 'url' || sourceType === 'link' || sourceType === 'http') &&
      nextId === 'upload'
    ) {
      const uploadStage = stages.find((s) => s.id === 'upload');
      nextId = uploadStage?.next || 'progress';
      patch.upload = { ...patch[stageId], source_type: sourceType || 'url' };
    }

    setStageResults((prev) => ({ ...prev, ...patch }));
    const nextIdx = nextId
      ? stages.findIndex((s) => s.id === nextId)
      : idx >= 0
        ? idx + 1
        : -1;
    if (nextIdx >= 0) {
      setCurrentStage(nextIdx);
    } else if (idx >= 0 && idx < stages.length - 1) {
      setCurrentStage(idx + 1);
    }
  };

  const renderStage = (stage: StageConfig, idx: number, isActive: boolean) => {
    const input = resolveInput(stage.config?.input, stageResults);
    const advance = (result: any) => handleStageComplete(stage.id, result);
    const props = {
      config: stage.config,
      onExecute: executeSkill,
      skill: stage.skill,
      stageInput: input,
      projectId,
      // DataForm/FileUpload 用 onNext；部分组件用 onComplete — 同时提供
      onNext: advance,
      onComplete: advance,
    };

    const Component = resolveStageComponent(stage.component);

    if (!Component) {
      return (
        <Card className="p-4">
          <p className="text-sm text-gray-400">未知组件: {stage.component}</p>
        </Card>
      );
    }

    return (
      <div key={stage.id} className={isActive ? '' : 'hidden'}>
        <Component {...(props as any)} />
      </div>
    );
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 animate-spin text-primary" />
        <span className="ml-2 text-gray-400">加载应用...</span>
      </div>
    );
  }
  if (error) {
    return (
      <Card className="p-6 max-w-lg mx-auto mt-10">
        <p className="text-red-400">{error}</p>
      </Card>
    );
  }
  if (!config) return null;

  const isWizard = config.mode === 'wizard';

  return (
    <div className={`flex ${embedMode ? 'min-h-screen' : 'h-full'} bg-dark-bg`}>
      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-3xl mx-auto">
          <h1 className="text-xl font-bold text-gray-100 mb-2">{config.app_title}</h1>
          {embedMode && (
            <p className="text-xs text-gray-500 mb-4">应用预览 · {projectId}</p>
          )}

          {isWizard && (
            <div className="flex items-center gap-1 mb-6 text-xs">
              {config.stages.map((s, i) => (
                <React.Fragment key={s.id}>
                  <span
                    className={`px-2 py-1 rounded ${
                      i === currentStage
                        ? 'bg-primary/20 text-primary'
                        : i < currentStage
                          ? 'text-green-400'
                          : 'text-gray-600'
                    }`}
                  >
                    {i < currentStage ? <Check className="w-3 h-3 inline mr-1" /> : null}
                    {s.title}
                  </span>
                  {i < config.stages.length - 1 && (
                    <ChevronRight className="w-3 h-3 text-gray-600" />
                  )}
                </React.Fragment>
              ))}
            </div>
          )}

          <div className="space-y-4">
            {config.stages.map((s, i) => {
              // Wizard: only mount the active stage. Hidden CSS still runs
              // ProgressPoller/ResultDashboard effects with unresolved {{upload.*}}.
              if (isWizard && i !== currentStage) return null;
              return renderStage(s, i, true);
            })}
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
