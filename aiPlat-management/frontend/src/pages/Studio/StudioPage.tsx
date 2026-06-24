import { useState, useEffect, useRef, useCallback } from 'react';
import { Send, Sparkles, Check, X, ExternalLink, RefreshCw, Loader2, FileText, ChevronRight } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { studioApi } from '../../services';
import type { StudioSession, PipelineState } from '../../services';

type StudioPhase =
  | 'initial'
  | 'clarifying'
  | 'prd_draft'
  | 'team_assembled'
  | 'pipeline_running'
  | 'testing'
  | 'deploying'
  | 'completed';

interface Message {
  id: string;
  role: 'user' | 'pm';
  content: string;
  timestamp: number;
}

interface DeployEvent {
  type: string;
  version?: string;
  elapsed_s?: number;
  error?: string;
  attempt?: number;
  timestamp: number;
}

interface StageInfo {
  stage_id: string;
  agent_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'paused' | 'skipped';
  error?: string;
  pause_reason?: string;
}

function StageIcon({ status }: { status: StageInfo['status'] }) {
  const base = 'w-4 h-4 flex-shrink-0';
  switch (status) {
    case 'completed':
      return <Check className={`${base} text-green-500`} />;
    case 'running':
      return <Loader2 className={`${base} text-blue-500 animate-spin`} />;
    case 'failed':
      return <X className={`${base} text-red-500`} />;
    case 'paused':
      return <ChevronRight className={`${base} text-yellow-500`} />;
    default:
      return <div className={`${base} rounded-full border border-gray-600`} />;
  }
}

const PHASE_LABELS: Record<StudioPhase, string> = {
  initial: '就绪',
  clarifying: '需求澄清中',
  prd_draft: 'PRD 已生成',
  team_assembled: '团队已组建',
  pipeline_running: '构建中',
  testing: '测试中',
  deploying: '部署中',
  completed: '构建完成',
};

function generateId() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
}

const SESSION_STORAGE_KEY = 'app_studio_session_id';

