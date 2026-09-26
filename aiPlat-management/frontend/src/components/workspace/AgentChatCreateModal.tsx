import React, { useEffect, useRef, useState } from 'react';
import { Button, Modal, Textarea, toast } from '../ui';
import { workspaceAgentApi } from '../../services';
import AssetBoundaryHint from './AssetBoundaryHint';
import { hintsForAgentDraft } from '../../utils/assetBoundaryHints';

type Msg = { role: 'user' | 'assistant'; content: string };

type Draft = {
  name?: string;
  display_name?: string;
  description?: string;
  agent_type?: string;
  config?: Record<string, unknown>;
  skills?: string[];
  tools?: string[];
  mcp_ids?: string[];
  workflow_ids?: string[];
  agent_ids?: string[];
  memory_config?: Record<string, unknown>;
  sop_text?: string;
  trigger_conditions?: string[];
  permissions?: string[];
  reasoning?: string;
  missing_skills?: Array<{ capability?: string; suggested_name?: string; must_have?: string; how_to_create?: string }>;
  missing_tools?: Array<{ capability?: string; how_to_create?: string }>;
  missing_mcps?: unknown[];
};

export interface AgentChatCreateModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

const WELCOME =
  '你好。用自然语言描述要创建的数字员工即可，例如：「根据用户要点做成 PPT，有模版就按模版，输出 pptx，不联网不编造」。我会追问缺的信息，然后生成草稿供你确认。';

