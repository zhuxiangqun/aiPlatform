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
  const [defaultToolset, setDefaultToolset] = useState<string>('workspace_default');
  // Pipeline/Builder configuration fields
  const [generateTestPlan, setGenerateTestPlan] = useState(false);
  const [autoHitl, setAutoHitl] = useState(false);
  const [phaseDescription, setPhaseDescription] = useState('');
  const [hitlAfterExecute, setHitlAfterExecute] = useState(false);
  const [hitlAfterPhase, setHitlAfterPhase] = useState('');

  // Disambiguation wizard
  const [wizOpen, setWizOpen] = useState(false);
  const [wizMode, setWizMode] = useState<'manual' | 'auto'>('manual');
  const [wizSources, setWizSources] = useState<string[]>([]);
  const [wizMayWrite, setWizMayWrite] = useState(false);
  const [wizToolset, setWizToolset] = useState<string>('workspace_default');
  const [genWarnings, setGenWarnings] = useState<string[]>([]);
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

  const detectAmbiguity = () => {
    const text = `${name} ${description}`.toLowerCase();
    const wantsFs = text.includes('目录') || text.includes('文件') || text.includes('仓库') || text.includes('代码库') || text.includes('文件夹') || text.includes('path');
    const wantsBrowser = text.includes('浏览器') || text.includes('网页') || text.includes('爬取') || text.includes('自动化');
    const wantsHttp = text.includes('api') || text.includes('接口') || text.includes('http') || text.includes('crm') || text.includes('工单');
    const wantsDb = text.includes('数据库') || text.includes('sql');
    const wantsWeb = text.includes('公网') || text.includes('搜索') || text.includes('查资料') || text.includes('外部信息');
    const wantsWrite = text.includes('写入') || text.includes('更新') || text.includes('创建') || text.includes('删除') || text.includes('修改');
    return { wantsFs, wantsBrowser, wantsHttp, wantsDb, wantsWeb, wantsWrite };
  };

  const recommendToolset = (opts?: { mode?: 'manual' | 'auto'; sources?: string[]; mayWrite?: boolean }) => {
    const mode = opts?.mode || 'manual';
    const sources = new Set<string>(opts?.sources || []);
    const mayWrite = Boolean(opts?.mayWrite);

    // Rules (minimal, predictable):
    // 1) If the task needs high-risk integrations (http/database/browser) → full
    // 2) Else if mayWrite → workspace_default (allows file write but avoids extra risky tools)
    // 3) Else if auto mode with any external sources/filesystem → safe_readonly
    // 4) Else → workspace_default
    if (sources.has('http') || sources.has('database') || sources.has('browser')) {
      return { toolset: 'full', reason: '选择了高风险数据源（HTTP/数据库/浏览器），需要 full 才可能调用相应工具。' };
    }
    if (mayWrite) {
      return { toolset: 'workspace_default', reason: '标记“可能写入/修改”，推荐 workspace_default（允许 file_operations 写/删，但不默认放开 http/browser/code/database）。' };
    }
    if (mode === 'auto' && (sources.size > 0 || sources.has('filesystem') || sources.has('web'))) {
      return { toolset: 'safe_readonly', reason: '自动获取但不需要写入，推荐 safe_readonly（只读 + 低风险工具）。' };
    }
    return { toolset: 'workspace_default', reason: '默认推荐 workspace_default。' };
  };

  const fetchSop = async () => {
    if (!agent) return;
    setSopLoading(true);
    try {
      const res = await workspaceAgentApi.getSop(agent.id).catch(() => ({ sop: '' } as any));
      setSopText(String((res as any).sop || ''));
    } catch {
      // SOP might not exist; allow user to create it.
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

      // models from core model registry
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

  const applySmartGenerateWithWiz = (opts?: { mode?: 'manual' | 'auto'; sources?: string[]; mayWrite?: boolean }) => {
    const nm = name.trim() || agent?.name || 'Agent';
    const desc = description.trim();
    const modelName = selectedModel || 'DeepSeek Reasoner';
    const mode = opts?.mode || 'manual';
    const sources = new Set<string>(opts?.sources || []);
    const mayWrite = Boolean(opts?.mayWrite);

    const sys = [
      `你是“${nm}”。`,
      desc ? `职责与边界：${desc}` : '',
      mode === 'auto' ? '你需要在回答前主动获取必要信息（通过工具/MCP/技能），必要时委派子Agent或触发Workflow，不要默认要求用户粘贴大段数据。' : '请先澄清目标与约束，再给出结构化输出。',
      '输出要求：给出结论、依据（如有）、以及下一步建议。',
      '如果缺少上下文，请提出需要的材料（文件/接口/数据范围）。',
      mayWrite ? '注意：涉及对外部系统写入/修改时，必须先二次确认并说明影响范围；必要时触发审批。' : '',
    ].filter(Boolean).join('\n');

    const sopLines: string[] = ['1. 澄清问题与范围（目标/输入/约束/权限）。'];
    if (mode === 'auto') {
      if (sources.has('filesystem')) sopLines.push('2. 使用 file_operations：先 list 目录结构（可递归/限量），再 read 关键文件内容（控制读取范围与大小）。');
      if (sources.has('http')) sopLines.push('2. 使用 http 工具访问内部 API（必要时配置白名单/鉴权），获取所需数据。');
      if (sources.has('database')) sopLines.push('2. 使用 database 工具执行只读查询（必要时做权限与审计）。');
      if (sources.has('browser')) sopLines.push('2. 使用 browser/webfetch 获取网页信息（注意合规与来源）。');
      if (sources.has('web')) sopLines.push('2. 使用 search/webfetch 获取公开信息（记录来源）。');
      if (!sources.size) sopLines.push('2. 如果需要外部数据，先明确数据源并通过工具获取。');
    } else {
      sopLines.push('2. 若需要外部信息，明确需要哪些材料并让用户提供（或建议开启工具自动获取）。');
    }
    sopLines.push('3. 分析与处理：按优先级输出发现与建议（必要时分模块/分文件）。');
    if (mcpIds.length > 0) sopLines.push('   - 可通过 MCP 服务器获取外部能力（工具自动注册到工具池）。');
    if (workflowIds.length > 0) sopLines.push('   - 可触发已绑定的 Workflow 执行预定义流水线。');
    if (agentIds.length > 0) sopLines.push('   - 可将子任务委派给已绑定的子 Agent（debugger/test-engineer等）。');
    sopLines.push('4. 汇总输出：结论 → 依据/引用 → 建议/下一步（含高/中/低优先级）。');
    sopLines.push('5. 自检：一致性、可执行性、风险与不确定性提示。');

    try {
      const cfg: any = configText?.trim() ? JSON.parse(configText) : {};
      cfg.model = modelName;
      if (cfg.temperature === undefined) cfg.temperature = 0.1;
      if (cfg.max_tokens === undefined) cfg.max_tokens = 4096;
      cfg.system_prompt = sys;
      setConfigText(JSON.stringify(cfg, null, 2));
    } catch {
      setConfigText(JSON.stringify({ model: modelName, temperature: 0.1, max_tokens: 4096, system_prompt: sys }, null, 2));
    }
    if (!sopText.trim()) setSopText(sopLines.join('\n'));

    // auto add tools for auto mode if user hasn't bound any tools yet
    if (mode === 'auto' && tools.length === 0) {
      const rec = new Set<string>();
      if (sources.has('filesystem')) rec.add('file_operations');
      if (sources.has('http')) rec.add('http');
      if (sources.has('database')) rec.add('database');
      if (sources.has('browser')) rec.add('browser');
      if (sources.has('web')) {
        rec.add('webfetch');
        rec.add('search');
      }
      if (rec.size) setTools(Array.from(rec));
    }

    // post-generate lint (best-effort)
    const warns: string[] = [];
    if (mode === 'auto' && sources.has('filesystem') && !(tools.includes('file_operations'))) {
      warns.push('你选择了“自动读取目录/仓库”，请确保绑定了 file_operations 工具，并在服务端配置 AIPLAT_FILE_OPERATIONS_ALLOWED_ROOTS。');
    }
    if (mode === 'auto' && sources.has('http') && !(tools.includes('http'))) {
      warns.push('你选择了“内部 HTTP API”，请确保绑定了 http 工具。');
    }
    if (mode === 'auto' && sources.has('database') && !(tools.includes('database'))) {
      warns.push('你选择了“数据库”，请确保绑定了 database 工具。');
    }
    if (mode === 'auto' && sources.has('browser') && !(tools.includes('browser'))) {
      warns.push('你选择了“浏览器自动化”，请确保绑定了 browser 工具。');
    }
    if (mayWrite) warns.push('你选择了“可能写入/修改外部系统”：请确保审批/审计与白名单策略已启用。');
    setGenWarnings(warns);
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

      await workspaceAgentApi.update(agent.id, { name: name.trim() || undefined, status: agentStatus || undefined, config, skills: skills.length ? skills : undefined, tools: tools.length ? tools : undefined, mcp_ids: mcpIds.length ? mcpIds : undefined, workflow_ids: workflowIds.length ? workflowIds : undefined, agent_ids: agentIds.length ? agentIds : undefined, memory_config, metadata });

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
              onClick={() => {
                const a = detectAmbiguity();
                // Pre-fill wizard from detected keywords
                const srcs: string[] = [];
                if (a.wantsFs) srcs.push('filesystem');
                if (a.wantsBrowser) srcs.push('browser');
                if (a.wantsHttp) srcs.push('http');
                if (a.wantsDb) srcs.push('database');
                if (a.wantsWeb) srcs.push('web');
                if (srcs.length || a.wantsWrite) {
                  setWizMode('auto');
                  setWizSources(srcs);
                  setWizMayWrite(a.wantsWrite);
                }
                setWizOpen(true);
              }}
              disabled={loading}
            >
              生成向导（推荐）
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
        {genWarnings.length > 0 && (
          <Alert type="warning" title="自动生成提示">
            <ul className="list-disc pl-5 space-y-1">
              {genWarnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </Alert>
        )}
        <Alert type="info" title="说明">
          {configHint} {configHint2}
        </Alert>
      </div>
    </Modal>

    <Modal
      open={wizOpen}
      onClose={() => setWizOpen(false)}
      title="智能生成：主动消歧"
      width={760}
      footer={
        <>
          <Button variant="secondary" onClick={() => setWizOpen(false)} disabled={loading}>
            取消
          </Button>
          <Button
            variant="primary"
            onClick={() => {
              applySmartGenerateWithWiz({ mode: wizMode, sources: wizSources, mayWrite: wizMayWrite });
              // apply recommended/selected toolset to agent default (stored in metadata.toolset)
              try {
                setDefaultToolset(wizToolset || 'workspace_default');
              } catch {
                setDefaultToolset('workspace_default');
              }
              setWizOpen(false);
            }}
            disabled={loading}
          >
            生成
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Alert type="info" title="说明">
          为避免“目录分析/系统接入”等场景出现歧义，这里先确认运行方式与数据来源。选择“自动获取”时会自动推荐绑定相应工具（可再手动调整）。
        </Alert>

        <div>
          <div className="text-sm font-medium text-gray-300 mb-2">运行方式</div>
          <div className="flex gap-4">
            <label className="flex items-center gap-2 text-sm text-gray-200">
              <input type="radio" checked={wizMode === 'manual'} onChange={() => setWizMode('manual')} />
              我会手动提供材料（粘贴代码/上传内容）
            </label>
            <label className="flex items-center gap-2 text-sm text-gray-200">
              <input type="radio" checked={wizMode === 'auto'} onChange={() => setWizMode('auto')} />
              自动获取（需要工具/MCP）
            </label>
          </div>
        </div>

        {wizMode === 'auto' && (
          <div>
            <div className="text-sm font-medium text-gray-300 mb-2">数据来源（可多选）</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-sm text-gray-200">
              {[
                { key: 'filesystem', label: '本地目录/仓库（需要 file_operations）' },
                { key: 'http', label: '内部 HTTP API（需要 http）' },
                { key: 'database', label: '数据库（需要 database）' },
                { key: 'browser', label: '浏览器自动化（需要 browser）' },
                { key: 'web', label: '公网检索/抓取（search/webfetch）' },
              ].map((x) => (
                <label key={x.key} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={wizSources.includes(x.key)}
                    onChange={() => {
                      setWizSources((prev) => (prev.includes(x.key) ? prev.filter((k) => k !== x.key) : [...prev, x.key]));
                    }}
                  />
                  {x.label}
                </label>
              ))}
            </div>
          </div>
        )}

        <div>
          <div className="text-sm font-medium text-gray-300 mb-2">推荐 Toolset（运行时工具集）</div>
          <select
            value={wizToolset}
            onChange={(e) => setWizToolset(e.target.value)}
            className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100"
          >
            <option value="safe_readonly">safe_readonly（只读）</option>
            <option value="workspace_default">workspace_default（默认）</option>
            <option value="full">full（全量/高风险）</option>
          </select>
          <div className="text-xs text-gray-500 mt-1">
            {recommendToolset({ mode: wizMode, sources: wizSources, mayWrite: wizMayWrite }).reason}
          </div>
        </div>

        <div>
          <div className="text-sm font-medium text-gray-300 mb-2">是否可能写入/修改外部系统？</div>
          <label className="flex items-center gap-2 text-sm text-gray-200">
            <input type="checkbox" checked={wizMayWrite} onChange={() => setWizMayWrite(!wizMayWrite)} />
            可能（将提示二次确认/审批）
          </label>
        </div>
      </div>
    </Modal>
    </>
  );
};

export default EditAgentModal;
