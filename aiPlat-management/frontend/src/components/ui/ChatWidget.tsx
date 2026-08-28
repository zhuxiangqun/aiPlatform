import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Send, Loader2 } from 'lucide-react';
import { Button, Textarea } from '../ui';

interface ChatMessage {
  role: string;
  content: string;
}

interface ChatWidgetProps {
  title?: string;
  initialMessage?: string;
  initialMessages?: ChatMessage[];
  placeholder?: string;
  onSend: (message: string) => Promise<string>;
  className?: string;
  maxHeight?: string;
}

export const ChatWidget: React.FC<ChatWidgetProps> = ({
  title = 'AI',
  initialMessage,
  initialMessages = [],
  placeholder = '输入消息...',
  onSend,
  className = '',
  maxHeight = '60vh',
}) => {
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [autoSent, setAutoSent] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const prevLenRef = useRef(messages.length);

  // Scroll to bottom on new messages only (not on every render).
  // requestAnimationFrame defers the layout read/write out of the React commit
  // phase — avoids the "[Violation] Forced reflow" triggered by synchronous
  // smooth scrollIntoView right after DOM mutation (68ms reflows on chat apps).
  useEffect(() => {
    const prevLen = prevLenRef.current;
    prevLenRef.current = messages.length;
    if (messages.length <= prevLen) return;
    const raf = requestAnimationFrame(() => {
      const el = scrollContainerRef.current;
      if (el) el.scrollTop = el.scrollHeight; // direct assignment: no smooth animation, no reflow cascade
    });
    return () => cancelAnimationFrame(raf);
  }, [messages.length]);

  // Auto-send initial message
  useEffect(() => {
    if (initialMessage && !autoSent && messages.length === 0) {
      setAutoSent(true);
      send(initialMessage);
    }
  }, [initialMessage, autoSent, messages.length]);

  // Update from external initialMessages
  useEffect(() => {
    if (initialMessages.length > 0 && messages.length === 0) {
      setMessages(initialMessages);
    }
  }, [initialMessages]);

  const send = async (msg: string) => {
    if (!msg.trim()) return;
    setSending(true);
    const userMsg = { role: 'user', content: msg };
    setMessages((prev) => [...prev, userMsg]);
    try {
      const reply = await onSend(msg);
      setMessages((prev) => [...prev, { role: 'assistant', content: reply }]);
    } catch {
      setMessages((prev) => [...prev, { role: 'assistant', content: '发送失败，请重试' }]);
    } finally {
      setSending(false);
    }
  };

  const handleSend = useCallback(() => {
    const msg = input.trim();
    if (!msg) return;
    setInput('');
    send(msg);
  }, [input]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  return (
    <div className={`flex flex-col ${className}`}>
      <div ref={scrollContainerRef} className="flex-1 overflow-y-auto p-4 space-y-3" style={{ maxHeight }}>
        {messages.map((m, i) => (
          <div key={i} className={`p-3 rounded-lg border ${
            m.role === 'assistant' ? 'border-primary/30 bg-primary/5' : 'border-dark-border bg-dark-card'
          }`}>
            <div className="text-xs font-semibold mb-1 text-gray-400">
              {m.role === 'assistant' ? title : '你'}
            </div>
            <div className="text-sm text-gray-100 whitespace-pre-wrap break-words">{m.content}</div>
          </div>
        ))}
        {sending && (
          <div className="p-3 rounded-lg border border-primary/30 bg-primary/5">
            <div className="flex items-center gap-2 text-sm text-gray-400">
              <Loader2 className="w-4 h-4 animate-spin" />思考中...
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>
      <div className="p-4 border-t border-dark-border">
        <div className="flex gap-2">
          <Textarea
            value={input}
            onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            rows={2}
            className="flex-1"
          />
          <Button variant="primary" onClick={handleSend} loading={sending} icon={<Send className="w-4 h-4" />} />
        </div>
      </div>
    </div>
  );
};
