import React, { useState, useRef, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { CheckCircle, Play } from 'lucide-react';
import { builderApi, type BuilderSession } from '../../../services';
import { Button, Card, CardHeader, CardContent, toast } from '../../../components/ui';
import { ChatWidget } from '../../../components/ui/ChatWidget';
import { BuilderPipeline } from '../../../components/Builder/BuilderPipeline';

const PHASE_LABELS: Record<string, string> = {
  dialogue: '需求对话',
  executing: '流水线执行中',
  done: '交付完成',
  failed: '执行失败',
};

const BuilderPage: React.FC = () => {
  const [session, setSession] = useState<BuilderSession | null>(null);
  const [prdReady, setPrdReady] = useState(false);
  const [started, setStarted] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval>>();

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  const handleSend = useCallback(async (message: string) => {
    if (!session) {
      const r = message || '新的需求';
      const { session_id } = await builderApi.createSession(r);
      const resp = await builderApi.chat(session_id, r);
      setSession(resp.session_state);
      if (resp.prd_ready) setPrdReady(true);
      return resp.reply;
    }
    const resp = await builderApi.chat(session.session_id, message);
    setSession(resp.session_state);
    if (resp.prd_ready) setPrdReady(true);
    return resp.reply;
  }, [session]);

  const confirmAndStart = useCallback(async () => {
    if (!session) return;
    try {
      await builderApi.confirm(session.session_id);
      await builderApi.startPipeline(session.session_id);
      setStarted(true);

      pollRef.current = setInterval(async () => {
        try {
          const state = await builderApi.getState(session.session_id);
          setSession(state);
          if (state.phase === 'done' || state.phase === 'failed') {
            if (pollRef.current) clearInterval(pollRef.current);
          }
        } catch { if (pollRef.current) clearInterval(pollRef.current); }
      }, 2000);
    } catch (e: unknown) { toast.error(e instanceof Error ? e.message : '启动失败'); }
  }, [session]);

  if (started) {
    return (
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4 p-4">
        <Card>
          <CardHeader title="流水线执行" extra={
            <span className={`text-xs px-2 py-1 rounded ${
              session?.phase === 'done' ? 'bg-green-500/10 text-green-300' :
              session?.phase === 'failed' ? 'bg-red-500/10 text-red-300' :
              'bg-primary/10 text-primary'
            }`}>{PHASE_LABELS[session?.phase || 'executing']}</span>
          } />
          <CardContent>
            {session && <BuilderPipeline session={session} />}
          </CardContent>
        </Card>
      </motion.div>
    );
  }

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4 p-4">
      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_380px] gap-4">
        <Card className="flex flex-col">
          <CardHeader title="需求对话" extra={
            <span className="text-xs px-2 py-1 rounded bg-primary/10 text-primary">
              {PHASE_LABELS[session?.phase || 'dialogue']}
            </span>
          } />
          <CardContent className="flex-1 flex flex-col p-0">
            <ChatWidget
              title="AI 产品经理"
              placeholder="描述你想要构建的功能..."
              onSend={handleSend}
              maxHeight="55vh"
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader title="PRD 预览" />
          <CardContent>
            {session?.prd ? (
              <div className="space-y-3 text-sm">
                <div><span className="text-gray-400">标题：</span><span className="text-gray-100">{session.prd.title}</span></div>
                <div><span className="text-gray-400">Scope：</span><span className="text-gray-100">{session.prd.scope}</span></div>
                <div><span className="text-gray-400">用户故事：</span>
                  <ul className="mt-1 space-y-1">
                    {session.prd.user_stories?.map((us: { id: string; description: string }) => (
                      <li key={us.id} className="text-gray-100 text-xs"><span className="text-primary">{us.id}</span> {us.description}</li>
                    ))}
                  </ul>
                </div>
              </div>
            ) : (
              <div className="text-sm text-gray-500">等待需求确认...</div>
            )}
          </CardContent>
        </Card>
      </div>

      {prdReady && !started && (
        <div className="p-4 rounded-lg border border-green-500/30 bg-green-500/5">
          <div className="flex items-center gap-2 mb-2"><CheckCircle className="w-4 h-4 text-green-400" /><span className="text-sm font-semibold text-green-300">PRD 已生成</span></div>
          <div className="text-xs text-gray-400 mb-3">确认需求后启动流水线</div>
          <Button variant="primary" onClick={confirmAndStart} icon={<Play className="w-4 h-4" />}>确认需求，开始构建</Button>
        </div>
      )}
    </motion.div>
  );
};

export default BuilderPage;
