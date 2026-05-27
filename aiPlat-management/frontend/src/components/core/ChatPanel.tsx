import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Send, Loader2, Zap, X, MessageSquare, User, Bot, BrainCircuit, Eye } from 'lucide-react';
import { agentApi } from '../../services';
import type { Agent } from '../../services';

interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  steps?: number;
  model?: string;
  duration?: number;
}

interface ChatPanelProps {
  agent: Agent | null;
  onClose: () => void;
}

const ChatPanel: React.FC<ChatPanelProps> = ({ agent, onClose }) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [reactMode, setReactMode] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  const handleSend = async () => {
    if (!agent || !input.trim() || sending) return;
    const userMsg: ChatMessage = { role: 'user', content: input };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setSending(true);

    try {
      const res: any = await agentApi.execute(agent.id, {
        input: { message: input },
        options: { force_react: reactMode },
      });
      const meta = res?.metadata || {};
      const assistantMsg: ChatMessage = {
        role: 'assistant',
        content: typeof res?.output === 'string' ? res.output : JSON.stringify(res?.output || res?.error || '(no output)'),
        steps: meta?.steps || 0,
        model: meta?.engine || '?',
        duration: res?.duration_ms || 0,
      };
      setMessages(prev => [...prev, assistantMsg]);
    } catch (e: any) {
      setMessages(prev => [...prev, { role: 'system', content: `Error: ${e?.message || 'unknown'}` }]);
    } finally {
      setSending(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  if (!agent) return null;

  const modelName = (agent as any)?.config?.model || (agent as any)?.metadata?.model || '?';

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <motion.div
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.95, opacity: 0 }}
        className="bg-dark-card border border-dark-border rounded-xl w-full max-w-[640px] h-[85vh] flex flex-col overflow-hidden shadow-2xl"
      >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-dark-border">
        <div className="flex items-center gap-2">
          <MessageSquare className="w-4 h-4 text-blue-400" />
          <div>
            <div className="text-sm font-medium text-gray-100 truncate max-w-[200px]">{agent.display_name || agent.name}</div>
            <div className="text-[10px] text-gray-500">{modelName}</div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setReactMode(!reactMode)}
            className={`p-1 rounded text-[10px] ${reactMode ? 'bg-blue-500/20 text-blue-300' : 'text-gray-500'}`}
            title="ReAct模式"
          >
            <BrainCircuit className="w-3.5 h-3.5" />
          </button>
          <button onClick={onClose} className="p-1 rounded hover:bg-dark-hover">
            <X className="w-4 h-4 text-gray-400" />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-gray-600">
            <Zap className="w-8 h-8 mb-2" />
            <p className="text-xs">发送消息开始测试 Agent</p>
            <p className="text-[10px] mt-1">{reactMode ? 'ReAct 模式：Thought→Action→Observation' : '快速模式：直接 LLM 回复'}</p>
          </div>
        )}
        <AnimatePresence>
          {messages.map((msg, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className={`flex gap-2 ${msg.role === 'user' ? 'justify-end' : ''}`}
            >
              {msg.role !== 'user' && (
                <div className="flex-shrink-0 mt-1">
                  {msg.role === 'assistant' ? <Bot className="w-4 h-4 text-blue-400" /> : <Eye className="w-4 h-4 text-amber-400" />}
                </div>
              )}
              <div className={`max-w-[85%] rounded-lg px-3 py-2 text-xs ${
                msg.role === 'user'
                  ? 'bg-blue-500/15 text-blue-100 rounded-br-sm'
                  : msg.role === 'system'
                  ? 'bg-amber-500/10 text-amber-200 rounded-bl-sm'
                  : 'bg-dark-bg border border-dark-border text-gray-300 rounded-bl-sm'
              }`}>
                <div className="whitespace-pre-wrap break-words">{msg.content?.slice(0, 2000)}</div>
                {msg.steps !== undefined && msg.steps > 0 && (
                  <div className="flex items-center gap-2 mt-1 pt-1 border-t border-dark-border/50">
                    <span className="text-[10px] text-gray-500">{msg.steps}步 · {msg.model} · {msg.duration}ms</span>
                  </div>
                )}
              </div>
              {msg.role === 'user' && (
                <div className="flex-shrink-0 mt-1">
                  <User className="w-4 h-4 text-gray-400" />
                </div>
              )}
            </motion.div>
          ))}
        </AnimatePresence>
        {sending && (
          <div className="flex gap-2">
            <Bot className="w-4 h-4 text-blue-400 mt-1" />
            <div className="bg-dark-bg border border-dark-border rounded-lg px-3 py-2 text-xs text-gray-500">
              <Loader2 className="w-3 h-3 animate-spin inline mr-1" />
              思考中...
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="px-3 py-2 border-t border-dark-border">
        <div className="flex items-center gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入消息测试 Agent..."
            disabled={sending}
            className="flex-1 h-8 px-3 bg-dark-bg border border-dark-border rounded-lg text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:border-primary/40"
          />
          <button
            onClick={handleSend}
            disabled={sending || !input.trim()}
            className="p-1.5 rounded-lg bg-primary/20 text-primary hover:bg-primary/30 disabled:opacity-30 transition-colors"
          >
            <Send className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
      </motion.div>
    </motion.div>
  );
};

export default ChatPanel;
