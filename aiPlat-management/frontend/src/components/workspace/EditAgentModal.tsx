import React, { useEffect, useMemo, useState } from 'react';
import { workspaceAgentApi, workspaceSkillApi, modelsApi } from '../../services';
import { toolApi } from '../../services';
import { workspaceMcpApi, workflowTemplateApi } from '../../services';
import type { Agent } from '../../services';
import { Alert, Button, Input, Modal, Textarea, toast, MultiSelect } from '../ui';

interface EditAgentModalProps {
  open: boolean;
  agent: Agent | null;
  onClose: () => void;
  onSuccess: () => void;
}

const EditAgentModal: React.FC<EditAgentModalProps> = ({ open, agent, onClose, onSuccess }) => {
  const [loading, setLoading] = useState(false);
  const [skills, setSkills] = useState<string[]>([]);
  const [tools, setTools] = useState<string[]>([]);
  const [mcpIds, setMcpIds] = useState<string[]>([]);
  const [workflowIds, setWorkflowIds] = useState<string[]>([]);
  const [agentIds, setAgentIds] = useState<string[]>([]);
  const [configText, setConfigText] = useState('');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [memoryConfigText, setMemoryConfigText] = useState('');
  const [sopText, setSopText] = useState('');
  const [sopLoading, setSopLoading] = useState(false);
  const [skillOptions, setSkillOptions] = useState<Array<{ value: string; label: string }>>([]);
  const [toolOptions, setToolOptions] = useState<Array<{ value: string; label: string }>>([]);
  const [mcpOptions, setMcpOptions] = useState<Array<{ value: string; label: string }>>([]);
  const [workflowOptions, setWorkflowOptions] = useState<Array<{ value: string; label: string }>>([]);
  const [agentOptions, setAgentOptions] = useState<Array<{ value: string; label: string }>>([]);
  const [modelOptions, setModelOptions] = useState<Array<{ value: string; label: string }>>([]);
  const [selectedModel, setSelectedModel] = useState<string>('');
  // Inline workflow stages
  interface WorkflowStage {
    key: string;
    agent_id: string;
    phase: string;
    order: number;
  }
  const [workflowStages, setWorkflowStages] = useState<WorkflowStage[]>([]);
  const [workflowExpanded, setWorkflowExpanded] = useState(false);
  const [defaultToolset, setDefaultToolset] = useState<string>('workspace_default');
  // Pipeline/Builder configuration fields
  const [generateTestPlan, setGenerateTestPlan] = useState(false);
  const [autoHitl, setAutoHitl] = useState(false);
  const [phaseDescription, setPhaseDescription] = useState('');
  const [hitlAfterExecute, setHitlAfterExecute] = useState(false);
  const [hitlAfterPhase, setHitlAfterPhase] = useState('');

  const [loopType, setLoopType] = useState<string>('react');
  const [agentStatus, setAgentStatus] = useState<string>('draft');

  useEffect(() => {
    if (open && agent) {
      setName(agent.name || '');
      setDescription(String((agent as any)?.metadata?.description || ''));
      setDefaultToolset(String((agent as any)?.metadata?.toolset || 'workspace_default'));
      setSkills(agent.skills || []);
      setTools(agent.tools || []);
      setMcpIds((agent as any)?.mcp_ids || []);
      setWorkflowIds((agent as any)?.workflow_ids || []);
      setAgentIds((agent as any)?.agent_ids || []);
      setConfigText(agent.metadata?.config ? JSON.stringify(agent.metadata.config, null, 2) : (agent as any)?.config ? JSON.stringify((agent as any).config, null, 2) : '');
      setMemoryConfigText((agent as any)?.memory_config ? JSON.stringify((agent as any).memory_config, null, 2) : '');
      setSopText('');
      setAgentStatus(agent.status || 'draft');
      // Pipeline config fields from metadata
      const md = (agent as any)?.metadata || {};
      setGenerateTestPlan(Boolean(md.generate_test_plan));
      setAutoHitl(Boolean(md.auto_hitl));
      setPhaseDescription(String(md.phase_description || ''));
      setHitlAfterExecute(Boolean(md.hitl_after_execute));
      setHitlAfterPhase(String(md.hitl_after_phase || ''));
      fetchOptions();
      fetchSop();
      // init selectedModel from config if possible
      try {
        const cfg = (agent as any)?.config || {};
        if (cfg?.model) setSelectedModel(String(cfg.model));
        setLoopType(String((agent as any)?.metadata?.loop_type || 'react'));
      } catch {
        // ignore
      }
    }
  }, [open, agent]);

  const fetchSop = async () => {
    if (!agent) return;
    setSopLoading(true);
    try {
      const res = await workspaceAgentApi.getSop(agent.id).catch(() => ({ sop: '' } as any));
      setSopText(String((res as any).sop || ''));
    } catch {
      setSopText('');
    } finally {
      setSopLoading(false);
    }
  };

  const fetchOptions = async () => {
    try {
      const [skillRes, toolRes, agentSkills, agentTools] = await Promise.all([
        workspaceSkillApi.list({ limit: 200 }),
        toolApi.list({ limit: 200 } as any),
        agent ? workspaceAgentApi.getSkills(agent.id).catch(() => ({ skill_ids: agent.skills || [] } as any)) : Promise.resolve({ skill_ids: [] as string[] } as any),
        agent ? workspaceAgentApi.getTools(agent.id).catch(() => ({ tool_ids: agent.tools || [] } as any)) : Promise.resolve({ tool_ids: [] as string[] } as any),
      ]);
      const baseSkillOptions = (skillRes.skills || []).map((s: any) => ({ value: s.id, label: s.name }));
      const baseToolOptions = (toolRes.tools || []).map((t: any) => ({ value: t.name, label: t.description || t.name }));

      const selectedSkillIds: string[] = ((agentSkills as any).skill_ids || agent?.skills || []) as string[];
      const selectedToolIds: string[] = ((agentTools as any).tool_ids || agent?.tools || []) as string[];

      const skillSet = new Set(baseSkillOptions.map((o: any) => o.value));
      const toolSet = new Set(baseToolOptions.map((o: any) => o.value));
      const missingSkillOptions = selectedSkillIds
        .filter((id) => id && !skillSet.has(id))
        .map((id) => ({ value: id, label: `${id}（未在 Skill 库中找到）` }));
      const missingToolOptions = selectedToolIds
        .filter((id) => id && !toolSet.has(id))
        .map((id) => ({ value: id, label: `${id}（未在 Tool 列表中找到）` }));

      setSkillOptions([...baseSkillOptions, ...missingSkillOptions]);
      setToolOptions([...baseToolOptions, ...missingToolOptions]);
      if (agent) {
        setSkills(selectedSkillIds);
        setTools(selectedToolIds);
      }

      try {
        const mcpRes = await workspaceMcpApi.listServers();
        const mcpList = (mcpRes as any).servers || [];
        setMcpOptions(mcpList.map((s: any) => ({ value: s.name || s.id, label: `${s.name || s.id} (MCP)` })));
      } catch { /* ignore */ }
      try {
        const wfRes = await workflowTemplateApi.list();
        setWorkflowOptions(((wfRes as any).templates || []).map((w: any) => ({ value: w.name, label: `${w.label || w.name} (Workflow)` })));
      } catch { /* ignore */ }
      try {
        const agentRes = await workspaceAgentApi.list({ limit: 200 });
        setAgentOptions(((agentRes as any).agents || []).filter((a: any) => a.name && a.id !== agent?.id)
          .map((a: any) => ({ value: a.id || a.name, label: `${a.name || a.id} (Agent)` })));
      } catch { /* ignore */ }

      try {
        const modelRes = await modelsApi.list();
        const models = ((modelRes as any).models || []) as { name: string; provider: string; capabilities: string[] }[];
        const modelOpts = models.map((m) => ({
          value: m.name,
          label: `${m.name} (${m.provider})${m.capabilities?.includes('reasoning') ? ' 🧠' : ''}`,
        }));
        setModelOptions(modelOpts);
        if (!selectedModel && models.length > 0) {
          const prefer = models.find((m) => m.name.includes('reasoner'))
            || models.find((m) => m.capabilities?.includes('reasoning'))
            || models[0];
          setSelectedModel(prefer?.name || models[0]?.name || '');
        }
      } catch {
        setModelOptions([]);
      }
    } catch {
      setSkillOptions([]);
      setToolOptions([]);
      setModelOptions([]);
    }
  };

  const handleAutoFill = async () => {
    if (!agent) return;
    const nm = name.trim() || agent.name || '';
    const desc = description.trim();
    if (!nm && !desc) { toast.warning('请先填写名称或描述'); return; }
    setLoading(true);
    try {
      const result = await workspaceAgentApi.autoFill({ name: nm, description: desc });
      if (result.agent_type) setAgentStatus(result.agent_type);
      if (result.config) setConfigText(JSON.stringify(result.config, null, 2));
      if (result.skills?.length) setSkills(result.skills.filter((s: string) => skillOptions.some(o => o.value === s)));
      if (result.tools?.length) setTools(result.tools.filter((t: string) => toolOptions.some(o => o.value === t)));
      if (result.mcp_ids?.length) setMcpIds(result.mcp_ids.filter((m: string) => mcpOptions.some(o => o.value === m)));
      if (result.agent_ids?.length) setAgentIds(result.agent_ids.filter((a: string) => agentOptions.some(o => o.value === a)));
      if (result.memory_config) setMemoryConfigText(JSON.stringify(result.memory_config, null, 2));
      if (result.sop_text) setSopText(result.sop_text);
      toast.success('AI 智能填充完成', result.reasoning || '');
    } catch (e: any) {
      toast.error('智能填充失败', e?.message || String(e));
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async () => {
    if (!agent) return;
    try {
      setLoading(true);

      let config: Record<string, unknown> = {};
      if (configText?.trim()) {
        try {
          config = JSON.parse(configText);
        } catch {
          toast.error('配置 JSON 格式错误，请检查');
          setLoading(false);
          return;
        }
      }

      let memory_config: Record<string, unknown> | undefined;
      if (memoryConfigText?.trim()) {
        try {
          memory_config = JSON.parse(memoryConfigText);
        } catch {
          toast.error('memory_config JSON 格式错误，请检查');
          setLoading(false);
          return;
        }
      }

      const metadata: Record<string, unknown> = { ...(agent.metadata || {}) };
      if (description.trim()) metadata.description = description.trim();
      else delete (metadata as any).description;
      if (defaultToolset && defaultToolset !== 'workspace_default') metadata.toolset = defaultToolset;
      else delete (metadata as any).toolset;
      metadata.generate_test_plan = generateTestPlan;
      metadata.auto_hitl = autoHitl;
      metadata.phase_description = phaseDescription.trim() || undefined;
      metadata.hitl_after_execute = hitlAfterExecute;
      metadata.hitl_after_phase = hitlAfterPhase.trim() || undefined;
      metadata.loop_type = loopType;

      // Save inline workflow stages as a template, then bind it to this agent
      const validStages = workflowStages.filter(s => s.agent_id && s.phase).sort((a, b) => a.order - b.order);
      if (validStages.length > 0) {
        try {
          const wfName = `wf_${agent.id}`;
          const wfPayload = {
            name: wfName,
            description: `Auto-generated workflow from agent "${agent.name}"`,
            stages: validStages.map((s, i) => ({
              agent_id: s.agent_id,
              phase: s.phase,
              order: i + 1,
              output_artifact: `${s.phase}_output`.replace(/\s+/g, '_'),
            })),
          };
          await workflowTemplateApi.save(wfPayload);
          // Ensure the workflow is in the bound list
          if (!workflowIds.includes(wfName)) {
            setWorkflowIds(prev => [...prev, wfName]);
          }
          // Update the local workflowIds for the save call below
          const allWfIds = [...new Set([...workflowIds, wfName])];
          await workspaceAgentApi.update(agent.id, { name: name.trim() || undefined, status: agentStatus || undefined, config, skills: skills.length ? skills : undefined, tools: tools.length ? tools : undefined, mcp_ids: mcpIds.length ? mcpIds : undefined, workflow_ids: allWfIds, agent_ids: agentIds.length ? agentIds : undefined, memory_config, metadata });
          // Skip the normal update below since we already did it
          // Continue to SOP + binding sync
        } catch (e: any) {
          toast.error('Workflow 保存失败', e?.message || String(e));
          setLoading(false);
          return;
        }
      } else {
        await workspaceAgentApi.update(agent.id, { name: name.trim() || undefined, status: agentStatus || undefined, config, skills: skills.length ? skills : undefined, tools: tools.length ? tools : undefined, mcp_ids: mcpIds.length ? mcpIds : undefined, workflow_ids: workflowIds.length ? workflowIds : undefined, agent_ids: agentIds.length ? agentIds : undefined, memory_config, metadata });
      }

      // update SOP (best-effort; do not block binding changes)
      try {
        if (typeof sopText === 'string') {
          await workspaceAgentApi.updateSop(agent.id, sopText);
          // create a version record for auditability (best-effort)
          try {
            await workspaceAgentApi.createVersion(agent.id, 'Update SOP');
          } catch {
            // ignore
          }
        }
      } catch {
        // ignore SOP failures; main update succeeded
      }

      // sync bindings by diff
      const curSkillsRes = await workspaceAgentApi.getSkills(agent.id);
      const curToolsRes = await workspaceAgentApi.getTools(agent.id);
      const curSkills = new Set<string>(((curSkillsRes as any).skill_ids || []) as string[]);
      const curTools = new Set<string>(((curToolsRes as any).tool_ids || []) as string[]);
      const desiredSkills = new Set<string>((skills || []) as string[]);
      const desiredTools = new Set<string>((tools || []) as string[]);

      // unbind removed
      await Promise.all(Array.from(curSkills).filter((id) => !desiredSkills.has(id)).map((id) => workspaceAgentApi.unbindSkill(agent.id, id)));
      await Promise.all(Array.from(curTools).filter((id) => !desiredTools.has(id)).map((id) => workspaceAgentApi.unbindTool(agent.id, id)));

      // bind new (send list for batch add)
      const toAddSkills = Array.from(desiredSkills).filter((id) => !curSkills.has(id));
      const toAddTools = Array.from(desiredTools).filter((id) => !curTools.has(id));
      if (toAddSkills.length) await workspaceAgentApi.bindSkills(agent.id, toAddSkills);
      if (toAddTools.length) await workspaceAgentApi.bindTools(agent.id, toAddTools);

      toast.success(`Agent "${agent.name}" 更新成功`);
      onSuccess();
      onClose();
    } catch (error: any) {
      toast.error('更新失败', String(error?.message || ''));
    } finally {
      setLoading(false);
    }
  };

  const configHint = useMemo(() => '提示：此处仅更新 Agent config；名称/类型不可修改。', []);
  const configHint2 = useMemo(() => '提示：agent_id 不变；“名称”是显示名，可修改。', []);

  return (
    <>
    <Modal
      open={open}
      onClose={onClose}
      title="编辑应用库 Agent"
      width={720}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={loading}>
            取消
          </Button>
          <Button variant="primary" onClick={handleSubmit} loading={loading}>
            保存
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Input label="名称（显示名）" value={name} onChange={(e: any) => setName(e.target.value)} />
        <div className="mb-2">
          <label className="block text-sm font-medium text-gray-300 mb-1">状态</label>
          {['draft', 'ready'].includes(agentStatus) ? (
            <select value={agentStatus} onChange={(e) => setAgentStatus(e.target.value)}
              className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100">
              <option value="draft">draft（草稿）</option>
              <option value="ready">ready（就绪，提交审核）</option>
            </select>
          ) : (
            <div className="w-full h-10 px-3 flex items-center bg-dark-card border border-dark-border rounded-lg text-sm text-gray-400">
              {agentStatus === 'published' ? '已发布 — 需在审批中心操作' :
               agentStatus === 'listed' ? '已上架 — 需在审批中心操作' :
               agentStatus === 'deprecated' ? '已废弃 — 只读' :
               `${agentStatus} — 需在审批中心操作`}
            </div>
          )}
        </div>
        <Input label="描述（可选）" value={description} onChange={(e: any) => setDescription(e.target.value)} />

        {/* ── 流水线配置 ── */}
        <details className="mt-2">
          <summary className="text-sm font-medium text-gray-300 cursor-pointer hover:text-gray-200">⚙️ 流水线配置</summary>
          <div className="mt-2 ml-2 space-y-2 p-2 rounded bg-dark-hover/30">
            <Input label="阶段描述（phase_description）" value={phaseDescription} onChange={(e: any) => setPhaseDescription(e.target.value)} placeholder="如：系统架构设计" />
            <div className="flex items-center gap-2 mt-1">
              <input type="checkbox" checked={generateTestPlan} onChange={(e) => setGenerateTestPlan(e.target.checked)} className="w-4 h-4" />
              <span className="text-xs text-gray-400">自动生成测试计划（generate_test_plan）</span>
            </div>
            <div className="flex items-center gap-2 mt-1">
              <input type="checkbox" checked={autoHitl} onChange={(e) => setAutoHitl(e.target.checked)} className="w-4 h-4" />
              <span className="text-xs text-gray-400">自动启用 HITL 确认（auto_hitl）</span>
            </div>
            <div className="flex items-center gap-2 mt-1">
              <input type="checkbox" checked={hitlAfterExecute} onChange={(e) => setHitlAfterExecute(e.target.checked)} className="w-4 h-4" />
              <span className="text-xs text-gray-400">执行后暂停（hitl_after_execute）</span>
            </div>
            {hitlAfterExecute && (
              <Input label="执行后暂停阶段名（hitl_after_phase）" value={hitlAfterPhase} onChange={(e: any) => setHitlAfterPhase(e.target.value)} placeholder="如：awaiting_test_report_review" />
            )}
          </div>
        </details>

        <div>
          <div className="text-sm font-medium text-gray-300 mb-2">默认 Toolset（运行时工具集）</div>
          <select
            value={defaultToolset}
            onChange={(e) => setDefaultToolset(e.target.value)}
            className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100"
          >
            <option value="workspace_default">workspace_default（默认）</option>
            <option value="safe_readonly">safe_readonly（只读）</option>
            <option value="browser">browser（浏览器/HTTP）</option>
            <option value="full">full（全量/高风险）</option>
          </select>
          <div className="text-xs text-gray-500 mt-1">
            提示：该字段会写入 Agent metadata.toolset；执行弹窗会默认读取它，也可在执行时临时覆盖。
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <div className="text-sm font-medium text-gray-300 mb-2">模型（来自基础设施模型库）</div>
            <select
              value={selectedModel}
              onChange={(e) => {
                const v = e.target.value;
                setSelectedModel(v);
                try {
                  const cfg = configText?.trim() ? JSON.parse(configText) : {};
                  cfg.model = v;
                  setConfigText(JSON.stringify(cfg, null, 2));
                } catch {
                  setConfigText(JSON.stringify({ model: v, temperature: 0.1 }, null, 2));
                }
              }}
              className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100"
            >
              {modelOptions.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-end justify-end">
            <Button
              variant="primary"
              onClick={handleAutoFill}
              disabled={loading}
            >
              ✨ AI 智能填充
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <MultiSelect label="绑定技能" options={skillOptions} selected={skills} onChange={setSkills} />
          <MultiSelect label="绑定工具" options={toolOptions} selected={tools} onChange={setTools} />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {mcpOptions.length > 0 && <MultiSelect label="绑定 MCP" options={mcpOptions} selected={mcpIds} onChange={setMcpIds} />}
          {workflowOptions.length > 0 && <MultiSelect label="绑定 Workflow" options={workflowOptions} selected={workflowIds} onChange={setWorkflowIds} />}
        </div>

        {agentOptions.length > 0 && (
          <MultiSelect label="绑定子 Agent" options={agentOptions} selected={agentIds} onChange={setAgentIds} hint="当前 Agent 可以将任务委派给选中的子 Agent" />
        )}

        {/* Inline Workflow Stage Config */}
        {agentOptions.length > 0 && (
          <div className="bg-dark-bg border border-dark-border rounded-lg p-3">
            <div
              className="flex items-center justify-between cursor-pointer select-none"
              onClick={() => setWorkflowExpanded(!workflowExpanded)}
            >
              <span className="text-sm font-medium text-gray-200">内建 Workflow 阶段</span>
              <span className="text-gray-500 text-xs">{workflowExpanded ? '收起 ▲' : '展开 ▼'}</span>
            </div>
            <p className="text-xs text-gray-500 mt-1 mb-2">
              为当前 Agent 配置顺序执行的工作流阶段，每个阶段绑定一个子 Agent。保存时会自动创建/更新 Workflow 模板。
            </p>
            {workflowExpanded && (
              <div className="space-y-2">
                {workflowStages.sort((a, b) => a.order - b.order).map((stage, idx) => (
                  <div key={stage.key} className="flex items-center gap-2 bg-dark-card rounded p-2">
                    <span className="text-xs text-gray-500 w-6">{idx + 1}.</span>
                    <select
                      value={stage.agent_id}
                      onChange={(e) => {
                        setWorkflowStages(prev => prev.map(s => s.key === stage.key ? { ...s, agent_id: e.target.value } : s));
                      }}
                      className="flex-1 h-8 px-2 bg-dark-bg border border-dark-border rounded text-xs text-gray-200"
                    >
                      <option value="">选择子 Agent</option>
                      {agentOptions.map(a => (
                        <option key={a.value} value={a.value}>{a.label}</option>
                      ))}
                    </select>
                    <input
                      value={stage.phase}
                      onChange={(e) => {
                        setWorkflowStages(prev => prev.map(s => s.key === stage.key ? { ...s, phase: e.target.value } : s));
                      }}
                      placeholder="阶段名（如: 设计、开发、测试）"
                      className="w-28 h-8 px-2 bg-dark-bg border border-dark-border rounded text-xs text-gray-200 placeholder-gray-600"
                    />
                    <button
                      onClick={() => setWorkflowStages(prev => prev.filter(s => s.key !== stage.key))}
                      className="p-1 text-gray-500 hover:text-red-400"
                      title="删除阶段"
                    >
                      ×
                    </button>
                  </div>
                ))}
                <button
                  onClick={() => {
                    const newStage: WorkflowStage = {
                      key: `wf_${Date.now()}`,
                      agent_id: '',
                      phase: '',
                      order: workflowStages.length + 1,
                    };
                    setWorkflowStages(prev => [...prev, newStage]);
                  }}
                  className="w-full py-1.5 rounded border border-dashed border-dark-border text-xs text-gray-500 hover:text-gray-300 hover:border-gray-600 transition-colors"
                >
                  ＋ 添加阶段
                </button>
              </div>
            )}
          </div>
        )}

        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="text-sm font-medium text-gray-300 mb-2">Agent 策略</div>
            <select
              value={loopType}
              onChange={(e) => setLoopType(e.target.value)}
              className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100"
            >
              <option value="react">ReAct (Reason + Act) — 透明推理循环</option>
              <option value="function_call">Function Calling — 模型原生工具调用</option>
            </select>
            <div className="text-xs text-gray-500 mt-1">
              ReAct 适用于大多数模型；Function Calling 需要模型支持（GPT-4 / Claude）
            </div>
          </div>
        </div>

        <Textarea label="配置（JSON）" value={configText} onChange={(e: any) => setConfigText(e.target.value)} rows={10} />
        <Textarea label="memory_config（JSON，可选）" value={memoryConfigText} onChange={(e: any) => setMemoryConfigText(e.target.value)} rows={6} />
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-sm font-medium text-gray-300">SOP（Markdown，可选）</span>
          </div>
          <Textarea
          value={sopText}
          onChange={(e: any) => setSopText(e.target.value)}
          rows={10}
          placeholder={'例如：\n1. 澄清问题与范围。\n2. 调用 knowledge_retrieval 检索证据。\n3. 综合生成答案并引用证据。'}
          />
          </div>
        {sopLoading && <div className="text-xs text-gray-500">SOP 加载中...</div>}
        <Alert type="info" title="说明">
          {configHint} {configHint2}
        </Alert>
      </div>
    </Modal>
    </>
  );
};

export default EditAgentModal;