export default function StudioPage() {
  const [phase, setPhase] = useState<StudioPhase>('initial');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [prd, setPrd] = useState<Record<string, unknown> | null>(null);
  const [stages, setStages] = useState<StageInfo[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [appUrl, setAppUrl] = useState<string | null>(null);
  const [deployEvents, setDeployEvents] = useState<DeployEvent[]>([]);
  const [deployHealthStatus, setDeployHealthStatus] = useState<'pending' | 'healthy' | 'failed' | 'rolled_back' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const deployStreamRef = useRef<EventSource | null>(null);
  const [pmThinking, setPmThinking] = useState(false);
  const [thinkingDuration, setThinkingDuration] = useState(0);

  const scrollToBottom = useCallback(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  useEffect(() => {
    const saved = localStorage.getItem(SESSION_STORAGE_KEY);
    if (!saved) return;
    studioApi.getSession(saved).then((res) => {
      const s = res as StudioSession;
      setSessionId(s.session_id);
      if (s.project_id) setProjectId(s.project_id);
      if (s.messages?.length) {
        setMessages(s.messages.map((m, i) => ({
          id: `restored-${i}`,
          role: m.role as 'user' | 'pm',
          content: m.content,
          timestamp: Date.now() - (s.messages!.length - i) * 1000,
        })));
      }
      if (s.prd) setPrd(s.prd);
      if (s.phase) {
        const phaseMap: Record<string, StudioPhase> = {
          clarifying: 'clarifying',
          prd_draft: 'prd_draft',
          team_assembled: 'team_assembled',
          running: 'pipeline_running',
          testing: 'testing',
          deploying: 'deploying',
          completed: 'completed',
        };
        setPhase(phaseMap[s.phase] || 'initial');
      }
    }).catch(() => {
      localStorage.removeItem(SESSION_STORAGE_KEY);
    });
  }, []);

  useEffect(() => {
    return () => {
      eventSourceRef.current?.close();
      deployStreamRef.current?.close();
    };
  }, []);

  useEffect(() => {
    if (!pmThinking) { setThinkingDuration(0); return; }
    const timer = setInterval(() => setThinkingDuration(d => d + 1), 1000);
    return () => clearInterval(timer);
  }, [pmThinking]);

  const subscribeToPipeline = useCallback((pid: string) => {
    eventSourceRef.current?.close();

    let retryDelay = 3000;
    let lastStatus = '';

    const poll = () => {
      studioApi.getProjectState(pid).then((res) => {
        const state = res as PipelineState;
        const stageList = (state.stages || []) as StageInfo[];
        setStages(stageList);

        const runningStages = stageList.filter(s => s.status !== 'completed' && s.status !== 'failed' && s.status !== 'skipped');
        const failedStage = stageList.find(s => s.status === 'failed');
        const pausedStage = stageList.find(s => s.status === 'paused');
        const allCompleted = stageList.length > 0 && stageList.every(
          s => s.status === 'completed' || s.status === 'skipped'
        );

        if (pausedStage) {
          setPhase('pipeline_running');
        } else if (failedStage) {
          setPhase('pipeline_running');
          setError(`阶段 ${failedStage.agent_id} 执行失败: ${failedStage.error || '未知错误'}`);
        } else if (allCompleted) {
          setPhase('testing');
        } else if (runningStages.length > 0) {
          setPhase('pipeline_running');
          retryDelay = 3000;
        } else {
          retryDelay = Math.min(retryDelay * 1.5, 15000);
        }

        const statusSnapshot = stageList.map(s => `${s.stage_id}:${s.status}`).join(',');
        if (statusSnapshot !== lastStatus) {
          lastStatus = statusSnapshot;
        }
      }).catch(() => {
        retryDelay = Math.min(retryDelay * 2, 30000);
      }).finally(() => {
        setTimeout(poll, retryDelay);
      });
    };

    poll();
  }, []);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput('');
    setLoading(true);
    setError(null);

    const userMsg: Message = { id: generateId(), role: 'user', content: text, timestamp: Date.now() };
    setMessages((prev) => [...prev, userMsg]);

    try {
      if (!sessionId) {
        const res = (await studioApi.createSession(text)) as StudioSession;
        setSessionId(res.session_id);
        localStorage.setItem(SESSION_STORAGE_KEY, res.session_id);
        setPhase('clarifying');

        // Send first message to get PM's initial response
        setPmThinking(true);
        const chatRes = (await studioApi.chatSession(res.session_id, text)) as StudioSession;
        setPmThinking(false);
        if (chatRes.messages?.length) {
          const msgs = chatRes.messages.map((m, i) => ({
            id: generateId() + i,
            role: m.role as 'user' | 'pm',
            content: m.content,
            timestamp: Date.now() + i,
          }));
          setMessages((prev) => [...prev, ...msgs]);
        }
        if (chatRes.prd) { setPrd(chatRes.prd); setPhase('prd_draft'); }
      } else if (phase === 'prd_draft' || phase === 'team_assembled') {
        if (phase === 'prd_draft') {
          await studioApi.confirmSession(sessionId);
          setPhase('team_assembled');
          setMessages((prev) => [
            ...prev,
            { id: generateId(), role: 'pm', content: 'PRD 已确认，正在组装 Agent 团队...', timestamp: Date.now() },
          ]);
        }
        const startRes = (await studioApi.startPipeline(sessionId)) as StudioSession;
        setPhase('pipeline_running');
        if (startRes.project_id) {
          setProjectId(startRes.project_id);
          subscribeToPipeline(startRes.project_id);
        }
        setMessages((prev) => [
          ...prev,
          {
            id: generateId(),
            role: 'pm',
            content: 'Builder Pipeline 已启动！Agent 团队正在按阶段执行构建任务。右侧面板可查看实时进度。',
            timestamp: Date.now(),
          },
        ]);
      } else {
        setPmThinking(true);
        const chatRes = (await studioApi.chatSession(sessionId, text)) as StudioSession;
        setPmThinking(false);
        if (chatRes.messages?.length) {
          const msgs = chatRes.messages.map((m, i) => ({
            id: generateId() + i,
            role: m.role as 'user' | 'pm',
            content: m.content,
            timestamp: Date.now() + i,
          }));
          setMessages((prev) => [...prev, ...msgs]);
        }
        if (chatRes.prd) {
          setPrd(chatRes.prd);
          setPhase('prd_draft');
        }
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '请求失败';
      setError(msg);
      setMessages((prev) => [
        ...prev,
        { id: generateId(), role: 'pm', content: `抱歉，出现了错误：${msg}。请重试或刷新页面。`, timestamp: Date.now() },
      ]);
    } finally {
      setPmThinking(false);
      setLoading(false);
    }
  };

  const handleConfirm = () => {
    handleSend();
  };

  const handleApprove = async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      await studioApi.approveProject(projectId);
      setMessages((prev) => [
        ...prev,
        { id: generateId(), role: 'pm', content: '已批准继续执行。', timestamp: Date.now() },
      ]);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '审批失败');
    } finally {
      setLoading(false);
    }
  };

  const handleReject = async () => {
    if (!projectId) return;
    const feedback = prompt('请输入驳回原因：');
    if (!feedback?.trim()) return;
    setLoading(true);
    try {
      await studioApi.rejectProject(projectId, feedback);
      setMessages((prev) => [
        ...prev,
        { id: generateId(), role: 'pm', content: `已驳回：${feedback}。Pipeline 将回滚并重新执行。`, timestamp: Date.now() },
      ]);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '驳回失败');
    } finally {
      setLoading(false);
    }
  };

  const handleDeploy = async () => {
    if (!projectId) return;
    setLoading(true);
    setPhase('deploying');
    setDeployEvents([]);
    setDeployHealthStatus('pending');
    try {
      const res = await studioApi.deployToApp(projectId);
      const deployResult = res as { app_url: string; health_check_pending?: boolean };
      setAppUrl(deployResult.app_url);

      // Connect to deploy-stream SSE for health check progress
      const streamUrl = `${window.location.origin}/api/studio/projects/${projectId}/deploy-stream`;
      const deployEs = new EventSource(streamUrl);
      deployStreamRef.current?.close();
      deployStreamRef.current = deployEs;

      deployEs.addEventListener('deploy_healthy', () => {
        setDeployHealthStatus('healthy');
        setPhase('completed');
        setMessages((prev) => [
          ...prev,
          { id: generateId(), role: 'pm', content: `部署成功！应用已通过健康检查。\n\n[打开应用](${deployResult.app_url})`, timestamp: Date.now() },
        ]);
        deployEs.close();
      });

      deployEs.addEventListener('health_timeout', () => {
        setDeployEvents((prev) => [...prev, { type: 'health_timeout', timestamp: Date.now() }]);
      });

      deployEs.addEventListener('rollback_success', () => {
        setDeployHealthStatus('rolled_back');
        setPhase('completed');
        setError('部署的健康检查超时，已自动回滚到上一个版本。');
        setMessages((prev) => [
          ...prev,
          { id: generateId(), role: 'pm', content: '健康检查超时，已自动回滚到上一个稳定版本。请检查部署日志后重试。', timestamp: Date.now() },
        ]);
        deployEs.close();
      });

      deployEs.addEventListener('rollback_failed_critical', (e) => {
        setDeployHealthStatus('failed');
        setPhase('completed');
        setError('部署失败且回滚失败！请手动检查部署目录。');
        deployEs.close();
      });

      deployEs.addEventListener('health_poll', (e) => {
        const data = JSON.parse((e as MessageEvent).data) as DeployEvent;
        setDeployEvents((prev) => [...prev, data]);
      });

      deployEs.onerror = () => {
        deployEs.close();
      };

      setMessages((prev) => [
        ...prev,
        { id: generateId(), role: 'pm', content: '部署包已解压，正在进行健康检查...', timestamp: Date.now() },
      ]);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '部署失败');
      setPhase('testing');
    } finally {
      setLoading(false);
    }
  };

  const handleTest = async () => {
    if (!projectId) return;
    setLoading(true);
    setPhase('testing');
    try {
      const res = await studioApi.testProject(projectId);
      setMessages((prev) => [
        ...prev,
        {
          id: generateId(),
          role: 'pm',
          content: (res as { all_passed: boolean }).all_passed
            ? '测试全部通过！点击"部署"将应用发布上线。'
            : '部分测试未通过，请检查 Pipeline 各阶段输出。',
          timestamp: Date.now(),
        },
      ]);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '测试失败');
      setPhase('pipeline_running');
    } finally {
      setLoading(false);
    }
  };

  const handleNewSession = () => {
    eventSourceRef.current?.close();
    deployStreamRef.current?.close();
    localStorage.removeItem(SESSION_STORAGE_KEY);
    setSessionId(null);
    setProjectId(null);
    setMessages([]);
    setPrd(null);
    setStages([]);
    setAppUrl(null);
    setDeployEvents([]);
    setDeployHealthStatus(null);
    setError(null);
    setPhase('initial');
  };

  return (
    <div className="flex flex-col h-[calc(100vh-80px)]">
      <header className="flex items-center justify-between mb-4 flex-shrink-0">
        <div className="flex items-center gap-3">
          <Sparkles className="w-5 h-5 text-primary" />
          <h1 className="text-lg font-semibold text-gray-100">App Studio</h1>
          <span className="text-xs px-2 py-0.5 rounded bg-dark-hover text-gray-400 border border-dark-border">
            {PHASE_LABELS[phase]}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {sessionId && (
            <button
              onClick={handleNewSession}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border border-dark-border text-gray-400 hover:text-gray-200 hover:bg-dark-hover transition-colors"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              新项目
            </button>
          )}
        </div>
      </header>

      <div className="flex gap-4 flex-1 min-h-0">
        <div className="flex-1 flex flex-col min-w-0 bg-dark-card rounded-xl border border-dark-border">
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.length === 0 && phase === 'initial' && (
              <div className="flex items-center justify-center h-full">
                <div className="text-center space-y-3 max-w-md">
                  <Sparkles className="w-10 h-10 text-primary mx-auto" />
                  <h2 className="text-xl font-semibold text-gray-200">一句话，生成你的应用</h2>
                  <p className="text-sm text-gray-500">
                    描述你想要创建的应用，AI PM 会和你对话澄清需求，
                    然后自动组建 Agent 团队完成开发、测试、部署。
                  </p>
                  <p className="text-xs text-gray-600">
                    试试说：&ldquo;我要一个客户管理系统&rdquo;或&ldquo;给我一个TODO应用&rdquo;
                  </p>
                </div>
              </div>
            )}

            {messages.map((msg) => (
              <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div
                  className={`max-w-[80%] rounded-xl px-4 py-2.5 text-sm leading-relaxed ${
                    msg.role === 'user'
                      ? 'bg-primary text-white'
                      : 'bg-dark-hover text-gray-200 border border-dark-border'
                  }`}
                >
                  {msg.role === 'pm' ? (
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        a: ({ href, children }) => (
                          <a href={href} target="_blank" rel="noopener noreferrer" className="text-blue-400 underline">
                            {children}
                          </a>
                        ),
                        code: ({ children }) => (
                          <code className="bg-dark-bg px-1 py-0.5 rounded text-xs">{children}</code>
                        ),
                        pre: ({ children }) => (
                          <pre className="bg-dark-bg p-3 rounded-lg text-xs overflow-x-auto my-2">{children}</pre>
                        ),
                      }}
                    >
                      {msg.content}
                    </ReactMarkdown>
                  ) : (
                    msg.content
                  )}
                </div>
              </div>
            ))}
            <div ref={chatEndRef} />

            {pmThinking && (
              <div className="flex justify-start px-4 pb-2">
                <div className="bg-dark-hover border border-dark-border rounded-xl px-4 py-3 flex items-center gap-3">
                  <Loader2 className="w-4 h-4 text-blue-400 animate-spin" />
                  <div>
                    <span className="text-sm text-gray-300">PM 正在分析你的需求</span>
                    {thinkingDuration > 10 && (
                      <span className="text-xs text-gray-600 ml-2">
                        (本地模型推理中... {thinkingDuration}s)
                      </span>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>

          {phase === 'prd_draft' && prd && (
            <div className="px-4 pb-2">
              <div className="flex gap-2">
                <button
                  onClick={handleConfirm}
                  disabled={loading}
                  className="flex items-center gap-1.5 px-4 py-1.5 bg-green-600 hover:bg-green-700 rounded-lg text-white text-sm font-medium disabled:opacity-50 transition-colors"
                >
                  <Check className="w-4 h-4" /> 确认 PRD，开始构建
                </button>
                <button
                  onClick={() => setPhase('clarifying')}
                  className="flex items-center gap-1.5 px-4 py-1.5 border border-dark-border rounded-lg text-gray-400 hover:text-gray-200 text-sm transition-colors"
                >
                  补充需求
                </button>
              </div>
            </div>
          )}

          {(phase === 'testing' || messages.length > 0) && (
            <div className="px-4 pb-2">
              <div className="flex gap-2 flex-wrap">
                {phase === 'testing' && (
                  <button
                    onClick={handleTest}
                    disabled={loading}
                    className="flex items-center gap-1.5 px-4 py-1.5 bg-blue-600 hover:bg-blue-700 rounded-lg text-white text-sm font-medium disabled:opacity-50 transition-colors"
                  >
                    <FileText className="w-4 h-4" /> 运行测试
                  </button>
                )}
                {phase === 'completed' && appUrl && (
                  <a
                    href={appUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1.5 px-4 py-1.5 bg-green-600 hover:bg-green-700 rounded-lg text-white text-sm font-medium transition-colors"
                  >
                    <ExternalLink className="w-4 h-4" /> 打开应用
                  </a>
                )}
                {phase === 'testing' && (
                  <button
                    onClick={handleDeploy}
                    disabled={loading}
                    className="flex items-center gap-1.5 px-4 py-1.5 bg-purple-600 hover:bg-purple-700 rounded-lg text-white text-sm font-medium disabled:opacity-50 transition-colors"
                  >
                    <ExternalLink className="w-4 h-4" /> 部署到 App
                  </button>
                )}
              </div>
            </div>
          )}

          {error && (
            <div className="px-4 pb-2">
              <div className="px-3 py-2 bg-red-900/30 border border-red-800 rounded-lg text-red-400 text-xs">
                {error}
                <button onClick={() => setError(null)} className="ml-2 underline">关闭</button>
              </div>
            </div>
          )}

          <div className="p-3 border-t border-dark-border">
            <div className="flex gap-2">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
                placeholder={
                  !sessionId
                    ? '描述你想要创建的应用...'
                    : phase === 'prd_draft'
                      ? '确认 PRD 或补充需求...'
                      : '补充需求或回答问题...'
                }
                disabled={loading}
                className="flex-1 px-4 py-2 bg-dark-hover border border-dark-border rounded-lg text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-primary disabled:opacity-50"
              />
              <button
                onClick={handleSend}
                disabled={loading || !input.trim()}
                className="px-4 py-2 bg-primary hover:bg-primary-hover rounded-lg text-white disabled:opacity-50 transition-colors"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        <aside className="w-72 flex-shrink-0 flex flex-col gap-3">
          {prd && (
            <div className="bg-dark-card border border-dark-border rounded-xl p-4">
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">PRD 预览</h3>
              <div className="text-xs text-gray-300 max-h-40 overflow-y-auto">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {typeof prd.summary === 'string'
                    ? prd.summary
                    : JSON.stringify(prd, null, 2)}
                </ReactMarkdown>
              </div>
            </div>
          )}

          {stages.length > 0 && (
            <div className="bg-dark-card border border-dark-border rounded-xl p-4">
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">Pipeline 进度</h3>
              <div className="space-y-2">
                {stages.map((stage) => (
                  <div key={stage.stage_id} className="flex items-center gap-2 text-xs">
                    <StageIcon status={stage.status} />
                    <span className={`flex-1 ${
                      stage.status === 'failed' ? 'text-red-400' :
                      stage.status === 'running' ? 'text-blue-400' :
                      stage.status === 'completed' ? 'text-green-400' :
                      stage.status === 'paused' ? 'text-yellow-400' :
                      'text-gray-500'
                    }`}>
                      {stage.agent_id}
                      {stage.status === 'paused' && stage.pause_reason && (
                        <span className="block text-yellow-500">({stage.pause_reason})</span>
                      )}
                      {stage.status === 'failed' && stage.error && (
                        <span className="block text-red-500">({stage.error})</span>
                      )}
                    </span>
                    <span className="text-gray-600">{{
                      pending: '待执行',
                      running: '执行中',
                      completed: '完成',
                      failed: '失败',
                      paused: '暂停',
                      skipped: '跳过',
                    }[stage.status]}</span>
                  </div>
                ))}
              </div>

              {stages.some(s => s.status === 'paused') && (
                <div className="mt-3 p-2 border border-yellow-800 rounded-lg bg-yellow-900/20">
                  <p className="text-xs text-yellow-400 mb-2">Pipeline 暂停，等待审批</p>
                  <div className="flex gap-2">
                    <button
                      onClick={handleApprove}
                      disabled={loading}
                      className="flex-1 flex items-center justify-center gap-1 px-2 py-1.5 bg-green-700 hover:bg-green-600 rounded text-xs text-white font-medium disabled:opacity-50"
                    >
                      <Check className="w-3 h-3" /> 批准
                    </button>
                    <button
                      onClick={handleReject}
                      disabled={loading}
                      className="flex-1 flex items-center justify-center gap-1 px-2 py-1.5 bg-red-700 hover:bg-red-600 rounded text-xs text-white font-medium disabled:opacity-50"
                    >
                      <X className="w-3 h-3" /> 驳回
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {projectId && (
            <div className="bg-dark-card border border-dark-border rounded-xl p-4">
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">项目信息</h3>
              <div className="text-xs text-gray-500 space-y-1">
                <div>Session: <span className="text-gray-400 font-mono">{sessionId?.slice(0, 12)}...</span></div>
                <div>Project: <span className="text-gray-400 font-mono">{projectId.slice(0, 12)}...</span></div>
                <div>状态: <span className="text-gray-300">{PHASE_LABELS[phase]}</span></div>
              </div>
            </div>
          )}

          {deployHealthStatus && (
            <div className={`bg-dark-card border rounded-xl p-4 ${
              deployHealthStatus === 'healthy' ? 'border-green-800' :
              deployHealthStatus === 'rolled_back' ? 'border-yellow-800' :
              deployHealthStatus === 'failed' ? 'border-red-800' :
              'border-blue-800'
            }`}>
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">部署健康检查</h3>
              <div className="space-y-1.5 text-xs">
                {deployHealthStatus === 'pending' && (
                  <div className="flex items-center gap-2 text-blue-400">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    健康检查进行中... ({deployEvents.length > 0 ? `${deployEvents.filter(e => e.type === 'health_poll').length}s` : ''})
                  </div>
                )}
                {deployHealthStatus === 'healthy' && (
                  <div className="flex items-center gap-2 text-green-400">
                    <Check className="w-3 h-3" /> 健康检查通过
                  </div>
                )}
                {deployHealthStatus === 'rolled_back' && (
                  <div className="text-yellow-400 space-y-1">
                    <div className="flex items-center gap-2">
                      <RefreshCw className="w-3 h-3" /> 已自动回滚
                    </div>
                    <p className="text-yellow-500">健康检查超时，已恢复至上一个稳定版本。</p>
                  </div>
                )}
                {deployHealthStatus === 'failed' && (
                  <div className="text-red-400 space-y-1">
                    <div className="flex items-center gap-2">
                      <X className="w-3 h-3" /> 部署失败
                    </div>
                    <p className="text-red-500">回滚也失败，请手动检查部署目录。</p>
                  </div>
                )}
              </div>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
