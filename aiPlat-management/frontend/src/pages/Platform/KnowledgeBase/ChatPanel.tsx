import React, { useEffect, useRef, useState } from 'react';
import { Button, Textarea, toast } from '../../../components/ui';
import { useKBStore } from '../../../stores';

export const ChatPanel: React.FC<{ onClose?: () => void }> = ({ onClose }) => {
  const messages = useKBStore(s => s.messages);
  const appendMessage = useKBStore(s => s.appendMessage);
  const selectedDocIds = useKBStore(s => s.selectedDocIds);
  const conversation = useKBStore(s => s.conversation);
  const chatLoading = useKBStore(s => s.chatLoading);
  const createConversation = useKBStore(s => s.createConversation);
  const sendMessage = useKBStore(s => s.sendMessage);

  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [streamingText, setStreamingText] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const selIds = Array.from(selectedDocIds);

  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, streamingText]);

  const handleCreateOrContinue = async () => {
    if (selIds.length === 0) return;
    if (conversation && conversation.scope?.doc_ids?.join(',') === selIds.join(',')) return;
    await createConversation(selIds, '资料对话');
  };

  useEffect(() => {
    if (selIds.length === 0) return;
    handleCreateOrContinue();
  }, [selIds.join(',')]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text) return;
    if (!conversation?.session_id) { toast.error('请先选中资料'); return; }
    setSending(true);
    setInput('');
    setStreamingText('');
    appendMessage({ role: 'user', content: text });

    try {
      const resp = await fetch(`/api/platform/conversations/${conversation.session_id}/query/stream`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: text }),
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
                appendMessage({ role: 'assistant', content: `⚠️ ${data.error === 'no_document_content' ? '未找到相关资料' : data.error}` });
                break;
              }
              if (data.text) { fullAnswer += data.text; setStreamingText(fullAnswer); }
              if (data.done) {
                fullAnswer = data.answer || fullAnswer || '(无回复内容)';
                setStreamingText('');
                if (fullAnswer) appendMessage({ role: 'assistant', content: fullAnswer });
              }
            } catch {}
          }
        }
      }
    } catch (e: any) {
      if (e.name !== 'AbortError') { try { await sendMessage(text); } catch {} }
    } finally {
      setSending(false); setStreamingText('');
    }
  };

  if (selIds.length === 0 && !conversation) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gray-500 p-8">
        <div className="text-4xl mb-3">💬</div>
        <div className="text-sm">选中文档后开始对话</div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-3 border-b border-dark-border flex-shrink-0">
        <div>
          <span className="text-sm font-medium text-gray-100">AI 资料助手</span>
          {selIds.length > 0 && <span className="ml-2 text-xs text-gray-500">基于 {selIds.length} 份资料</span>}
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
            <div className="text-xs mt-1 text-gray-600">比如"总结这些资料"或"对比核心观点"</div>
          </div>
        )}
        {messages.map((msg: any, idx: number) => (
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
          <Button variant="primary" loading={sending || chatLoading} onClick={handleSend} className="flex-shrink-0">发送</Button>
        </div>
      </div>
    </div>
  );
};
