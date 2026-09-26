import React, { useEffect, useRef, useState } from 'react';
import { Button, Modal, Textarea, toast } from '../ui';
import { builderTeamApi, type AgentCatalogItem, type PipelineStageConfig } from '../../services';
import AssetBoundaryHint from './AssetBoundaryHint';

type Msg = { role: 'user' | 'assistant'; content: string };
type Draft = {
  name?: string;
  display_name?: string;
  description?: string;
  stages?: PipelineStageConfig[];
};

export interface TeamChatCreateModalProps {
  open: boolean;
  onClose: () => void;
  /** Apply draft into canvas (does not auto-save). */
  onApplyDraft: (draft: { name: string; description: string; stages: PipelineStageConfig[] }) => void;
}

const WELCOME =
  '你好。描述要组装的团队流水线，例如：「先产品澄清，再架构设计，最后实现与测试，架构后需人工审批」。我会按可用 Agent 目录生成阶段草稿，确认后写入画布。';

const TeamChatCreateModal: React.FC<TeamChatCreateModalProps> = ({ open, onClose, onApplyDraft }) => {
  const [conversation, setConversation] = useState<Msg[]>([{ role: 'assistant', content: WELCOME }]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [preview, setPreview] = useState('');
  const [agents, setAgents] = useState<AgentCatalogItem[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    setConversation([{ role: 'assistant', content: WELCOME }]);
    setInput('');
    setDraft(null);
    setPreview('');
    setLoading(false);
    setApplying(false);
    (async () => {
      try {
        const res = await builderTeamApi.listAgents();
        setAgents(res.agents || []);
      } catch {
        setAgents([]);
      }
    })();
  }, [open]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [conversation, draft, loading]);

  const send = async () => {
    const text = input.trim();
    if (!text || loading || applying) return;
    const history = conversation.map((m) => ({ role: m.role, content: m.content }));
    const nextConv: Msg[] = [...conversation, { role: 'user', content: text }];
    setConversation(nextConv);
    setInput('');
    setLoading(true);
    setDraft(null);
    setPreview('');
    try {
      const res = await builderTeamApi.createDialog({
        text,
        history,
        agents: agents.map((a) => ({
          agent_id: a.agent_id,
          display_name: a.display_name,
          description: a.description,
          category: a.category,
          tags: a.tags,
          phase: a.phase,
          output_artifact: a.output_artifact,
          hitl_phase: a.hitl_phase,
        })),
      });
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
        setPreview(String(res.team_preview || ''));
      }
    } catch (e: any) {
      toast.error('对话失败', e?.detail || e?.message || String(e));
      setConversation([...nextConv, { role: 'assistant', content: '网络或服务异常，请稍后重试。' }]);
    } finally {
      setLoading(false);
    }
  };

  const handleApply = () => {
    if (!draft?.stages?.length) {
      toast.warning('草稿没有可用阶段');
      return;
    }
    setApplying(true);
    try {
      onApplyDraft({
        name: String(draft.display_name || draft.name || '未命名团队').trim(),
        description: String(draft.description || '').trim(),
        stages: draft.stages,
      });
      toast.success('已写入画布', '可继续拖拽调整后点保存');
      onClose();
    } finally {
      setApplying(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="对话组装团队"
      width={720}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={applying}>取消</Button>
          {draft && (
            <Button variant="primary" onClick={handleApply} loading={applying} disabled={loading}>
              写入画布
            </Button>
          )}
        </>
      }
    >
      <div className="flex flex-col gap-3" style={{ maxHeight: '70vh' }}>
        <div className="text-xs text-gray-500">
          与 Skill/Agent 同路径：澄清 → 草稿预览 → 写入画布。保存仍点画布上的「保存」（不自动落库）。
          {agents.length === 0 ? ' · 当前 Agent 目录为空，请先创建 Agent。' : ` · 已加载 ${agents.length} 个 Agent`}
        </div>
        <AssetBoundaryHint kind="team" />
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
              <div className="text-[10px] text-gray-500 mb-1">{m.role === 'user' ? '你' : '团队顾问'}</div>
              {m.content}
            </div>
          ))}
          {loading && <div className="text-xs text-gray-500 px-1">思考中…</div>}
          <div ref={bottomRef} />
        </div>
        {draft && (
          <div className="border border-dark-border rounded-lg p-3 space-y-2 bg-dark-card">
            <div className="text-sm text-gray-200 font-medium">阶段草稿</div>
            <div className="text-xs text-gray-400">
              {draft.display_name || draft.name} · {draft.stages?.length || 0} 个阶段
            </div>
            <Textarea label="预览" rows={8} value={preview || JSON.stringify(draft.stages, null, 2)} readOnly />
          </div>
        )}
        <div className="flex gap-2 items-end">
          <div className="flex-1">
            <Textarea
              rows={3}
              value={input}
              onChange={(e: any) => setInput(e.target.value)}
              placeholder="描述流水线目标与阶段…"
              onKeyDown={(e: any) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
            />
          </div>
          <Button variant="primary" onClick={send} loading={loading} disabled={!input.trim() || applying}>
            发送
          </Button>
        </div>
      </div>
    </Modal>
  );
};

export default TeamChatCreateModal;
