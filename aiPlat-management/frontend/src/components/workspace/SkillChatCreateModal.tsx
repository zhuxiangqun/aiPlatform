import React, { useEffect, useRef, useState } from 'react';
import { Button, Modal, Textarea, toast } from '../ui';
import { workspaceSkillApi } from '../../services';
import AssetBoundaryHint from './AssetBoundaryHint';
import { hintsForSkillDraft } from '../../utils/assetBoundaryHints';

type Msg = { role: 'user' | 'assistant'; content: string };

type Draft = {
  name?: string;
  display_name?: string;
  description?: string;
  category?: string;
  skill_kind?: string;
  permissions?: string[];
  trigger_conditions?: string[];
  input_schema?: Record<string, unknown>;
  output_schema?: Record<string, unknown>;
  config?: Record<string, unknown>;
  sop?: string;
};

export interface SkillChatCreateModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

const WELCOME =
  '你好。用自然语言描述要创建的 Skill 即可，例如：「根据大纲生成 PPT，按模版填充，输出 pptx 路径，不联网不编造」。我会追问缺的信息，然后生成草稿供你确认。';

const SkillChatCreateModal: React.FC<SkillChatCreateModalProps> = ({ open, onClose, onSuccess }) => {
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
      const res = await workspaceSkillApi.createDialog({ text, history });
      if ((res as any)?.error && !(res as any)?.next) {
        toast.error('对话失败', String((res as any).error));
        setConversation([
          ...nextConv,
          { role: 'assistant', content: '出错了，请换种说法再试一次。' },
        ]);
        return;
      }
      const reply = String(res.reply || '').trim();
      const qs = Array.isArray(res.questions) ? res.questions.filter(Boolean) : [];
      let assistantText = reply || '（无回复）';
      if (qs.length > 0 && res.next === 'ask') {
        assistantText += '\n\n' + qs.map((q, i) => `${i + 1}. ${q}`).join('\n');
      }
      setConversation([...nextConv, { role: 'assistant', content: assistantText }]);
      if (res.next === 'draft' && res.draft && typeof res.draft === 'object') {
        const d = res.draft as Draft;
        setDraft(d);
        setPreview(String(res.skill_md_preview || ''));
        if (Array.isArray((res as any).boundary_hints)) {
          setBoundaryHints((res as any).boundary_hints.map(String));
        } else {
          setBoundaryHints(hintsForSkillDraft(d as any, String(d.description || '')));
        }
      }
    } catch (e: any) {
      toast.error('对话失败', e?.detail || e?.message || String(e));
      setConversation([
        ...nextConv,
        { role: 'assistant', content: '网络或服务异常，请稍后重试。' },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    if (!draft) return;
    setCreating(true);
    try {
      const skillKind = draft.skill_kind === 'executable' ? 'executable' : 'rule';
      // Dialog-created skills are SOP+tools by default (no handler.py) → prompt.
      // Only keep handler/python_class when draft explicitly says so.
      const rawEt = String(draft.execution_type || '').trim().toLowerCase();
      const executionType =
        rawEt === 'handler' || rawEt === 'python_class' || rawEt === 'prompt'
          ? rawEt
          : skillKind === 'executable'
            ? 'prompt'
            : 'prompt';
      const displayName = String(draft.display_name || draft.name || '').trim();
      const skillId = String(draft.name || '').trim();
      const isWrite =
        skillKind === 'executable' ||
        (Array.isArray(draft.permissions) &&
          draft.permissions.some((p) => /workspace_fs_write|run_command|file_operations/.test(String(p))));
      const res = await workspaceSkillApi.create({
        name: displayName || skillId || '未命名技能',
        ...(skillId && /^[a-z][a-z0-9_-]{2,}$/.test(skillId) ? { skill_id: skillId } : {}),
        display_name: displayName || skillId,
        description: String(draft.description || ''),
        category: String(draft.category || 'general'),
        skill_kind: skillKind,
        execution_type: executionType,
        permissions: Array.isArray(draft.permissions) ? draft.permissions : ['llm:generate'],
        trigger_conditions: Array.isArray(draft.trigger_conditions) ? draft.trigger_conditions : [],
        config: draft.config && typeof draft.config === 'object' ? draft.config : {},
        input_schema: draft.input_schema || {},
        output_schema: draft.output_schema || {},
        sop: String(draft.sop || ''),
        template: String(draft.category || 'general'),
        metadata: {
          execution_type: executionType,
          skill_kind: skillKind,
          source: 'create_dialog',
          ...(isWrite
            ? {
                keywords: {
                  objects: ['document', 'file', 'output'],
                  actions: ['generate', 'write', 'export'],
                  constraints: ['离线', '不编造'],
                },
                negative_triggers: ['联网搜图找素材', '编造未提供的事实或数据', '只要文字稿不要文件'],
              }
            : {}),
        },
      } as any);
      if ((res as any)?.error) {
        toast.error('创建失败', String((res as any).error));
        return;
      }
      toast.success('Skill 已创建', displayName || skillId);
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
      title="对话创建 Skill"
      width={720}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={creating}>
            取消
          </Button>
          {draft && (
            <Button variant="primary" onClick={handleCreate} loading={creating} disabled={loading}>
              确认创建
            </Button>
          )}
        </>
      }
    >
      <div className="flex flex-col gap-3" style={{ maxHeight: '70vh' }}>
        <div className="text-xs text-gray-500">
          多轮澄清需求 → 生成草稿预览 → 确认后写入 Skill 库（仍走标准 create API）。
        </div>
        <AssetBoundaryHint kind="skill" />
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
              <div className="text-[10px] text-gray-500 mb-1">{m.role === 'user' ? '你' : 'Skill 顾问'}</div>
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
              <div>名称：{draft.display_name || draft.name || '-'}</div>
              <div>ID：{draft.name || '-'}</div>
              <div>分类：{draft.category || '-'}</div>
              <div>形态：{draft.skill_kind || '-'}</div>
              <div className="col-span-2">
                权限：{Array.isArray(draft.permissions) && draft.permissions.length
                  ? draft.permissions.join(', ')
                  : '（空）'}
              </div>
            </div>
            <Textarea
              label="SKILL.md 预览"
              rows={10}
              value={preview || JSON.stringify(draft, null, 2)}
              readOnly
            />
            {boundaryHints.length > 0 && (
              <div className="text-xs text-amber-400 space-y-1">
                <div>边界提示：</div>
                {boundaryHints.map((h, i) => (
                  <div key={i}>· {h}</div>
                ))}
              </div>
            )}
            <div className="text-xs text-gray-500">
              Skill 可调 Tool（permissions）；不可再调另一个 Skill。原子读写/HTTP 请改建成 Tool。
            </div>
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

export default SkillChatCreateModal;
