import React, { useEffect, useRef, useState } from 'react';
import { Button, Modal, Textarea, toast } from '../ui';
import { toolApi } from '../../services';
import AssetBoundaryHint from './AssetBoundaryHint';

type Msg = { role: 'user' | 'assistant'; content: string };
type Draft = {
  name?: string;
  display_name?: string;
  description?: string;
  code?: string;
  category?: string;
  warning?: string;
};

export interface ToolChatCreateModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

const WELCOME =
  '你好。用自然语言描述要创建的 Tool，例如：「把 Markdown 转成 HTML，输入 md 字符串，返回 html，不联网」。我会追问后生成代码草稿供你确认。';

const ToolChatCreateModal: React.FC<ToolChatCreateModalProps> = ({ open, onClose, onSuccess }) => {
  const [conversation, setConversation] = useState<Msg[]>([{ role: 'assistant', content: WELCOME }]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [preview, setPreview] = useState('');
  const [boundaryHints, setBoundaryHints] = useState<string[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    setConversation([{ role: 'assistant', content: WELCOME }]);
    setInput('');
    setDraft(null);
    setPreview('');
    setBoundaryHints([]);
    setLoading(false);
    setCreating(false);
  }, [open]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [conversation, draft, loading]);

  const send = async () => {
    const text = input.trim();
    if (!text || loading || creating) return;
    const history = conversation.map((m) => ({ role: m.role, content: m.content }));
    const nextConv: Msg[] = [...conversation, { role: 'user', content: text }];
    setConversation(nextConv);
    setInput('');
    setLoading(true);
    setDraft(null);
    setPreview('');
    setBoundaryHints([]);
    try {
      const res = await toolApi.createDialog({ text, history });
      if ((res as any)?.error && !(res as any)?.next) {
        toast.error('对话失败', String((res as any).error));
        setConversation([...nextConv, { role: 'assistant', content: '出错了，请换种说法再试。' }]);
        return;
      }
      let assistantText = String(res.reply || '').trim() || '（无回复）';
      const qs = Array.isArray(res.questions) ? res.questions.filter(Boolean) : [];
      if (qs.length > 0 && res.next === 'ask') {
        assistantText += '\n\n' + qs.map((q, i) => `${i + 1}. ${q}`).join('\n');
      }
      setConversation([...nextConv, { role: 'assistant', content: assistantText }]);
      if (res.next === 'draft' && res.draft && typeof res.draft === 'object') {
        setDraft(res.draft as Draft);
        setPreview(String(res.tool_code_preview || ''));
        setBoundaryHints(Array.isArray((res as any).boundary_hints) ? (res as any).boundary_hints.map(String) : []);
      }
    } catch (e: any) {
      toast.error('对话失败', e?.detail || e?.message || String(e));
      setConversation([...nextConv, { role: 'assistant', content: '网络或服务异常，请稍后重试。' }]);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    if (!draft?.code?.trim() || !draft?.name?.trim()) {
      toast.warning('草稿缺少名称或代码');
      return;
    }
    setCreating(true);
    try {
      await toolApi.create({
        name: String(draft.name).trim(),
        description: String(draft.description || draft.display_name || '').trim(),
        code: String(draft.code).trim(),
      });
      toast.success('Tool 已创建', String(draft.display_name || draft.name));
      onSuccess();
      onClose();
    } catch (e: any) {
      toast.error('创建失败', e?.detail || e?.message || String(e));
    } finally {
      setCreating(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="对话创建 Tool"
      width={720}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={creating}>取消</Button>
          {draft && (
            <Button variant="primary" onClick={handleCreate} loading={creating} disabled={loading}>
              确认创建
            </Button>
          )}
        </>
      }
    >
      <div className="flex flex-col gap-3" style={{ maxHeight: '70vh' }}>
        <div className="text-xs text-gray-500">多轮澄清 → 生成 TOOL_DEF 草稿 → 确认后写入 ~/.aiplat/tools</div>
        <AssetBoundaryHint kind="tool" />
        <div className="flex-1 overflow-y-auto space-y-3 border border-dark-border rounded-lg p-3 bg-dark-bg min-h-[240px]">
          {conversation.map((m, i) => (
            <div
              key={i}
              className={`text-sm whitespace-pre-wrap rounded-lg px-3 py-2 ${
                m.role === 'user'
                  ? 'bg-primary/15 text-gray-100 ml-8'
                  : 'bg-dark-card text-gray-300 mr-8 border border-dark-border'
              }`}
            >
              <div className="text-[10px] text-gray-500 mb-1">{m.role === 'user' ? '你' : 'Tool 顾问'}</div>
              {m.content}
            </div>
          ))}
          {loading && <div className="text-xs text-gray-500 px-1">思考中…</div>}
          <div ref={bottomRef} />
        </div>
        {draft && (
          <div className="border border-dark-border rounded-lg p-3 space-y-2 bg-dark-card">
            <div className="text-sm text-gray-200 font-medium">草稿预览</div>
            <div className="text-xs text-gray-400 grid grid-cols-2 gap-1">
              <div>名称：{draft.display_name || draft.name}</div>
              <div>ID：{draft.name}</div>
              <div>分类：{draft.category || '-'}</div>
            </div>
            <Textarea label="代码预览" rows={10} value={preview || draft.code || ''} readOnly />
            {draft.warning ? <div className="text-xs text-amber-500">{draft.warning}</div> : null}
            {boundaryHints.length > 0 && (
              <div className="text-xs text-amber-400 space-y-1">
                <div>边界提示：</div>
                {boundaryHints.map((h, i) => (
                  <div key={i}>· {h}</div>
                ))}
              </div>
            )}
          </div>
        )}
        <div className="flex gap-2 items-end">
          <div className="flex-1">
            <Textarea
              rows={3}
              value={input}
              onChange={(e: any) => setInput(e.target.value)}
              placeholder="描述需求，或回答上面的问题…"
              onKeyDown={(e: any) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
            />
          </div>
          <Button variant="primary" onClick={send} loading={loading} disabled={!input.trim() || creating}>
            发送
          </Button>
        </div>
      </div>
    </Modal>
  );
};

export default ToolChatCreateModal;
