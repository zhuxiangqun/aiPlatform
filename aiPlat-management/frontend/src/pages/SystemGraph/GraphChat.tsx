import React, { useState, useRef, useEffect } from 'react';
import { Send, X, Loader2 } from 'lucide-react';

interface Props {
  onClose: () => void;
}

const QUICK_QUESTIONS = [
  '最复杂的模块是哪个？',
  '哪些文件耦合度最高？',
  '系统的循环依赖有哪些？',
];

const GraphChat: React.FC<Props> = ({ onClose }) => {
  const [messages, setMessages] = useState<{ role: string; content: string }[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  const sendMessage = async (text: string) => {
    if (!text.trim() || loading) return;
    const userMsg = { role: 'user', content: text };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const r = await fetch('/api/core/knowledge-graph/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: text, history: messages }),
      });
      const reader = r.body?.getReader();
      if (!reader) throw new Error('No reader');

      setMessages(prev => [...prev, { role: 'assistant', content: '' }]);
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (line.startsWith('data: ') && line !== 'data: [DONE]') {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.token) {
                setMessages(prev => {
                  const copy = [...prev];
                  copy[copy.length - 1] = { ...copy[copy.length - 1], content: copy[copy.length - 1].content + data.token };
                  return copy;
                });
              }
            } catch { }
          }
        }
      }
    } catch { }
    finally { setLoading(false); }
  };

  return (
    <div className="h-64 shrink-0 border-t border-dark-border bg-dark-card flex flex-col">
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-dark-border">
        <span className="text-xs font-medium text-gray-200">向系统图谱提问</span>
        <button onClick={onClose} className="p-0.5 rounded text-gray-400 hover:text-gray-200">
          <X className="w-3 h-3" />
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-2">
        {messages.length === 0 && (
          <div className="text-xs text-gray-500">
            <div className="mb-2">💡 试试这些问题：</div>
            <div className="flex flex-wrap gap-1">
              {QUICK_QUESTIONS.map((q, i) => (
                <button
                  key={i}
                  onClick={() => sendMessage(q)}
                  className="px-2 py-1 rounded text-[10px] bg-dark-bg border border-dark-border text-gray-400 hover:text-gray-200 hover:border-primary/30"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`text-xs ${msg.role === 'user' ? 'text-right' : ''}`}>
            <div className={`inline-block px-2 py-1 rounded-lg max-w-[85%] ${
              msg.role === 'user'
                ? 'bg-primary/20 text-gray-200'
                : 'bg-dark-bg border border-dark-border text-gray-300'
            }`}>
              {msg.content || (loading && i === messages.length - 1 ? <Loader2 className="w-3 h-3 animate-spin inline" /> : '')}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="px-3 py-2 border-t border-dark-border flex items-center gap-2">
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(input); } }}
          placeholder="问这个代码库..."
          className="flex-1 bg-dark-bg border border-dark-border rounded px-2 py-1 text-xs text-gray-200 outline-none focus:border-primary/50"
          disabled={loading}
        />
        <button
          onClick={() => sendMessage(input)}
          disabled={loading || !input.trim()}
          className="p-1.5 rounded bg-primary/20 text-primary hover:bg-primary/30 disabled:opacity-30"
        >
          <Send className="w-3 h-3" />
        </button>
      </div>
    </div>
  );
};

export default GraphChat;
