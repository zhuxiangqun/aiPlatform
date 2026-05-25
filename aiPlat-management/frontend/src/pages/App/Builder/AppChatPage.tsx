import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Send, Loader2, Bot, User } from 'lucide-react';
import { toast } from '../../../components/ui';
import { appApi, workflowApi } from '../../../services';

const AppChatPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [app, setApp] = useState<any>(null);
  const [messages, setMessages] = useState<{ role: string; text: string; run_id?: string }[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [pollingRun, setPollingRun] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval>>();

  useEffect(() => {
    if (!id) return;
    appApi.get(id).then((a: any) => setApp(a)).catch(() => toast.error('加载 App 失败'));
  }, [id]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const pollRunResult = useCallback(async (runId: string) => {
    setPollingRun(true);
    let attempts = 0;
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      attempts++;
      try {
        const state: any = await workflowApi.getRunState(runId);
        const phase = state.phase;
        if (phase === 'done' || phase === 'failed' || attempts > 30) {
          clearInterval(pollRef.current);
          setPollingRun(false);
          const parsedState: any = typeof state.state === 'string' ? JSON.parse(state.state || '{}') : (state.state || {});
          const error = parsedState._stage_error || parsedState.error || '';
          if (error) {
            setMessages(prev => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last && last.role === 'assistant' && last.run_id === runId) {
                last.text = `执行失败: ${String(error).slice(0, 500)}`;
              }
              return [...updated];
            });
          } else if (phase === 'done') {
            const outputs = Object.entries(parsedState)
              .filter(([k]) => k.startsWith('_stage_output_'))
              .map(([, v]) => {
                const raw = String(v);
                // Try to extract text from known keys inside the string
                for (const key of ['response', 'raw_output', 'content', 'text', 'output']) {
                  const re = new RegExp(`['"]${key}['"]\\s*:\\s*['"]([^'"]+)['"]`);
                  const m = raw.match(re);
                  if (m) return m[1];
                }
                // Skip empty/trivial values
                if (raw === '{}' || raw.length < 3) return '';
                return raw.slice(0, 1000);
              })
              .filter(Boolean);
            const reply = outputs.join('\n') || '已完成';
            setMessages(prev => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last && last.role === 'assistant' && last.run_id === runId) {
                last.text = reply;
              }
              return [...updated];
            });
          }
        }
      } catch { clearInterval(pollRef.current); setPollingRun(false); }
    }, 3000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  const handleSend = async () => {
    if (!input.trim() || sending || !id) return;
    const msg = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', text: msg }, { role: 'assistant', text: (pollingRun ? '...' : ''), run_id: '' }]);
    setSending(true);
    try {
      const r: any = await appApi.chat(id, msg);
      setMessages(prev => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last && last.role === 'assistant') {
          last.run_id = r.run_id;
          last.text = '思考中...';
        }
        return [...updated];
      });
      pollRunResult(r.run_id);
    } catch (e: any) {
      setMessages(prev => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last && last.role === 'assistant') last.text = '发送失败';
        return [...updated];
      });
      toast.error('发送失败', e?.detail || '');
    } finally { setSending(false); }
  };

  return (
    <div className="h-[calc(100vh-4rem)] flex flex-col">
      <div className="flex items-center gap-3 px-4 py-2 border-b border-dark-border bg-dark-card">
        <button onClick={() => navigate('/app/apps')} className="text-gray-500 hover:text-gray-300"><ArrowLeft className="w-4 h-4" /></button>
        <Bot className="w-4 h-4 text-blue-400" />
        <h1 className="text-sm font-semibold text-gray-100">{app?.name || 'Chat'}</h1>
        {pollingRun && <Loader2 className="w-3 h-3 text-blue-400 animate-spin" />}
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {messages.length === 0 && (
          <div className="text-center py-16 text-gray-500 text-sm">
            <Bot className="w-10 h-10 mx-auto mb-3 text-gray-700" />
            <p>发送消息开始对话</p>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`flex gap-2 ${m.role === 'user' ? 'justify-end' : ''}`}>
            {m.role === 'assistant' && <div className="w-6 h-6 rounded-full bg-blue-500/20 flex items-center justify-center flex-shrink-0 mt-1"><Bot className="w-3.5 h-3.5 text-blue-400" /></div>}
            <div className={`max-w-[75%] rounded-xl px-3 py-2 text-xs ${m.role === 'user' ? 'bg-blue-500/20 text-blue-100' : 'bg-dark-card border border-dark-border text-gray-300'}`}>
              <pre className="whitespace-pre-wrap break-all font-sans">{m.text || '...'}</pre>
              {m.run_id && <div className="text-[9px] text-gray-600 mt-1 font-mono">{m.run_id.slice(0, 12)}</div>}
            </div>
            {m.role === 'user' && <div className="w-6 h-6 rounded-full bg-dark-hover flex items-center justify-center flex-shrink-0 mt-1"><User className="w-3.5 h-3.5 text-gray-400" /></div>}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
      <div className="px-4 py-3 border-t border-dark-border bg-dark-card">
        <div className="flex gap-2">
          <input value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
            placeholder="输入消息..." className="flex-1 h-10 px-3 bg-dark-bg border border-dark-border rounded-lg text-sm text-gray-100 outline-none focus:border-blue-500/40" disabled={sending} />
          <button onClick={handleSend} disabled={!input.trim() || sending}
            className="w-10 h-10 rounded-lg bg-blue-500/20 border border-blue-500/30 flex items-center justify-center hover:bg-blue-500/30 transition-colors disabled:opacity-40">
            {sending ? <Loader2 className="w-4 h-4 text-blue-400 animate-spin" /> : <Send className="w-4 h-4 text-blue-400" />}
          </button>
        </div>
      </div>
    </div>
  );
};

export default AppChatPage;
