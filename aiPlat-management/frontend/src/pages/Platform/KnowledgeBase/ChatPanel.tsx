import React, { useEffect, useRef, useState } from 'react';
import { Button, Textarea, toast } from '../../../components/ui';

interface ChatPanelProps {
  onClose?: () => void;
  wikiTitles?: string[];
  label?: string;
}

export const ChatPanel: React.FC<ChatPanelProps> = ({ onClose, wikiTitles, label = 'Wiki 问答' }) => {
  const [messages, setMessages] = useState<any[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [streamingText, setStreamingText] = useState('');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const titles = wikiTitles || [];

  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, streamingText]);

  useEffect(() => {
    if (sessionId) return;
    createSession();
  }, [titles.join(',')]);

  const createSession = async () => {
    try {
      const scope = titles.length > 0
        ? { wiki_titles: titles, version: 1 }
        : { wiki_titles: [], version: 1 };
      const res = await fetch('/api/platform/conversations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scope, title: titles.length > 0 ? titles[0].slice(0, 30) : 'Wiki知识库' }),
      });
      const data = await res.json();
      setSessionId(data.session_id || data.id);
    } catch { toast.error('创建会话失败'); }
  };

  const handleSend = async () => {
    const text = input.trim();
    if (!text) return;
    if (!sessionId) { toast.error('会话未创建'); return; }
    setSending(true);
    setInput('');
    setStreamingText('');
    setMessages(prev => [...prev, { role: 'user', content: text }]);

    try {
      const resp = await fetch(`/api/platform/conversations/${sessionId}/query/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, scope_override: { wiki_titles: titles, version: 1 } }),
      });
      const reader = resp.body?.getReader();
      if (!reader) throw new Error('No reader');
      const decoder = new TextDecoder();
      let buffer = '', fullAnswer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.error) {
                setMessages(prev => [...prev, { role: 'assistant', content: `⚠️ ${data.error === 'no_document_content' ? '未找到相关知识' : data.error}` }]);
                break;
              }
              if (data.text) { fullAnswer += data.text; setStreamingText(fullAnswer); }
              if (data.done) {
                fullAnswer = data.answer || fullAnswer || '(无回复内容)';
                setStreamingText('');
                if (fullAnswer) setMessages(prev => [...prev, { role: 'assistant', content: fullAnswer }]);
              }
            } catch {}
          }
        }
      }
    } catch (e: any) {
      setMessages(prev => [...prev, { role: 'assistant', content: '网络错误，请重试' }]);
    } finally {
      setSending(false); setStreamingText('');
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-3 border-b border-dark-border flex-shrink-0">
        <div>
          <span className="text-sm font-medium text-gray-100">{label}</span>
          {titles.length > 0 && <span className="ml-2 text-xs text-gray-500">基于 {titles.length} 个知识页面</span>}
          {titles.length === 0 && <span className="ml-2 text-xs text-gray-500">全部 Wiki 知识</span>}
        </div>
        {onClose && (
          <button onClick={onClose} className="w-6 h-6 rounded flex items-center justify-center text-gray-400 hover:text-gray-200 hover:bg-dark-hover transition-colors">✕</button>
        )}
      </div>

      <div className="flex-1 overflow-auto px-4 py-3 space-y-4 min-h-0">
        {messages.length === 0 && !streamingText && (
          <div className="text-center py-12 text-gray-500">
            <div className="text-lg mb-1">👋</div>
            <div className="text-sm">向我提问吧</div>
            <div className="text-xs mt-1 text-gray-600">基于 Wiki 知识库回答你的问题</div>
          </div>
        )}
        {messages.map((msg, idx) => (
          <div key={idx} className={`flex gap-2 ${msg.role === 'assistant' ? '' : 'flex-row-reverse'}`}>
            <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs flex-shrink-0 ${msg.role === 'assistant' ? 'bg-primary/20 text-primary' : 'bg-dark-hover text-gray-300'}`}>
              {msg.role === 'assistant' ? 'AI' : '我'}
            </div>
            <div className={`flex-1 min-w-0 rounded-2xl px-4 py-2.5 ${msg.role === 'assistant' ? 'bg-dark-bg border border-dark-border' : 'bg-primary/10 border border-primary/20'}`}>
              <div className="text-sm text-gray-100 whitespace-pre-wrap break-words leading-relaxed">{String(msg.content || '')}</div>
            </div>
          </div>
        ))}
        {streamingText && (
          <div className="flex gap-2">
            <div className="w-7 h-7 rounded-full bg-primary/20 text-primary flex items-center justify-center text-xs flex-shrink-0">AI</div>
            <div className="flex-1 rounded-2xl px-4 py-2.5 bg-dark-bg border border-dark-border">
              <div className="text-sm text-gray-100 whitespace-pre-wrap break-words leading-relaxed">{streamingText}<span className="animate-pulse ml-0.5">▊</span></div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="px-4 py-3 border-t border-dark-border flex-shrink-0">
        <div className="flex gap-2 items-end">
          <Textarea rows={2} value={input} onChange={(e) => setInput(e.target.value)} placeholder="输入问题..." className="flex-1"
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }} />
          <Button variant="primary" loading={sending} onClick={handleSend} className="flex-shrink-0">发送</Button>
        </div>
      </div>
    </div>
  );
};
