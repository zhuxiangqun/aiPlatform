import React, { useEffect, useRef, useState } from 'react';
import { Button, Textarea, toast } from '../../../components/ui';
import { PipelineTrace } from '../../../components/wiki/PipelineTrace';
import GrillPanel from '../../../components/grilling/GrillPanel';

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
  const [reasoningPaths, setReasoningPaths] = useState<Record<number, any[]>>({});
  const [expandedPath, setExpandedPath] = useState<number | null>(null);
  const [retrievalTags, setRetrievalTags] = useState<Record<number, string>>({});
  const [qualityTags, setQualityTags] = useState<Record<number, string>>({});
  const [pipelineTraces, setPipelineTraces] = useState<Record<number, any[]>>({});
  const [domainIds, setDomainIds] = useState<Record<number, string>>({});
  const [domainNames, setDomainNames] = useState<Record<number, string>>({});
  const [feedbacks, setFeedbacks] = useState<Record<number, 'like' | 'dislike'>>({});
  const [showGrill, setShowGrill] = useState(false);
  const [grillDomain, setGrillDomain] = useState('');
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
        body: JSON.stringify({ scope, title: titles.length > 0 ? titles[0].slice(0, 30) : 'Wiki知识库', agent_type: 'materials_chat' }),
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
                const msgIdx = messages.length + (fullAnswer ? 1 : 0);
                if (data.reasoning_path) {
                  setReasoningPaths(prev => ({ ...prev, [msgIdx]: data.reasoning_path }));
                }
                // Detect retrieval path for status indicator
                if (data.strategy || data.mode) {
                  const tag = data.strategy || data.mode || '';
                  setRetrievalTags(prev => ({ ...prev, [msgIdx]: tag }));
                }
                if (data.quality) {
                  setQualityTags(prev => ({ ...prev, [msgIdx]: data.quality }));
                }
                if (data.pipeline_trace) {
                  setPipelineTraces(prev => ({ ...prev, [msgIdx]: data.pipeline_trace }));
                }
                if (data.domain_id) {
                  setDomainIds(prev => ({ ...prev, [msgIdx]: data.domain_id }));
                  setDomainNames(prev => ({ ...prev, [msgIdx]: data.domain_name || data.domain_id }));
                }
                // v2.9: auto-show GrillPanel when backend suggests clarification
                if (data.grill_suggested) {
                  setGrillDomain(data.domain_id || 'ai-knowledge');
                  setShowGrill(true);
                }
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
              {msg.role === 'assistant' && (
                <div className="flex items-center gap-2 mt-1.5">
                  {retrievalTags[idx] && (
                    <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                      retrievalTags[idx] === 'direct_retrieve' ? 'bg-blue-900/30 text-blue-300' :
                      retrievalTags[idx] === 'hyde' ? 'bg-purple-900/30 text-purple-300' :
                      'bg-gray-800 text-gray-400'
                    }`}>
                      🔍 {retrievalTags[idx]}
                    </span>
                  )}
                  {qualityTags[idx] && qualityTags[idx] !== 'ok' && (
                    <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                      qualityTags[idx] === 'low_evidence' ? 'bg-red-900/30 text-red-300' : 'bg-yellow-900/30 text-yellow-300'
                    }`}>
                      ⚠️ {qualityTags[idx]}
                    </span>
                  )}
                  {domainNames[idx] && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-green-900/25 text-green-300 border border-green-800/40">
                      📍 {domainNames[idx]}
                    </span>
                  )}
                  {domainIds[idx] && !domainNames[idx] && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-green-900/25 text-green-300 border border-green-800/40">
                      📍 {domainIds[idx]}
                    </span>
                  )}
                  {!feedbacks[idx] && (
                    <>
                      <button className="text-[10px] px-1 rounded hover:bg-green-900/30"
                        onClick={() => {
                          setFeedbacks(f => ({...f, [idx]: 'like'}));
                          fetch('/api/core/engine/feedback', {
                            method: 'POST', headers: {'Content-Type':'application/json'},
                            body: JSON.stringify({session_id: sessionId, query: msg.content?.slice(0,100), is_helpful: true, domain_id: domainIds[idx] || 'default'}),
                          }).catch(()=>{});
                        }}>👍</button>
                      <button className="text-[10px] px-1 rounded hover:bg-red-900/30"
                        onClick={() => {
                          setFeedbacks(f => ({...f, [idx]: 'dislike'}));
                          fetch('/api/core/engine/feedback', {
                            method: 'POST', headers: {'Content-Type':'application/json'},
                            body: JSON.stringify({session_id: sessionId, query: msg.content?.slice(0,100), is_helpful: false, domain_id: domainIds[idx] || 'default'}),
                          }).catch(()=>{});
                        }}>👎</button>
                    </>
                  )}
                  {feedbacks[idx] && (
                    <span className="text-[10px] text-gray-500">{feedbacks[idx] === 'like' ? '👍' : '👎'}</span>
                  )}
                  {reasoningPaths[idx]?.length > 0 && (
                    <button
                      className="text-[10px] text-purple-400 hover:text-purple-300 flex items-center gap-1"
                      onClick={() => setExpandedPath(expandedPath === idx ? null : idx)}
                    >
                      📊 推理路径 ({reasoningPaths[idx].length}步)
                      <span className="text-gray-500">{expandedPath === idx ? '▲' : '▼'}</span>
                    </button>
                  )}
                </div>
              )}
              {msg.role === 'assistant' && reasoningPaths[idx]?.length > 0 && expandedPath === idx && (
                    <div className="mt-1 space-y-0.5 pl-1">
                      {reasoningPaths[idx].map((step: any, si: number) => (
                        <div key={si} className="flex items-center gap-1 text-[10px]">
                          <span className="text-gray-500 w-4">{step.step}.</span>
                          <span className="text-gray-400 truncate max-w-[120px]">{step.from?.slice(0, 30)}</span>
                          <span className="text-purple-500 mx-0.5">─[{step.via}]→</span>
                          <span className="text-gray-300 truncate max-w-[120px]">{step.to?.slice(0, 30) || step.relation_label || '-'}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  <PipelineTrace trace={pipelineTraces[idx]} />
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

      {/* v2.9: GrillingBridge — auto-triggered when KB Q&A confidence is low */}
      {showGrill && (
        <GrillPanel
          mode="modal"
          entryPoint="kb_qa"
          domainId={grillDomain}
          title="知识库需求澄清"
          onComplete={() => {
            setShowGrill(false);
            toast.success('需求已澄清，请重新提问');
          }}
          onClose={() => setShowGrill(false)}
        />
      )}
      </div>
  );
};