const AgentChatCreateModal: React.FC<AgentChatCreateModalProps> = ({ open, onClose, onSuccess }) => {
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
      const res = await workspaceAgentApi.createDialog({ text, history });
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
        setPreview(String(res.agent_md_preview || ''));
        // Prefer API field when present (including empty []) — do not override with stale client heuristics.
        if (Array.isArray((res as any).boundary_hints)) {
          setBoundaryHints((res as any).boundary_hints.map(String));
        } else {
          setBoundaryHints(hintsForAgentDraft(d, String(d.description || '')));
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
      const displayName = String(draft.display_name || draft.name || '').trim() || '未命名数字员工';
      const description = String(draft.description || '').trim();
      const rawId = String(draft.name || '').trim();
      // Prefer stable english id; for CJK pass display_name so backend slugifies
      // deterministically (never Date.now — that flooded ~/.aiplat/agents).
      const agentId = /^[a-z][a-z0-9_-]{1,63}$/i.test(rawId) && !/[\u4e00-\u9fff]/.test(rawId)
        ? rawId.toLowerCase().replace(/-/g, '_')
        : (() => {
            const ascii = displayName
              .toLowerCase()
              .replace(/[^a-z0-9]+/g, '_')
              .replace(/^_|_$/g, '');
            if (/^[a-z][a-z0-9_]{1,63}$/.test(ascii)) return ascii.slice(0, 48);
            if (/ppt/i.test(displayName) || /pptx/i.test(description)) return 'ppt_maker';
            return displayName;
          })();
      const agentType = String(draft.agent_type || 'react').trim() || 'react';
      const skills = Array.isArray(draft.skills) ? draft.skills.map(String) : [];
      const tools = Array.isArray(draft.tools) ? draft.tools.map(String) : [];
      const mcpIds = Array.isArray(draft.mcp_ids) ? draft.mcp_ids.map(String) : [];
      const workflowIds = Array.isArray(draft.workflow_ids) ? draft.workflow_ids.map(String) : [];
      const agentIds = Array.isArray(draft.agent_ids) ? draft.agent_ids.map(String) : [];
      const triggers = Array.isArray(draft.trigger_conditions)
        ? draft.trigger_conditions.map(String).filter(Boolean)
        : [];
      const permissions = Array.isArray(draft.permissions)
        ? draft.permissions.map(String).filter(Boolean)
        : ['llm:generate'];
      const sopText = String(draft.sop_text || '').trim();
      const config =
        draft.config && typeof draft.config === 'object' ? draft.config : {};
      const memoryConfig =
        draft.memory_config && typeof draft.memory_config === 'object'
          ? draft.memory_config
          : undefined;

      const created = await workspaceAgentApi.create({
        name: agentId,
        agent_type: agentType,
        config,
        skills,
        tools,
        mcp_ids: mcpIds,
        workflow_ids: workflowIds,
        agent_ids: agentIds,
        memory_config: memoryConfig,
        reuse_equivalent: true,
        metadata: {
          description,
          display_name: displayName,
          source: 'create_dialog',
        },
        ...(triggers.length ? { trigger_conditions: triggers } : {}),
        ...(permissions.length ? { permissions } : {}),
      } as any);

      const createdId = String((created as any).id || agentId || '');
      if (createdId && sopText) {
        try {
          await workspaceAgentApi.updateSop(createdId, sopText);
          try {
            await workspaceAgentApi.createVersion(createdId, 'Initial SOP (create_dialog)');
          } catch {
            // ignore
          }
        } catch {
          // agent created; SOP best-effort
        }
      }

      toast.success('Agent 已创建', displayName);
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
      title="对话创建 Agent"
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
          多轮澄清需求 → 生成草稿预览 → 确认后写入 Agent 库（仍走标准 create API）。与 Skill「对话创建」同一路径。
        </div>
        <AssetBoundaryHint kind="agent" />
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
              <div className="text-[10px] text-gray-500 mb-1">{m.role === 'user' ? '你' : 'Agent 顾问'}</div>
              {m.content}
            </div>
          ))}
          {loading && (
            <div className="text-xs text-gray-500 px-1">
              正在生成草稿（信息已齐时跳过追问；智能填充约需数十秒）…
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {draft && (
          <div className="border border-dark-border rounded-lg p-3 space-y-2 bg-dark-card">
            <div className="text-sm text-gray-200 font-medium">草稿预览</div>
            <div className="text-xs text-gray-400 grid grid-cols-2 gap-1">
              <div>名称：{draft.display_name || draft.name || '-'}</div>
              <div>类型：{draft.agent_type || '-'}</div>
              <div className="col-span-2">
                技能：{Array.isArray(draft.skills) && draft.skills.length ? draft.skills.join(', ') : '（空）'}
              </div>
              <div className="col-span-2">
                工具：{Array.isArray(draft.tools) && draft.tools.length ? draft.tools.join(', ') : '（空）'}
              </div>
              <div className="col-span-2">
                MCP：
                {Array.isArray(draft.mcp_ids) && draft.mcp_ids.length
                  ? draft.mcp_ids.join(', ')
                  : '（未绑定 · 无外部对接时正常）'}
              </div>
              <div className="col-span-2">
                权限：
                {Array.isArray(draft.permissions) && draft.permissions.length
                  ? draft.permissions.join(', ')
                  : '（将默认 llm:generate）'}
              </div>
              <div className="col-span-2">
                触发词：
                {Array.isArray(draft.trigger_conditions) && draft.trigger_conditions.length
                  ? draft.trigger_conditions.join(' / ')
                  : '（空）'}
              </div>
            </div>
            <Textarea
              label="AGENT.md 预览"
              rows={10}
              value={preview || JSON.stringify(draft, null, 2)}
              readOnly
            />
            {(() => {
              const missS = Array.isArray(draft.missing_skills) ? draft.missing_skills : [];
              const missT = Array.isArray(draft.missing_tools) ? draft.missing_tools : [];
              const missM = Array.isArray(draft.missing_mcps) ? draft.missing_mcps : [];
              if (missS.length === 0 && missT.length === 0 && missM.length === 0) {
                return (
                  <div className="text-xs text-green-400">
                    绑定就绪：Skill / Tool / MCP 均在白名单内（或本任务不需要 MCP），可确认创建。
                  </div>
                );
              }
              return (
                <div className="text-xs text-amber-400 space-y-1">
                  <div>存在能力缺口，建议先补齐或改写 SOP 后再创建：</div>
                  {missS.map((m, i) => (
                    <div key={`s-${i}`}>
                      · Skill：{m.suggested_name || m.capability || '?'}
                      {m.must_have ? ` — ${String(m.must_have).slice(0, 80)}` : ''}
                    </div>
                  ))}
                  {missT.map((m, i) => (
                    <div key={`t-${i}`}>· Tool：{m.capability || '?'}</div>
                  ))}
                  {missM.map((m: any, i) => (
                    <div key={`m-${i}`}>· MCP：{m.capability || m.type || '?'}</div>
                  ))}
                </div>
              );
            })()}
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

export default AgentChatCreateModal;
