import React, { useEffect, useMemo, useState } from 'react';
import { workspaceAgentApi, workspaceSkillApi, modelsApi } from '../../services';
import { toolApi } from '../../services';
import { workspaceMcpApi, workflowTemplateApi } from '../../services';
import type { Agent } from '../../services';
import { Alert, Button, Input, Modal, Textarea, toast, MultiSelect, Tabs } from '../ui';
import PromptDiffModal from './PromptDiffModal';

interface EditAgentModalProps {
  open: boolean;
  agent: Agent | null;
  onClose: () => void;
  onSuccess: () => void;
}

const EditAgentModal: React.FC<EditAgentModalProps> = ({ open, agent, onClose, onSuccess }) => {
  const [loading, setLoading] = useState(false);
  const [autoFillLoading, setAutoFillLoading] = useState(false);
  const [smartFillLoading, setSmartFillLoading] = useState(false);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditResult, setAuditResult] = useState<any>(null);
  const [missingSkills, setMissingSkills] = useState<any[]>([]);
  const [missingTools, setMissingTools] = useState<any[]>([]);
  const [missingMcps, setMissingMcps] = useState<any[]>([]);
  // Role definition flow
  const [roleDefinition, setRoleDefinition] = useState<{
    role_name: string; responsibilities: string[]; scenarios: string[];
    required_capabilities: string[]; workflow_hint: string; reasoning: string;
  } | null>(null);
  const [showRolePreview, setShowRolePreview] = useState(false);
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
  const [triggerText, setTriggerText] = useState('');
  const [permissionsText, setPermissionsText] = useState('["llm:generate"]');
  const [sopLoading, setSopLoading] = useState(false);
  const [skillOptions, setSkillOptions] = useState<Array<{ value: string; label: string }>>([]);
  const [toolOptions, setToolOptions] = useState<Array<{ value: string; label: string }>>([]);
  const [mcpOptions, setMcpOptions] = useState<Array<{ value: string; label: string }>>([]);
  const [workflowOptions, setWorkflowOptions] = useState<Array<{ value: string; label: string }>>([]);
  const [agentOptions, setAgentOptions] = useState<Array<{ value: string; label: string }>>([]);
  const [modelOptions, setModelOptions] = useState<Array<{ value: string; label: string }>>([]);
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [knowledgeBases, setKnowledgeBases] = useState<string[]>([]);
  const [kbOptions, setKbOptions] = useState<Array<{ value: string; label: string }>>([]);
  const [defaultToolset, setDefaultToolset] = useState<string>('workspace_default');
  // Pipeline/Builder configuration fields
  const [generateTestPlan, setGenerateTestPlan] = useState(false);
  const [autoHitl, setAutoHitl] = useState(false);
  const [phaseDescription, setPhaseDescription] = useState('');
  const [hitlAfterExecute, setHitlAfterExecute] = useState(false);
  const [hitlAfterPhase, setHitlAfterPhase] = useState('');

  const [loopType, setLoopType] = useState<string>('react');
  const [agentStatus, setAgentStatus] = useState<string>('draft');
  const [optimizeOpen, setOptimizeOpen] = useState(false);
  const [optimizePrompt, setOptimizePrompt] = useState('');

  useEffect(() => {
    if (open && agent) {
      setName(agent.name || '');
      setDescription(String((agent as any)?.metadata?.description || ''));
      setDefaultToolset(String((agent as any)?.metadata?.toolset || 'workspace_default'));
      setSkills(agent.skills || []);
      setTools(agent.tools || []);
      setMcpIds((agent as any)?.mcp_ids || (agent as any)?.metadata?.mcp_servers || []);
      // Auto-select mcp_readonly toolset if agent has MCP servers bound
      const hasMcp = ((agent as any)?.mcp_ids || (agent as any)?.metadata?.mcp_servers || []).length > 0;
      if (hasMcp && String((agent as any)?.metadata?.toolset || 'workspace_default') === 'workspace_default') {
        setDefaultToolset('mcp_readonly');
      }
      setWorkflowIds((agent as any)?.workflow_ids || (agent as any)?.metadata?.workflows || []);
      setAgentIds((agent as any)?.agent_ids || (agent as any)?.metadata?.agent_ids || []);
      setConfigText((agent as any)?.config ? JSON.stringify((agent as any).config, null, 2) : agent.metadata?.config ? JSON.stringify(agent.metadata.config, null, 2) : '');
      setMemoryConfigText((agent as any)?.memory_config ? JSON.stringify((agent as any).memory_config, null, 2) : '{\n  "type": "short_term",\n  "recall_count": 5\n}');
      setSopText('');
      setTriggerText(((agent as any)?.metadata?.trigger_conditions || []).join('\n'));
      setPermissionsText(JSON.stringify((agent as any)?.metadata?.permissions || ["llm:generate"], null, 2));
      setAgentStatus(agent.status || 'draft');
      // Pipeline config fields from metadata
      const md = (agent as any)?.metadata || {};
      // Restore saved role definition (only if description hasn't changed)
      const savedRole = md.role_definition;
      const savedDesc = md.role_description;
      if (savedRole && typeof savedRole === 'object' && savedDesc === description.trim()) {
        setRoleDefinition(savedRole as any);
        setShowRolePreview(true);
      } else {
        setRoleDefinition(null);
        setShowRolePreview(false);
      }
      setGenerateTestPlan(Boolean(md.generate_test_plan));
      setAutoHitl(Boolean(md.auto_hitl));
      setPhaseDescription(String(md.phase_description || ''));
      setHitlAfterExecute(Boolean(md.hitl_after_execute));
      setHitlAfterPhase(String(md.hitl_after_phase || ''));
      setKnowledgeBases(Array.isArray(md.knowledge_bases) ? md.knowledge_bases : []);
      fetchOptions();
      fetchSop();
      fetchWikiCollections();
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
        // Only pick default if agent has no configured model
        const agentModel = String(((agent as any)?.config?.model) || '');
        if (!agentModel && models.length > 0) {
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

  const fetchWikiCollections = async () => {
    try {
      const r = await fetch('/api/core/wiki/collections');
      const data = await r.json();
      const cols = data.items || data.collections || [];
      setKbOptions(cols.map((c: any) => ({
        value: c.collection_id,
        label: `${c.collection_id} (${c.page_count} 页)`,
      })));
    } catch { }
  };

  // ── Ensure new skills/tools appear in MultiSelect options ──
  const _ensureOptions = (currentOpts: Array<{value: string; label: string}>, setter: any, newIds: string[]) => {
    const existing = new Set(currentOpts.map((o: any) => o.value));
    const missing = newIds.filter((id: string) => id && !existing.has(id));
    if (missing.length > 0) {
      setter((prev: any[]) => {
        const prevSet = new Set(prev.map((o: any) => o.value));
        const trulyMissing = missing.filter((id: string) => !prevSet.has(id));
        return trulyMissing.length > 0 ? [...prev, ...trulyMissing.map((id: string) => ({ value: id, label: id }))] : prev;
      });
    }
  };

  const handleSmartFill = async () => {
    if (!agent) return;
    const nm = name.trim() || agent.name || '';
    const desc = description.trim();
    if (!nm && !desc) { toast.warning('请先填写名称或描述'); return; }
    setSmartFillLoading(true);

    const applyResult = (result: any) => {
      if (result.agent_type) setLoopType(result.agent_type);
      if (result.config) {
        setConfigText(JSON.stringify(result.config, null, 2));
        const cfgModel = (result.config as any)?.model as string | undefined;
        if (cfgModel) {
          const norm = (s: string) => s.toLowerCase().replace(/^[a-z_]+:/, '').replace(/[-_]/g, '');
          const match = modelOptions.find(o => o.value === cfgModel)
            || modelOptions.find(o => norm(o.value) === norm(cfgModel));
          if (match) setSelectedModel(match.value);
        }
      }
      if (result.skills !== undefined) { setSkills([...result.skills]); _ensureOptions(skillOptions, setSkillOptions, result.skills); }
      if (result.tools !== undefined) { setTools([...result.tools]); _ensureOptions(toolOptions, setToolOptions, result.tools); }
      if (result.mcp_ids !== undefined) { setMcpIds([...result.mcp_ids]); }
      if (result.agent_ids !== undefined) setAgentIds([...result.agent_ids]);
      if (result.memory_config) setMemoryConfigText(JSON.stringify(result.memory_config, null, 2));
      if (result.sop_text) setSopText(result.sop_text);
      if (result.trigger_conditions !== undefined) setTriggerText(result.trigger_conditions.join('\n'));
      if (result.workflow_ids !== undefined) setWorkflowIds([...result.workflow_ids]);
      setMissingSkills(result.missing_skills || []);
      setMissingTools(result.missing_tools || []);
      setMissingMcps(result.missing_mcps || []);
    };

    try {
      // Step 1: Reuse existing role definition, or generate if none exists
      let roleDef: any = roleDefinition;
      if (!roleDef) {
        const roleInitRes: any = await workspaceAgentApi.generateRoleDefinition({ name: nm, description: desc, async_mode: true } as any);
        const roleTaskId = roleInitRes?.task_id;
        if (roleTaskId) {
          for (let i = 0; i < 60; i++) {
            await new Promise(r => setTimeout(r, 2000));
            const pollRes: any = await workspaceAgentApi.pollRoleDefinition(roleTaskId);
            if (pollRes.status === 'completed') { roleDef = pollRes.result; setRoleDefinition(roleDef); break; }
            if (pollRes.status === 'failed') break;
          }
        }
      }

      // Step 2: Auto-fill with role definition
      const initRes: any = await workspaceAgentApi.autoFillWithRole({
        name: nm, description: desc,
        role_definition: roleDef || {},
        async_mode: true,
      } as any);
      const taskId = initRes?.task_id;
      if (!taskId) throw new Error('No task_id returned');

      for (let i = 0; i < 60; i++) {
        await new Promise(r => setTimeout(r, 2000));
        const pollRes: any = await workspaceAgentApi.pollAutoFill(taskId);
        if (pollRes.status === 'completed') {
          applyResult(pollRes.result);
          if (roleDef) setRoleDefinition(roleDef);
          toast.success('AI 智能填充完成', pollRes.result?.reasoning || '已自动推荐 skills/tools/MCP/SOP');
          return;
        }
        if (pollRes.status === 'failed') {
          toast.error('智能填充失败', pollRes.error || 'LLM 服务繁忙，建议手动绑定 skills/tools');
          return;
        }
      }
      toast.error('等待超时', 'LLM 响应时间过长（>120s），建议稍后重试或手动绑定');
    } catch (e: any) {
      toast.error('智能填充失败', e?.message || String(e));
    } finally {
      setSmartFillLoading(false);
    }
  };

  const handleAutoFill = async () => {
    if (!agent) return;
    const nm = name.trim() || agent.name || '';
    const desc = description.trim();
    if (!nm && !desc) { toast.warning('请先填写名称或描述'); return; }
    setAutoFillLoading(true);
    try {
      const initRes: any = await workspaceAgentApi.generateRoleDefinition({ name: nm, description: desc, async_mode: true } as any);
      const taskId = initRes?.task_id;
      if (!taskId) throw new Error('No task_id returned');
      for (let i = 0; i < 60; i++) {
        await new Promise(r => setTimeout(r, 2000));
        const pollRes: any = await workspaceAgentApi.pollRoleDefinition(taskId);
        if (pollRes.status === 'completed') {
          const r = pollRes.result;
          if (r) {
            setRoleDefinition(r);
            setShowRolePreview(true);
            toast.success('角色定义已生成，请确认后继续填充');
          }
          return;
        }
        if (pollRes.status === 'failed') {
          toast.error('角色定义生成失败', pollRes.error || 'LLM 服务繁忙');
          return;
        }
      }
      toast.error('等待超时', 'LLM 响应时间过长（>120s），建议稍后重试');
    } catch (e: any) {
      toast.error('角色定义生成失败', e?.message || String(e));
    } finally {
      setAutoFillLoading(false);
    }
  };

  const handleAutoFillWithRole = async () => {
    if (!agent || !roleDefinition) return;
    setAutoFillLoading(true);
    try {
      const initRes: any = await workspaceAgentApi.autoFillWithRole({
        name: name.trim() || agent.name || '',
        description: description.trim(),
        role_definition: roleDefinition,
        async_mode: true,
      } as any);
      const taskId = initRes?.task_id;
      if (!taskId) throw new Error('No task_id returned');
      for (let i = 0; i < 60; i++) {
        await new Promise(r => setTimeout(r, 2000));
        const pollRes: any = await workspaceAgentApi.pollAutoFill(taskId);
        if (pollRes.status === 'completed') {
          const result = pollRes.result;
          if (result) {
            if (result.agent_type) setLoopType(result.agent_type);
            if (result.config) {
              setConfigText(JSON.stringify(result.config, null, 2));
              const cfgModel = (result.config as any)?.model as string | undefined;
              if (cfgModel) {
                const norm = (s: string) => s.toLowerCase().replace(/^[a-z_]+:/, '').replace(/[-_]/g, '');
                const match = modelOptions.find(o => o.value === cfgModel)
                  || modelOptions.find(o => norm(o.value) === norm(cfgModel));
                if (match) setSelectedModel(match.value);
              }
            }
            if (result.skills !== undefined) { setSkills([...result.skills]); _ensureOptions(skillOptions, setSkillOptions, result.skills); }
            if (result.tools !== undefined) { setTools([...result.tools]); _ensureOptions(toolOptions, setToolOptions, result.tools); }
            if (result.mcp_ids !== undefined) setMcpIds([...result.mcp_ids]);
            if (result.agent_ids !== undefined) setAgentIds([...result.agent_ids]);
            if (result.memory_config) setMemoryConfigText(JSON.stringify(result.memory_config, null, 2));
            if (result.sop_text) setSopText(result.sop_text);
            if (result.trigger_conditions !== undefined) setTriggerText(result.trigger_conditions.join('\n'));
            if (result.workflow_ids !== undefined) setWorkflowIds([...result.workflow_ids]);
            toast.success('AI 智能填充完成', result.reasoning || '已自动推荐 skills/tools/MCP/SOP');
            return;
          }
        }
        if (pollRes.status === 'failed') {
          toast.error('智能填充失败', pollRes.error || 'LLM 服务繁忙');
          return;
        }
      }
      toast.error('等待超时', 'LLM 响应时间过长（>120s），建议稍后重试');
    } catch (e: any) {
      toast.error('智能填充失败', e?.message || String(e));
    } finally {
      setAutoFillLoading(false);
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
      metadata.knowledge_bases = knowledgeBases;

      await workspaceAgentApi.update(agent.id, { name: name.trim() || undefined, status: agentStatus || undefined, config, skills: skills.length ? skills : undefined, tools: tools.length ? tools : undefined, mcp_ids: mcpIds.length ? mcpIds : undefined, workflow_ids: workflowIds.length ? workflowIds : undefined, agent_ids: agentIds.length ? agentIds : undefined, memory_config, metadata,
        ...(triggerText.trim() ? { trigger_conditions: triggerText.split('\n').map(s => s.trim()).filter(Boolean) } : {}),
        ...(permissionsText.trim() ? { permissions: JSON.parse(permissionsText) as string[] } : {}),
      });

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

  const handleAudit = async () => {
    if (!agent) return;
    setAuditLoading(true);
    setAuditResult(null);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30000);
    try {
      const res: any = await workspaceAgentApi.audit(agent.id);
      setAuditResult(res);
      if (res.summary?.total === 0) {
        toast.success('审核通过，配置无问题');
      } else {
        toast.success(`审核完成: ${res.summary?.errors || 0} 错误 ${res.summary?.warnings || 0} 警告`);
      }
    } catch (e: any) {
      clearTimeout(timeout);
      if (e.name === 'AbortError') {
        toast.error('审核超时', 'Core 服务首次响应较慢，请稍后重试');
      } else {
        toast.error('审核失败', String(e?.message || ''));
      }
    } finally {
      clearTimeout(timeout);
      setAuditLoading(false);
    }
  };

  const applyAuditFixLocal = (fix: any): boolean => {
    if (!fix?.type) return false;
    if (fix.type === 'replace_tool') {
      setTools((prev) => {
        const next = prev.map((t) => (t === fix.from ? fix.to : t));
        return next.includes(fix.to) ? next : [...next, fix.to];
      });
      _ensureOptions(toolOptions, setToolOptions, [String(fix.to)]);
      return true;
    }
    if (fix.type === 'remove_tool') {
      setTools((prev) => prev.filter((t) => t !== fix.tool));
      return true;
    }
    if (fix.type === 'migrate_field') {
      const keep = Array.isArray(fix.keep) ? fix.keep.map(String) : [];
      setTools((prev) => {
        const cleaned = prev.filter((t) => t !== 'knowledge_retrieve' && t !== 'knowledge_retrieval');
        return [...new Set([...cleaned, ...keep])];
      });
      if (keep.length) _ensureOptions(toolOptions, setToolOptions, keep);
      return true;
    }
    if (fix.type === 'add_skill') {
      setSkills((prev) => (prev.includes(fix.skill) ? prev : [...prev, fix.skill]));
      return true;
    }
    if (fix.type === 'set_kb_collection') {
      setKnowledgeBases([fix.collection]);
      return true;
    }
    if (fix.type === 'set_status') {
      setAgentStatus(String(fix.status || 'ready'));
      return true;
    }
    if (fix.type === 'set_system_prompt') {
      const sp = String(fix.system_prompt || '').trim();
      if (!sp) return false;
      try {
        const cfg = configText?.trim() ? JSON.parse(configText) : {};
        cfg.system_prompt = sp;
        if (selectedModel && !cfg.model) cfg.model = selectedModel;
        setConfigText(JSON.stringify(cfg, null, 2));
      } catch {
        setConfigText(JSON.stringify({ model: selectedModel || 'qwen2.5:3b', system_prompt: sp }, null, 2));
      }
      return true;
    }
    return false;
  };

  const applyAuditFix = async (fix: any) => {
    if (!agent || !fix) return;
    try {
      const ok = applyAuditFixLocal(fix);
      if (!ok) {
        toast.warning('该问题暂无自动修复');
        return;
      }
      toast.success('已应用到表单，请点「保存」写入 AGENT.md');
    } catch (e: any) {
      toast.error('修复失败', String(e?.message || ''));
    }
  };

  const handleApplyAllFixes = async () => {
    if (!agent || !auditResult?.issues) return;
    const fixable = auditResult.issues.filter((i: any) => i.fix_available && i.fix);
    if (!fixable.length) {
      toast.info('没有可自动修复的问题');
      return;
    }
    try {
      setLoading(true);
      // 1) Apply all fixes into local React state (order: replace → migrate → others)
      const ordered = [...fixable].sort((a: any, b: any) => {
        const rank = (t: string) =>
          t === 'replace_tool' ? 0 : t === 'remove_tool' ? 1 : t === 'migrate_field' ? 2 : 3;
        return rank(String(a.fix?.type || '')) - rank(String(b.fix?.type || ''));
      });
      let applied = 0;
      let nextTools = [...tools];
      let nextSkills = [...skills];
      let nextStatus = agentStatus;
      let nextKb = [...knowledgeBases];
      let nextConfigText = configText;

      for (const issue of ordered) {
        const fix = issue.fix;
        if (!fix?.type) continue;
        if (fix.type === 'replace_tool') {
          nextTools = nextTools.map((t) => (t === fix.from ? fix.to : t));
          if (!nextTools.includes(fix.to)) nextTools.push(fix.to);
          applied += 1;
        } else if (fix.type === 'remove_tool') {
          nextTools = nextTools.filter((t) => t !== fix.tool);
          applied += 1;
        } else if (fix.type === 'migrate_field') {
          const keep = Array.isArray(fix.keep) ? fix.keep.map(String) : [];
          nextTools = [...new Set([
            ...nextTools.filter((t) => t !== 'knowledge_retrieve' && t !== 'knowledge_retrieval'),
            ...keep,
          ])];
          applied += 1;
        } else if (fix.type === 'add_skill') {
          if (!nextSkills.includes(fix.skill)) nextSkills.push(fix.skill);
          applied += 1;
        } else if (fix.type === 'set_kb_collection') {
          nextKb = [fix.collection];
          applied += 1;
        } else if (fix.type === 'set_status') {
          nextStatus = String(fix.status || 'ready');
          applied += 1;
        } else if (fix.type === 'set_system_prompt') {
          const sp = String(fix.system_prompt || '').trim();
          if (sp) {
            try {
              const cfg = nextConfigText?.trim() ? JSON.parse(nextConfigText) : {};
              cfg.system_prompt = sp;
              if (selectedModel && !cfg.model) cfg.model = selectedModel;
              nextConfigText = JSON.stringify(cfg, null, 2);
            } catch {
              nextConfigText = JSON.stringify(
                { model: selectedModel || 'qwen2.5:3b', system_prompt: sp },
                null,
                2,
              );
            }
            applied += 1;
          }
        }
      }

      setTools(nextTools);
      setSkills(nextSkills);
      setAgentStatus(nextStatus);
      setKnowledgeBases(nextKb);
      setConfigText(nextConfigText);
      _ensureOptions(toolOptions, setToolOptions, nextTools);
      _ensureOptions(skillOptions, setSkillOptions, nextSkills);

      // 2) Persist immediately so subsequent audit reads fixed AGENT.md
      let config: Record<string, unknown> = {};
      try {
        config = nextConfigText?.trim() ? JSON.parse(nextConfigText) : {};
      } catch {
        toast.error('配置 JSON 格式错误，已应用表单但未保存');
        setLoading(false);
        return;
      }
      let memory_config: Record<string, unknown> | undefined;
      if (memoryConfigText?.trim()) {
        try {
          memory_config = JSON.parse(memoryConfigText);
        } catch {
          toast.error('memory_config JSON 格式错误');
          setLoading(false);
          return;
        }
      }
      const metadata: Record<string, unknown> = { ...(agent.metadata || {}) };
      if (description.trim()) metadata.description = description.trim();
      metadata.generate_test_plan = generateTestPlan;
      metadata.auto_hitl = autoHitl;
      metadata.phase_description = phaseDescription.trim() || undefined;
      metadata.hitl_after_execute = hitlAfterExecute;
      metadata.hitl_after_phase = hitlAfterPhase.trim() || undefined;
      metadata.loop_type = loopType;
      metadata.knowledge_bases = nextKb;
      if (defaultToolset && defaultToolset !== 'workspace_default') metadata.toolset = defaultToolset;
      else delete (metadata as any).toolset;

      await workspaceAgentApi.update(agent.id, {
        name: name.trim() || undefined,
        status: nextStatus || undefined,
        config,
        skills: nextSkills.length ? nextSkills : undefined,
        tools: nextTools.length ? nextTools : [],
        mcp_ids: mcpIds.length ? mcpIds : undefined,
        workflow_ids: workflowIds.length ? workflowIds : undefined,
        agent_ids: agentIds.length ? agentIds : undefined,
        memory_config,
        metadata,
        ...(triggerText.trim()
          ? { trigger_conditions: triggerText.split('\n').map((s) => s.trim()).filter(Boolean) }
          : {}),
        ...(permissionsText.trim() ? { permissions: JSON.parse(permissionsText) as string[] } : {}),
      });

      // sync tool/skill bindings
      try {
        const curSkillsRes = await workspaceAgentApi.getSkills(agent.id);
        const curToolsRes = await workspaceAgentApi.getTools(agent.id);
        const curSkills = new Set<string>(((curSkillsRes as any).skill_ids || []) as string[]);
        const curTools = new Set<string>(((curToolsRes as any).tool_ids || []) as string[]);
        const desiredSkills = new Set(nextSkills);
        const desiredTools = new Set(nextTools);
        await Promise.all(
          Array.from(curSkills)
            .filter((id) => !desiredSkills.has(id))
            .map((id) => workspaceAgentApi.unbindSkill(agent.id, id)),
        );
        await Promise.all(
          Array.from(curTools)
            .filter((id) => !desiredTools.has(id))
            .map((id) => workspaceAgentApi.unbindTool(agent.id, id)),
        );
        const toAddSkills = Array.from(desiredSkills).filter((id) => !curSkills.has(id));
        const toAddTools = Array.from(desiredTools).filter((id) => !curTools.has(id));
        if (toAddSkills.length) await workspaceAgentApi.bindSkills(agent.id, toAddSkills);
        if (toAddTools.length) await workspaceAgentApi.bindTools(agent.id, toAddTools);
      } catch {
        // binding sync best-effort
      }

      toast.success(`已自动修复 ${applied} 项并保存，正在重新审核…`);
      await handleAudit();
    } catch (e: any) {
      toast.error('一键修复失败', String(e?.message || e?.detail || ''));
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
      title={`编辑应用库 Agent${name ? ` · ${name}` : ''}`}
      width={880}
      footer={
        <>
          <Button variant="secondary" onClick={handleSmartFill} loading={smartFillLoading}>
            🤖 一键生成全部
          </Button>
          <Button variant="secondary" onClick={handleAudit} loading={auditLoading}>
            🔍 AI 审核
          </Button>
          <div className="flex-1" />
          <Button variant="secondary" onClick={onClose} disabled={loading}>
            取消
          </Button>
          <Button variant="primary" onClick={handleSubmit} loading={loading}>
            保存
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        {auditResult && (
          <div className={`p-3 rounded-lg border text-xs ${
            auditResult.summary?.health === 'A' ? 'border-green-500/30 bg-green-900/10' :
            auditResult.summary?.health === 'B' ? 'border-blue-500/30 bg-blue-900/10' :
            'border-yellow-500/30 bg-yellow-900/10'
          }`}>
            <div className="flex items-center justify-between mb-2">
              <span className="font-semibold text-gray-200">
                🔍 审核结果 ({auditResult.summary?.health || '?'})
              </span>
              <span className="text-gray-500">
                {auditResult.summary?.errors || 0}错误 {auditResult.summary?.warnings || 0}警告 {auditResult.summary?.info || 0}提示
              </span>
            </div>
            {auditResult.issues?.map((issue: any, idx: number) => (
              <div key={idx} className={`flex items-start gap-2 py-1.5 ${
                idx < auditResult.issues.length - 1 ? 'border-b border-dark-border/30' : ''
              }`}>
                <span className="mt-0.5">
                  {issue.severity === 'error' ? '❌' : issue.severity === 'warning' ? '⚠️' : 'ℹ️'}
                </span>
                <div className="flex-1">
                  <div className="text-gray-300">{issue.message}</div>
                  {issue.suggestion && (
                    <div className="text-gray-500 mt-0.5">{issue.suggestion}</div>
                  )}
                </div>
                {issue.fix_available && issue.fix && (
                  <Button
                    variant="secondary"
                    size="sm"
                    className="text-[10px] py-0 px-2 h-6 whitespace-nowrap"
                    onClick={() => applyAuditFix(issue.fix)}
                  >
                  {issue.fix.type === 'replace_tool' ? `替换 → ${issue.fix.to}` :
                   issue.fix.type === 'remove_tool' ? '移除' :
                   issue.fix.type === 'add_skill' ? `+${issue.fix.skill}` :
                   issue.fix.type === 'set_kb_collection' ? '设置知识库' : '修复'}
                </Button>
              )}
            </div>
          ))}
          {auditResult.issues?.some((i: any) => i.fix_available && i.fix) && (
            <div className="mt-2 pt-2 border-t border-dark-border/30">
              <Button variant="primary" size="sm" onClick={handleApplyAllFixes}>
                ⚡ 一键修复全部
              </Button>
            </div>)}
          </div>
        )}

        <div className="flex flex-wrap gap-2 text-[11px] text-gray-500">
          <span className="px-2 py-0.5 rounded bg-dark-card border border-dark-border">技能 {skills.length}</span>
          <span className="px-2 py-0.5 rounded bg-dark-card border border-dark-border">工具 {tools.length}</span>
          <span className="px-2 py-0.5 rounded bg-dark-card border border-dark-border">子Agent {agentIds.length}</span>
          <span className="px-2 py-0.5 rounded bg-dark-card border border-dark-border">知识库 {knowledgeBases.length}</span>
          <span className="px-2 py-0.5 rounded bg-dark-card border border-dark-border">模型 {selectedModel || '—'}</span>
        </div>

        <Tabs
          key={agent?.id || 'edit-agent'}
          defaultActiveKey="basic"
          tabs={[
            {
              key: 'basic',
              label: '基本信息',
              children: (
          <div className="space-y-3">
            <Input label="名称（显示名）" value={name} onChange={(e: any) => setName(e.target.value)} />
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">功能描述</label>
              <Textarea
                value={description}
                onChange={(e: any) => setDescription(e.target.value)}
                rows={3}
                placeholder="描述功能目标与适用场景；一键生成会据此推荐绑定与 SOP"
              />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">状态</label>
                {['draft', 'ready'].includes(agentStatus) ? (
                  <select value={agentStatus} onChange={(e) => setAgentStatus(e.target.value)}
                    className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100">
                    <option value="draft">draft（草稿）</option>
                    <option value="ready">ready（待审核）</option>
                  </select>
                ) : (
                  <div className="w-full min-h-10 px-3 py-2 flex flex-wrap items-center gap-2 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-400">
                    <span>
                      {agentStatus === 'published' ? '已发布' :
                       agentStatus === 'listed' ? '已上架' :
                       agentStatus === 'deprecated' ? '已废弃 — 只读' :
                       agentStatus}
                    </span>
                    {agentStatus !== 'deprecated' && (
                      <a href="/approval?type=agent" className="text-amber-300 underline text-xs">去资产审批</a>
                    )}
                  </div>
                )}
              </div>
              <div>
                <div className="text-sm font-medium text-gray-300 mb-1">模型</div>
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
                    <option key={m.value} value={m.value}>{m.label}</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <div className="text-sm font-medium text-gray-300 mb-1">默认 Toolset</div>
                <select
                  value={defaultToolset}
                  onChange={(e) => setDefaultToolset(e.target.value)}
                  className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100"
                >
                  <option value="workspace_default">workspace_default（默认）</option>
                  <option value="safe_readonly">safe_readonly（只读）</option>
                  <option value="mcp_readonly">mcp_readonly（MCP）</option>
                  <option value="browser">browser（浏览器/HTTP）</option>
                  <option value="full">full（全量/高风险）</option>
                </select>
                <div className="text-[10px] text-gray-500 mt-1">写入 metadata.toolset；执行时可临时覆盖</div>
              </div>
              <div>
                <div className="text-sm font-medium text-gray-300 mb-1">Agent 策略</div>
                <select
                  value={loopType}
                  onChange={(e) => setLoopType(e.target.value)}
                  className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100"
                >
                  <option value="react">ReAct — 透明推理循环</option>
                  <option value="function_call">Function Calling — 原生工具调用</option>
                </select>
              </div>
            </div>
            <details className="rounded-lg border border-dark-border bg-dark-card/30">
              <summary className="cursor-pointer px-3 py-2 text-sm text-gray-400 hover:text-gray-200">触发词 / 权限（可选）</summary>
              <div className="px-3 pb-3 space-y-2 border-t border-dark-border/50">
                <Textarea label="trigger_conditions（每行一条）" rows={2} value={triggerText} onChange={(e: any) => setTriggerText(e.target.value)} placeholder="例如：帮我分析需求" />
                <Textarea label="permissions（JSON 数组）" rows={2} value={permissionsText} onChange={(e: any) => setPermissionsText(e.target.value)} placeholder='["llm:generate"]' />
              </div>
            </details>
            <details className="rounded-lg border border-dark-border bg-dark-card/30">
              <summary className="cursor-pointer px-3 py-2 text-sm text-gray-400 hover:text-gray-200">流水线配置</summary>
              <div className="px-3 pb-3 space-y-2 border-t border-dark-border/50">
                <Input label="阶段描述（phase_description）" value={phaseDescription} onChange={(e: any) => setPhaseDescription(e.target.value)} placeholder="如：需求分析与PRD生成" />
                <label className="flex items-center gap-2 text-xs text-gray-400">
                  <input type="checkbox" checked={generateTestPlan} onChange={(e) => setGenerateTestPlan(e.target.checked)} className="w-4 h-4" />
                  自动生成测试计划
                </label>
                <label className="flex items-center gap-2 text-xs text-gray-400">
                  <input type="checkbox" checked={autoHitl} onChange={(e) => setAutoHitl(e.target.checked)} className="w-4 h-4" />
                  自动启用 HITL
                </label>
                <label className="flex items-center gap-2 text-xs text-gray-400">
                  <input type="checkbox" checked={hitlAfterExecute} onChange={(e) => setHitlAfterExecute(e.target.checked)} className="w-4 h-4" />
                  执行后暂停
                </label>
                {hitlAfterExecute && (
                  <Input label="暂停阶段名" value={hitlAfterPhase} onChange={(e: any) => setHitlAfterPhase(e.target.value)} />
                )}
              </div>
            </details>
            <div className="flex flex-wrap gap-2 justify-end">
              <Button variant="secondary" onClick={handleAutoFill} loading={autoFillLoading}>
                📋 生成角色定义
              </Button>
              {showRolePreview && roleDefinition && (
                <Button variant="primary" onClick={handleAutoFillWithRole} loading={autoFillLoading}>
                  ✨ 更新推荐配置
                </Button>
              )}
            </div>
            {showRolePreview && roleDefinition && (
              <div className="bg-blue-900/20 border border-blue-500/20 rounded-lg p-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium text-blue-300">角色定义 JSON</span>
                  <button
                    type="button"
                    onClick={() => { setShowRolePreview(false); setRoleDefinition(null); }}
                    className="text-xs text-gray-500 hover:text-gray-300"
                  >
                    关闭
                  </button>
                </div>
                <Textarea
                  value={JSON.stringify(roleDefinition, null, 2)}
                  onChange={(e: any) => {
                    try { setRoleDefinition(JSON.parse(e.target.value)); } catch { /* keep editing */ }
                  }}
                  rows={8}
                />
              </div>
            )}
          </div>
              ),
            },
            {
              key: 'bindings',
              label: `能力绑定 (${skills.length + tools.length + mcpIds.length + workflowIds.length + agentIds.length + knowledgeBases.length})`,
              children: (
          <div className="space-y-4">
            <p className="text-xs text-gray-500">已选项显示为标签；在搜索框中查找并添加，不再整页铺满「+」按钮。</p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <MultiSelect label="绑定技能" options={skillOptions} selected={skills} onChange={setSkills} />
                {missingSkills.length > 0 && (
                  <div className="text-yellow-400 text-xs bg-yellow-900/20 border border-yellow-800 rounded px-3 py-2 mt-1 space-y-1">
                    <p className="font-medium">⚠️ Skill 库未找到匹配：</p>
                    {missingSkills.map((m: any, i: number) => (
                      <div key={i} className="ml-2 border-l-2 border-yellow-700 pl-2">
                        <p>需要：<b>{m.capability}</b> → 建议：<code>{m.suggested_name}</code></p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <div>
                <MultiSelect label="绑定工具" options={toolOptions} selected={tools} onChange={setTools} />
                {missingTools.length > 0 && (
                  <div className="text-yellow-400 text-xs bg-yellow-900/20 border border-yellow-800 rounded px-3 py-2 mt-1 space-y-1">
                    <p className="font-medium">⚠️ 建议补充工具：</p>
                    {missingTools.map((m: any, i: number) => (
                      <div key={i} className="ml-2 border-l-2 border-yellow-700 pl-2">
                        <p><b>{m.tool}</b> — {m.reason}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
            {missingMcps.length > 0 && (
              <div className="text-yellow-400 text-xs bg-yellow-900/20 border border-yellow-800 rounded px-3 py-2 space-y-1">
                <p className="font-medium">⚠️ 建议配置 MCP：</p>
                {missingMcps.map((m: any, i: number) => (
                  <p key={i} className="ml-2">{m.description}</p>
                ))}
              </div>
            )}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {mcpOptions.length > 0 && <MultiSelect label="绑定 MCP" options={mcpOptions} selected={mcpIds} onChange={setMcpIds} />}
              {workflowOptions.length > 0 && (
                <MultiSelect
                  label="关联 Workflow（可选）"
                  options={workflowOptions}
                  selected={workflowIds}
                  onChange={setWorkflowIds}
                  hint="编排模板关联，非运行时必绑；日常执行靠 Skill/Tool/MCP。空着即可。"
                />
              )}
            </div>
            {agentOptions.length > 0 && (
              <MultiSelect label="绑定子 Agent" options={agentOptions} selected={agentIds} onChange={setAgentIds} hint="可将任务委派给选中的子 Agent" />
            )}
            {kbOptions.length > 0 && (
              <MultiSelect label="知识库（Wiki 集合）" options={kbOptions} selected={knowledgeBases} onChange={setKnowledgeBases} hint="不选则默认 default" />
            )}
          </div>
              ),
            },
            {
              key: 'advanced',
              label: 'SOP / 高级',
              children: (
          <div className="space-y-3">
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-medium text-gray-300">SOP（Markdown）</span>
                {sopLoading && <span className="text-xs text-gray-500">加载中…</span>}
              </div>
              <Textarea
                value={sopText}
                onChange={(e: any) => setSopText(e.target.value)}
                rows={12}
                placeholder="角色定义与工作流程（写入 AGENT.md body）"
              />
            </div>
            <Textarea label="配置（JSON）" value={configText} onChange={(e: any) => setConfigText(e.target.value)} rows={6} />
            <div className="flex gap-2">
              <Button variant="ghost" size="sm" onClick={() => {
                try {
                  const cfg = JSON.parse(configText || '{}');
                  const sp = cfg.system_prompt || '';
                  if (!sp) { toast.warning('配置中无 system_prompt 可优化'); return; }
                  setOptimizePrompt(sp);
                  setOptimizeOpen(true);
                } catch { toast.warning('配置 JSON 格式错误'); }
              }}>🤖 AI 优化 System Prompt</Button>
            </div>
            <Textarea label="memory_config（JSON，可选）" value={memoryConfigText} onChange={(e: any) => setMemoryConfigText(e.target.value)} rows={4} />
            <Alert type="info" title="说明">
              {configHint} {configHint2}
            </Alert>
          </div>
              ),
            },
          ]}
        />
      </div>
    </Modal>

    <PromptDiffModal
      open={optimizeOpen}
      title="AI 优化 Agent System Prompt"
      original={optimizePrompt}
      onClose={() => setOptimizeOpen(false)}
      onApply={(optimized) => {
        try {
          const cfg = configText?.trim() ? JSON.parse(configText) : {};
          cfg.system_prompt = optimized;
          setConfigText(JSON.stringify(cfg, null, 2));
          if (agent) {
            workspaceAgentApi.update(agent.id as string, { config: cfg }).catch(() => {});
          }
          toast.success('已应用并保存优化');
        } catch { toast.error('应用失败'); }
      }}
    />
    </>
  );
};

export default EditAgentModal;
