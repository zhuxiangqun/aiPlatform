import { useEffect, useRef, useState } from 'react';
import { Send, X } from 'lucide-react';

interface Msg {
  role: string;
  content: string;
}

interface StructuredResult {
  type: string;
  root_cause: string;
  severity: string;
}

interface ClarifyResult {
  conversation: Msg[];
  summary: string;
  structured: StructuredResult;
}

interface ClarifyDialogProps {
  open: boolean;
  onClose: () => void;
  context: string;              // "feedback" | "diagnosis" | "poc"
  title: string;                // dialog title
  placeholder?: string;         // input placeholder
  extra?: Record<string, string>;
  onSubmit: (result: ClarifyResult) => void;
}

const API = (path: string) => `/api/platform/apps/fde${path}`;

const ClarifyDialog: React.FC<ClarifyDialogProps> = ({
  open, onClose, context, title, placeholder = '描述你遇到的问题…',
  extra, onSubmit,
}) => {
  const [conversation, setConversation] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [state, setState] = useState<'idle' | 'loading' | 'done'>('idle');
  const [summary, setSummary] = useState('');
  const [structured, setStructured] = useState<StructuredResult>({ type: '', root_cause: '', severity: 'medium' });
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [conversation]);

  const send = async () => {
    const text = input.trim();
    if (!text) return;
    const newConv: Msg[] = [...conversation, { role: 'user', content: text }];
    setConversation(newConv);
    setInput('');
    setState('loading');

    try {
      const res = await fetch(API('/clarify'), {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ context, text, history: newConv, extra: extra || {} }),
      });
      const data = await res.json();

      if (data.next === 'done') {
        const s = data.structured || {};
        if (s.type === 'pending') {
          // LLM unavailable — don't echo back as AI bubble, just go to submit
          setSummary(data.summary || text);
        } else {
          setConversation([...newConv, { role: 'assistant', content: data.summary || text }]);
          setSummary(data.summary || text);
        }
        setStructured({ type: s.type || '', root_cause: s.root_cause || '', severity: s.severity || 'medium' });
        setState('done');
      } else {
        const aiMsg = (data.questions || ['请再详细描述一下']).join('\n');
        setConversation([...newConv, { role: 'assistant', content: aiMsg }]);
        setState('idle');
      }
    } catch {
      // Network error — skip AI bubble, go straight to submit
      setSummary(text);
      setStructured({ type: 'pending', root_cause: '', severity: 'medium' });
      setState('done');
    }
  };

  const handleSubmit = () => {
    onSubmit({ conversation, summary, structured });
    onClose();
    setConversation([]);
    setInput('');
    setState('idle');
    setSummary('');
  };

  const [showSkipConfirm, setShowSkipConfirm] = useState(false);

  const skip = () => {
    const content = input.trim() || '（跳过澄清，仅记录上下文）';
    onSubmit({ conversation: [{ role: 'user', content }], summary: content, structured: { type: 'skipped', root_cause: '', severity: 'low' } });
    onClose();
    setConversation([]);
    setInput('');
    setState('idle');
    setShowSkipConfirm(false);
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[10vh] bg-black/60">
      <div className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-md mx-4 flex flex-col max-h-[80vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-700/50 shrink-0">
          <h3 className="text-sm font-semibold text-gray-200">{title}</h3>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300"><X className="w-4 h-4" /></button>
        </div>

        {/* Extra info */}
        {extra && Object.keys(extra).some(k => extra[k]) && (
          <div className="px-5 py-2 shrink-0 flex flex-wrap gap-1.5">
            {Object.entries(extra).filter(([k, v]) => v && !k.startsWith('_')).map(([k, v]) => (
              <span key={k} className="text-xs text-gray-500 bg-gray-800 px-2 py-0.5 rounded">{v}</span>
            ))}
          </div>
        )}

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-5 py-3 space-y-3 min-h-[180px] max-h-[400px]">
          {conversation.length === 0 && (
            <div className="text-xs text-gray-500 text-center py-6">
              描述你遇到的问题，AI 会追问帮你澄清
            </div>
          )}
          {conversation.map((msg, i) => (
            <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[85%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap ${
                msg.role === 'user' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-200 border border-gray-700'
              }`}>
                <span className="text-[10px] opacity-60 block mb-0.5">
                  {msg.role === 'user' ? '😶' : '🤖'} {msg.role === 'user' ? 'FDE' : 'AI'}
                </span>
                {msg.content}
              </div>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        {/* Input / Submit */}
        <div className="px-5 py-3 border-t border-gray-700/50 shrink-0 space-y-3">
          {state !== 'done' ? (
            state === 'loading' ? (
              <div className="flex items-center justify-center py-3 gap-2 text-sm text-gray-400">
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-400" />
                思考中…
              </div>
            ) : (
            <div className="flex gap-2">
              <input
                className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500"
                value={input} onChange={e => setInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && state === 'idle') { e.preventDefault(); send(); } }}
                placeholder={placeholder}
                autoFocus
              />
              <button onClick={send} disabled={!input.trim()}
                className="px-3 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg disabled:opacity-50">
                <Send className="w-4 h-4" />
              </button>
            </div>)
          ) : (
            <div className="space-y-2">
              {structured.root_cause && (
                <div className="text-xs text-gray-400 space-y-1">
                  <div>类型：<span className="text-yellow-400">{structured.type || '—'}</span></div>
                  <div>根因：<span className="text-yellow-400">{structured.root_cause}</span></div>
                  <div>严重：<span className={structured.severity === 'high' ? 'text-red-400' : structured.severity === 'medium' ? 'text-yellow-400' : 'text-green-400'}>{structured.severity || '—'}</span></div>
                </div>
              )}
              <p className="text-[10px] text-gray-500 text-center">AI 已澄清完成，确认后保存到反馈记录</p>
              <button onClick={handleSubmit}
                className="w-full px-3 py-2 bg-green-600 hover:bg-green-500 text-white rounded-lg text-sm font-medium">
                提交澄清结果
              </button>
            </div>
          )}

          {state === 'idle' && conversation.length === 0 && (
            showSkipConfirm ? (
              <div className="flex gap-2 items-center">
                <span className="text-xs text-yellow-400">提交空反馈仅记录上下文，确认？</span>
                <button onClick={skip} className="text-xs text-green-400 hover:text-green-300 font-medium">确认</button>
                <button onClick={() => setShowSkipConfirm(false)} className="text-xs text-gray-500 hover:text-gray-400">取消</button>
              </div>
            ) : (
              <button onClick={() => setShowSkipConfirm(true)} className="w-full text-xs text-gray-600 hover:text-gray-400 py-1">
                跳过澄清，直接提交
              </button>
            )
          )}
        </div>
      </div>
    </div>
  );
};

export default ClarifyDialog;
