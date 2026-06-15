import React, { useEffect, useMemo, useState } from 'react';
import { workspaceAgentApi, workspaceSkillApi } from '../../services';
import { modelApi, toolApi, type Model } from '../../services';
import { workspaceMcpApi, workflowTemplateApi } from '../../services';
import { Alert, Button, Input, Modal, Select, Textarea, toast, MultiSelect } from '../ui';
import PromptDiffModal from './PromptDiffModal';
import { diagnosticsApi } from '../../services';

interface AgentConfigTemplate {
  name: string;
  description: string;
  config: Record<string, unknown>;
}

const AGENT_TYPE_TEMPLATES: Record<string, AgentConfigTemplate> = {
  base: {
    name: '基础Agent',
    description: '最基础的对话Agent，适用于简单问答场景',
    config: { model: '', temperature: 0.7, max_tokens: 2048, system_prompt: '你是一个有帮助的AI助手。' },
  },
  react: {
    name: 'ReAct Agent',
    description: '使用ReAct（Reasoning + Acting）模式，具备推理和工具调用能力',
    config: { model: '', temperature: 0.0, max_tokens: 4096, reasoning_steps: 3, system_prompt: '你是一个使用ReAct模式的推理Agent。' },
  },
  plan: {
    name: '规划型Agent',
    description: '具备任务分解和规划能力，适合复杂多步骤任务',
    config: { model: '', temperature: 0.1, max_tokens: 8192, planning_enabled: true, max_subtasks: 10, system_prompt: '你是一个任务规划Agent。' },
  },
  tool: {
    name: '工具型Agent',
    description: '专注于工具调用和自动化执行的Agent',
    config: { model: '', temperature: 0.0, max_tokens: 2048, system_prompt: '你是一个工具型Agent。' },
  },
};

interface AddAgentModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

const AddAgentModal: React.FC<AddAgentModalProps> = ({ open, onClose, onSuccess }) => {
  const [loading, setLoading] = useState(false);
  const [selectedType, setSelectedType] = useState<string>('base');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [skills, setSkills] = useState<string[]>([]);
  const [tools, setTools] = useState<string[]>([]);
  const [mcpIds, setMcpIds] = useState<string[]>([]);
  const [workflowIds, setWorkflowIds] = useState<string[]>([]);
  const [agentIds, setAgentIds] = useState<string[]>([]);
  const [configText, setConfigText] = useState('');
  const [memoryConfigText, setMemoryConfigText] = useState('{\n  "type": "short_term",\n  "recall_count": 5\n}');
  const [sopText, setSopText] = useState('');
  const [triggerText, setTriggerText] = useState('');
  const [permissionsText, setPermissionsText] = useState('["llm:generate"]');
  const [skillOptions, setSkillOptions] = useState<Array<{ value: string; label: string }>>([]);
  const [toolOptions, setToolOptions] = useState<Array<{ value: string; label: string }>>([]);
  const [mcpOptions, setMcpOptions] = useState<Array<{ value: string; label: string }>>([]);
  const [workflowOptions, setWorkflowOptions] = useState<Array<{ value: string; label: string }>>([]);
  const [agentOptions, setAgentOptions] = useState<Array<{ value: string; label: string }>>([]);
  const [modelOptions, setModelOptions] = useState<Array<{ value: string; label: string }>>([]);
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [knowledgeBases, setKnowledgeBases] = useState<string[]>([]);
  const [kbOptions, setKbOptions] = useState<Array<{ value: string; label: string }>>([]);
  const [autoSmoke, setAutoSmoke] = useState(true);
  const [autoFillLoading, setAutoFillLoading] = useState(false);
  const [optimizeOpen, setOptimizeOpen] = useState(false);
  const [optimizePrompt, setOptimizePrompt] = useState('');
  const [configEdited, setConfigEdited] = useState(false);

  // Disambiguation wizard
  const [wizOpen, setWizOpen] = useState(false);
  const [wizMode, setWizMode] = useState<'manual' | 'auto'>('manual');
  const [wizSources, setWizSources] = useState<string[]>([]);
  const [wizMayWrite, setWizMayWrite] = useState(false);
  const [genWarnings, setGenWarnings] = useState<string[]>([]);

  // Import mode (file/URL import with AI detection)
  const [sourceMode, setSourceMode] = useState<'manual' | 'url' | 'file'>('manual');
  const [importUrl, setImportUrl] = useState('');
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importDetecting, setImportDetecting] = useState(false);
  const [importResult, setImportResult] = useState<any>(null);
  const [importMeta, setImportMeta] = useState<Record<string, any>>({});
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setSelectedType('base');
      setName('');
      setDescription('');
      setSkills([]);
      setTools([]);
      setMcpIds([]);
      setWorkflowIds([]);
      setAgentIds([]);
      setConfigText(JSON.stringify(AGENT_TYPE_TEMPLATES.base.config, null, 2));
      setMemoryConfigText('{\n  "type": "short_term",\n  "recall_count": 5\n}');
      setSopText('');
      setTriggerText('');
      setKnowledgeBases([]);
      setConfigEdited(false);
      fetchOptions();
      fetchWikiCollections();
    }
  }, [open]);

  React.useEffect(() => {
    setImportUrl('');
    setImportFile(null);
    setImportResult(null);
    setImportMeta({});
  }, [sourceMode]);

  const handleImportDetect = async () => {
    if (sourceMode === 'url' && !importUrl.trim()) { toast.warning('请输入 GitHub URL'); return; }
    if (sourceMode === 'file' && !importFile) { toast.warning('请选择本地 Zip 文件'); return; }
    setImportDetecting(true);
    try {
      const payload: any = {};
      if (sourceMode === 'url') {
        payload.url = importUrl.trim();
      } else if (sourceMode === 'file' && importFile) {
        const buf = await importFile.arrayBuffer();
        const bytes = new Uint8Array(buf);
        let binary = '';
        for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
        payload.file_content = btoa(binary);
      }
      const res = await workspaceAgentApi.importDetect(payload);
      if (res.error) { toast.error('检测失败', res.error); return; }
      setImportResult(res);
      if (res.detected_name && !name) setName(res.detected_name);
      if (res.detected_description && !description) setDescription(res.detected_description);
      if (res.agent_type) setSelectedType(res.agent_type);
      if (res.sop_body) setSopText(res.sop_body);
      if (res.trigger_conditions?.length) setTriggerText(res.trigger_conditions.join('\n'));
      else if (sourceMode !== 'manual') setTriggerText('');
      if (res.config) {
        setConfigText(JSON.stringify(res.config, null, 2));
        setConfigEdited(true);
      }
      if (res.skills?.length) setSkills(res.skills);
      if (res.tools?.length) setTools(res.tools);
      if (res.mcp_ids?.length) setMcpIds(res.mcp_ids);
      if (res.agent_ids?.length) setAgentIds(res.agent_ids);
      if (res.permissions?.length) setPermissionsText(JSON.stringify(res.permissions, null, 2));
      setImportMeta({
        ...(res.tools ? { tools: res.tools } : {}),
        ...(sourceMode === 'url' && importUrl.trim() ? { source_url: importUrl.trim() } : {}),
      });
      if (sourceMode === 'file' && importFile) {
        try {
          const buf2 = await importFile.arrayBuffer();
          const bytes2 = new Uint8Array(buf2);
          let binary2 = '';
          for (let i = 0; i < bytes2.length; i++) binary2 += String.fromCharCode(bytes2[i]);
          setImportMeta((prev: any) => ({ ...prev, source_file_content: btoa(binary2) }));
        } catch { }
      }
      toast.success('AI 检测完成');
    } catch (e: any) {
      toast.error('检测失败', e?.detail || e?.message || String(e));
    } finally { setImportDetecting(false); }
  };

  const fetchWikiCollections = async () => {
    try {
      const r = await fetch('/api/core/wiki/collections');
      const data = await r.json();
      const cols = data.collections || [];
      setKbOptions(cols.map((c: any) => ({
        value: c.collection_id,
        label: `${c.collection_id} (${c.page_count} 页)`,
      })));
    } catch { }
  };

  const fetchOptions = async () => {
    try {
      const [skillRes, toolRes, modelRes] = await Promise.all([
        workspaceSkillApi.list({ limit: 200 }),
        toolApi.list({ limit: 200 } as any),
        modelApi.list({ enabled: true, status: 'available' }),
      ]);
      const baseSkillOptions = (skillRes.skills || []).map((s: any) => ({ value: s.id, label: s.name }));
      const baseToolOptions = (toolRes.tools || []).map((t: any) => ({ value: t.name, label: t.description || t.name }));
      // If user already selected ids not present in options, keep them visible.
      const skillSet = new Set(baseSkillOptions.map((o: any) => o.value));
      const toolSet = new Set(baseToolOptions.map((o: any) => o.value));
      const missingSkillOptions = (skills || [])
        .filter((id) => id && !skillSet.has(id))
        .map((id) => ({ value: id, label: `${id}（未在 Skill 库中找到）` }));
      const missingToolOptions = (tools || [])
        .filter((id) => id && !toolSet.has(id))
        .map((id) => ({ value: id, label: `${id}（未在 Tool 列表中找到）` }));
      setSkillOptions([...baseSkillOptions, ...missingSkillOptions]);
      setToolOptions([...baseToolOptions, ...missingToolOptions]);

      try {
        const mcpRes = await workspaceMcpApi.listServers();
        const mcpList = (mcpRes as any).servers || [];
        setMcpOptions(mcpList.map((s: any) => ({ value: s.name || s.id, label: `${s.name || s.id} (MCP)` })));
      } catch { /* ignore */ }

      try {
        const wfRes = await workflowTemplateApi.list();
        const wfList = (wfRes as any).templates || [];
        setWorkflowOptions(wfList.map((w: any) => ({ value: w.name, label: `${w.label || w.name} (Workflow)` })));
      } catch { /* ignore */ }

      try {
        const agentRes = await workspaceAgentApi.list({ limit: 200 });
        const agentList = (agentRes as any).agents || [];
        setAgentOptions(agentList.filter((a: any) => a.name).map((a: any) => ({ value: a.id || a.name, label: `${a.name || a.id} (Agent)` })));
      } catch { /* ignore */ }

      const models = ((modelRes as any).models || []) as Model[];
      const modelOpts = models.map((m) => ({ value: m.name, label: m.displayName || m.name }));
      setModelOptions(modelOpts);
      // default: DeepSeek Reasoner if available, else keep existing, else first model
      const prefer = models.find((m) => (m.displayName || '').toLowerCase().includes('deepseek') && (m.displayName || '').toLowerCase().includes('reasoner'))
        || models.find((m) => (m.name || '').toLowerCase().includes('deepseek') && (m.name || '').toLowerCase().includes('reasoner'));
      const fallback = prefer?.name || selectedModel || models[0]?.name || '';
      if (fallback) {
        setSelectedModel(fallback);
        // best-effort sync to configText
        try {
          const cfg = configText?.trim() ? JSON.parse(configText) : {};
          cfg.model = fallback;
          setConfigText(JSON.stringify(cfg, null, 2));
        } catch {
          setConfigText(JSON.stringify({ model: fallback, temperature: 0.3 }, null, 2));
        }
      }
    } catch {
      setSkillOptions([]);
      setToolOptions([]);
      setModelOptions([]);
    }
  };

  const maybeRunSmoke = async () => {
    if (!autoSmoke) return;
    try {
      const smoke = await diagnosticsApi.runE2ESmoke({ tenant_id: 'ops_smoke', actor_id: 'admin', agent_model: 'deepseek-reasoner' });
      toast.success(smoke?.ok ? '全链路冒烟通过' : '全链路冒烟失败');
    } catch (e: any) {
      toast.error('全链路冒烟失败', String(e?.message || 'unknown'));
    }
  };

  const handleAutoFill = async () => {
    if (!name.trim() && !description.trim()) {
      toast.warning('请先填写名称或功能描述');
      return;
    }
    setAutoFillLoading(true);
    try {
      const result = await workspaceAgentApi.autoFill({ name: name.trim(), description: description.trim() });
      // Populate form fields from AI response
      if (result.agent_type) setSelectedType(result.agent_type);
      if (result.config) {
        setConfigText(JSON.stringify(result.config, null, 2));
        // sync model to dropdown
        const cfgModel = (result.config as any)?.model as string | undefined;
        if (cfgModel) {
          // match model ID/name against dropdown options (handle id vs name differences, e.g. "ollama:qwen2-5-coder-7b" vs "qwen2.5-coder:7b")
          const norm = (s: string) => s.toLowerCase().replace(/^[a-z_]+:/, '').replace(/[-_]/g, '');
          const match = modelOptions.find(o => o.value === cfgModel)
            || modelOptions.find(o => norm(o.value) === norm(cfgModel));
          if (match) setSelectedModel(match.value);
        }
      }
      if (result.skills?.length) setSkills(result.skills.filter((s: string) => skillOptions.some(o => o.value === s)));
      if (result.tools?.length) setTools(result.tools.filter((t: string) => toolOptions.some(o => o.value === t)));
      if (result.mcp_ids?.length) setMcpIds(result.mcp_ids.filter((m: string) => mcpOptions.some(o => o.value === m)));
      if (result.agent_ids?.length) setAgentIds(result.agent_ids.filter((a: string) => agentOptions.some(o => o.value === a)));
      if (result.workflow_ids?.length) setWorkflowIds(result.workflow_ids.filter((w: string) => Array.isArray(workflowOptions) && workflowOptions.some(o => o.value === w)));
      if (result.memory_config) setMemoryConfigText(JSON.stringify(result.memory_config, null, 2));
      if (result.sop_text) setSopText(result.sop_text);
      if (result.trigger_conditions?.length) setTriggerText(result.trigger_conditions.join('\n'));
      setConfigEdited(true);
      toast.success(`智能填充完成`, result.reasoning || 'AI 已根据描述推荐配置');
    } catch (e: any) {
      toast.error('智能填充失败', e?.message || String(e));
    } finally {
      setAutoFillLoading(false);
    }
  };

  const applySmartGenerate = (opts?: { mode?: 'manual' | 'auto'; sources?: string[]; mayWrite?: boolean }) => {
    const nm = name.trim() || '新建Agent';
    const desc = description.trim();
    const agentType = selectedType;
    const modelName = selectedModel || 'DeepSeek Reasoner';
    const mode = opts?.mode || 'manual';
    const sources = new Set<string>(opts?.sources || []);
    const mayWrite = Boolean(opts?.mayWrite);

    const base = AGENT_TYPE_TEMPLATES[agentType]?.config || {};
    const looksLikeReview = (`${nm} ${desc}`.toLowerCase().includes('代码') || `${nm} ${desc}`.toLowerCase().includes('review') || `${nm} ${desc}`.toLowerCase().includes('审查') || `${nm} ${desc}`.toLowerCase().includes('分析'));
    const temp =
      agentType === 'react' ? 0.1 :
        agentType === 'plan' ? 0.1 :
          agentType === 'tool' ? 0.0 :
            (looksLikeReview ? 0.1 : 0.3);

    const sys = [
      `你是“${nm}”。`,
      desc ? `职责与边界：${desc}` : '',
      mode === 'auto' ? '你需要在回答前主动获取必要信息（通过已绑定工具/MCP），不要要求用户粘贴大段数据作为默认方案。' : '请先澄清目标与约束，再给出结构化输出。',
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
    sopLines.push('4. 汇总输出：结论 → 依据/引用 → 建议/下一步（含高/中/低优先级）。');
    sopLines.push('5. 自检：一致性、可执行性、风险与不确定性提示。');
    const sop = sopLines.join('\n');

    const cfg: any = { ...base, model: modelName, temperature: temp };
    if (!cfg.max_tokens) cfg.max_tokens = looksLikeReview ? 4096 : 2048;
    cfg.system_prompt = sys;

    // recommended skills by keywords (only set if empty to avoid overriding)
    const recSkills = new Set<string>(skills || []);
    const text = `${nm} ${desc}`.toLowerCase();
    if (recSkills.size === 0) {
      if (text.includes('代码') || text.includes('review') || text.includes('审查')) recSkills.add('code_review');
      if (text.includes('知识') || text.includes('检索') || text.includes('rag')) recSkills.add('knowledge_retrieval');
      if (text.includes('总结') || text.includes('摘要')) recSkills.add('summarization');
      if (text.includes('接口') || text.includes('api') || text.includes('工单') || text.includes('crm')) recSkills.add('api_calling');
    }

    // recommended tools by wizard (only add when mode=auto)
    const recTools = new Set<string>(tools || []);
    if (mode === 'auto') {
      if (sources.has('filesystem')) recTools.add('file_operations');
      if (sources.has('http')) recTools.add('http');
      if (sources.has('database')) recTools.add('database');
      if (sources.has('browser')) recTools.add('browser');
      if (sources.has('web')) recTools.add('webfetch'); // plus search optionally
      if (sources.has('web')) recTools.add('search');
    }

    setConfigText(JSON.stringify(cfg, null, 2));
    if (!sopText.trim()) setSopText(sop);
    if (skills.length === 0 && recSkills.size > 0) setSkills(Array.from(recSkills));
    if (tools.length === 0 && recTools.size > 0) setTools(Array.from(recTools));
    setConfigEdited(true);

    // post-generate lint (best-effort)
    const warns: string[] = [];
    if (mode === 'auto' && sources.has('filesystem') && !recTools.has('file_operations') && !tools.includes('file_operations')) {
      warns.push('你选择了“自动读取目录/仓库”，但未绑定 file_operations 工具，目录分析将无法自动读取文件。');
    }
    if (mode === 'auto' && sources.has('http') && !recTools.has('http') && !tools.includes('http')) {
      warns.push('你选择了“内部 HTTP API”，但未绑定 http 工具。');
    }
    if (mode === 'auto' && sources.has('database') && !recTools.has('database') && !tools.includes('database')) {
      warns.push('你选择了“数据库”，但未绑定 database 工具。');
    }
    if (mode === 'auto' && sources.has('browser') && !recTools.has('browser') && !tools.includes('browser')) {
      warns.push('你选择了“浏览器自动化”，但未绑定 browser 工具。');
    }
    if (mayWrite) {
      warns.push('你选择了“可能写入/修改外部系统”：请确保写操作工具在白名单内，并启用审批/审计策略。');
    }
    setGenWarnings(warns);
  };

  const handleTypeChange = (type: string) => {
    if (configEdited) {
      const ok = window.confirm('切换 Agent 类型将重置配置（包括 AI 填充内容）。确定继续？');
      if (!ok) return;
    }
    setSelectedType(type);
    const template = AGENT_TYPE_TEMPLATES[type];
    if (template) {
      const next: any = { ...(template.config || {}) };
      if (selectedModel) next.model = selectedModel;
      setConfigText(JSON.stringify(next, null, 2));
    }
    setConfigEdited(false);
  };

  const handleSubmit = async () => {
    try {
      if (!name.trim()) {
        toast.error('请输入 Agent 名称');
        return;
      }
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

      const metadata: Record<string, unknown> = { ...importMeta };
      if (description.trim()) metadata.description = description.trim();
      if (knowledgeBases.length > 0) metadata.knowledge_bases = knowledgeBases;

      const created = await workspaceAgentApi.create({ name: name.trim(), agent_type: selectedType, config, skills, tools, mcp_ids: mcpIds, workflow_ids: workflowIds, agent_ids: agentIds, memory_config, metadata,
        ...(triggerText.trim() ? { trigger_conditions: triggerText.split('\n').map(s => s.trim()).filter(Boolean) } : {}),
        ...(permissionsText.trim() ? { permissions: JSON.parse(permissionsText) as string[] } : {}),
      });
      const agentId = String((created as any).id || '');
      // SOP is optional; best-effort write after create.
      if (agentId && sopText.trim()) {
        try {
          await workspaceAgentApi.updateSop(agentId, sopText);
          try {
            await workspaceAgentApi.createVersion(agentId, 'Initial SOP');
          } catch {
            // ignore
          }
        } catch {
          // ignore SOP failures; agent is created successfully
        }
      }
      toast.success('创建成功');
      onSuccess();
      await maybeRunSmoke();
      onClose();
    } catch (e: any) {
      toast.error('创建失败', String(e?.message || ''));
    } finally {
      setLoading(false);
    }
  };

  const template = AGENT_TYPE_TEMPLATES[selectedType];
  const configHint = useMemo(() => `以下是 ${template?.name || ''} 的配置示例，可直接复制修改：`, [template?.name]);

  return (
    <>
    <Modal
      open={open}
      onClose={onClose}
      title="创建应用库 Agent"
      width={720}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={loading}>
            取消
          </Button>
          <Button variant="primary" onClick={handleSubmit} loading={loading}>
            创建
          </Button>
        </>
      }
    >
      {/* ── Source / Import ── */}
      <div className="flex items-center gap-4 mb-3">
        <span className="text-sm text-gray-400">来源:</span>
        <label className="flex items-center gap-1 text-sm cursor-pointer">
          <input type="radio" name="sourceMode" checked={sourceMode === 'manual'} onChange={() => setSourceMode('manual')} />
          <span className="text-gray-300">手动创建</span>
        </label>
        <label className="flex items-center gap-1 text-sm cursor-pointer">
          <input type="radio" name="sourceMode" checked={sourceMode === 'url'} onChange={() => setSourceMode('url')} />
          <span className="text-gray-300">从 GitHub 导入</span>
        </label>
        <label className="flex items-center gap-1 text-sm cursor-pointer">
          <input type="radio" name="sourceMode" checked={sourceMode === 'file'} onChange={() => setSourceMode('file')} />
          <span className="text-gray-300">从本地导入</span>
        </label>
      </div>

      {(sourceMode === 'url' || sourceMode === 'file') && (
        <div className="p-4 rounded-lg border border-blue-500/30 bg-blue-500/5 mb-3">
          <div className="flex gap-2 items-end">
            <div className="flex-1">
              {sourceMode === 'url' ? (
                <Input label="GitHub URL" value={importUrl} onChange={(e: any) => setImportUrl(e.target.value)}
                  placeholder="https://github.com/user/agent-repo" />
              ) : (
                <div>
                  <div className="text-xs font-medium text-gray-300 mb-1">本地 Zip 文件</div>
                  <div className="flex gap-2 items-center">
                    <Button variant="secondary" size="sm" onClick={() => fileInputRef.current?.click()} disabled={importDetecting}>
                      选择文件
                    </Button>
                    <input ref={fileInputRef} type="file" accept=".zip" style={{ display: 'none' }}
                      onChange={(e) => { const f = e.target.files?.[0]; if (f) { setImportFile(f); setImportUrl(''); } }} />
                    <span className="text-xs text-gray-400">{importFile ? importFile.name : '未选择文件'}</span>
                  </div>
                </div>
              )}
            </div>
            <Button variant="primary" size="sm" onClick={handleImportDetect} loading={importDetecting}
              disabled={(sourceMode === 'url' && !importUrl.trim()) || (sourceMode === 'file' && !importFile)}>
              AI 检测
            </Button>
          </div>

          {importResult && !importResult.error && (
            <div className="mt-3 p-3 rounded-lg border border-green-500/30 bg-green-500/5">
              <div className="text-sm font-medium text-green-300 mb-2">AI 推荐配置（基于 AGENT.md 分析）</div>
              <div className="grid grid-cols-2 gap-2 text-xs text-gray-300">
                <div><span className="text-gray-500">类型:</span> {importResult.agent_type || '-'}</div>
                <div><span className="text-gray-500">技能:</span> {(importResult.skills || []).join(', ') || '-'}</div>
                <div><span className="text-gray-500">工具:</span> {(importResult.tools || []).join(', ') || '-'}</div>
                <div><span className="text-gray-500">MCP:</span> {(importResult.mcp_ids || []).join(', ') || '-'}</div>
                <div><span className="text-gray-500">触发词:</span> {(importResult.trigger_conditions || []).join(', ') || <span className="text-gray-400 italic">未声明</span>}</div>
              </div>
              {importResult.reasoning && (
                <div className="text-xs text-gray-400 mt-2 italic">"{(importResult.reasoning as string).slice(0, 200)}"</div>
              )}
              <div className="text-xs text-gray-500 mt-2">以上配置已自动填入表单</div>
              {(importResult.tools_missing || []).length > 0 && (
                <div className="mt-2 p-2 rounded border border-amber-500/30 bg-amber-500/5 text-xs text-amber-300">
                  ⚠️ 系统缺少以下工具: <strong>{(importResult.tools_missing as string[]).join(', ')}</strong>
                  <div className="mt-1 text-amber-400">Agent 可能无法完整运行，建议先在工具管理页面安装对应工具。</div>
                </div>
              )}
              {(importResult.skills_missing || []).length > 0 && (
                <div className="mt-2 p-2 rounded border border-amber-500/30 bg-amber-500/5 text-xs text-amber-300">
                  ⚠️ 系统缺少以下 Skills: <strong>{(importResult.skills_missing as string[]).join(', ')}</strong>
                </div>
              )}
              {(importResult.mcp_missing || []).length > 0 && (
                <div className="mt-2 p-2 rounded border border-amber-500/30 bg-amber-500/5 text-xs text-amber-300">
                  ⚠️ 系统缺少以下 MCP Server: <strong>{(importResult.mcp_missing as string[]).join(', ')}</strong>
                </div>
              )}
              {(importResult.agents_missing || []).length > 0 && (
                <div className="mt-2 p-2 rounded border border-amber-500/30 bg-amber-500/5 text-xs text-amber-300">
                  ⚠️ 系统缺少以下子 Agent: <strong>{(importResult.agents_missing as string[]).join(', ')}</strong>
                </div>
              )}
            </div>
          )}
          {importResult?.error && (
            <div className="mt-2 text-xs text-red-400">{importResult.error}</div>
          )}
        </div>
      )}

      <div className="space-y-4">
        <Input label="名称" value={name} onChange={(e: any) => setName(e.target.value)} placeholder="例如：数据分析助手" />
        <div className="flex items-center gap-2">
          <div className="flex-1">
            <label className="text-sm font-medium text-gray-300 mb-1 block">功能描述</label>
            <Textarea value={description} onChange={(e: any) => setDescription(e.target.value)} placeholder="描述这个 Agent 的任务目标和能力边界，AI 将根据描述自动推荐技能、工具和配置" />
          </div>
        </div>
        <Textarea label="trigger_conditions（每行一条，可选）" rows={3} value={triggerText} onChange={(e: any) => setTriggerText(e.target.value)} placeholder="例如：\n帮我分析代码...\n代码审查\nreview" />
        {!triggerText.trim() && sourceMode !== 'manual' && (
          <div className="text-xs text-blue-400 bg-blue-500/5 border border-blue-500/20 rounded p-2 -mt-2 mb-1">
            💡 此 Agent 未声明触发词，需要手动填写才能被自动匹配。建议 3-6 个中文触发词。
          </div>
        )}
        <Textarea label="permissions（JSON 数组）" rows={3} value={permissionsText} onChange={(e: any) => setPermissionsText(e.target.value)} placeholder='["llm:generate", "network:outbound"]' />
          {sourceMode === 'manual' && (
          <div className="flex items-center gap-2">
            <Button variant="secondary" size="sm" onClick={handleAutoFill} loading={autoFillLoading}>
              ✨ AI 智能填充
            </Button>
            <Button variant="secondary" size="sm" onClick={() => setWizOpen(true)} disabled={loading}>
              向导
            </Button>
            <span className="text-xs text-gray-500">根据名称和功能描述自动推荐 Agent 类型、模型、Skills / Tools / MCP / 子 Agent / Workflow / 配置 / SOP / 记忆配置</span>
          </div>
          )}

        <label className="flex items-center gap-2 text-sm text-gray-400">
          <input type="checkbox" checked={autoSmoke} onChange={(e) => setAutoSmoke(e.target.checked)} />
          创建后自动运行全链路冒烟（会创建/清理资源）
        </label>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Select
            label="模型"
            value={selectedModel}
            onChange={(v) => {
              setSelectedModel(v);
              try {
                const cfg = configText?.trim() ? JSON.parse(configText) : {};
                cfg.model = v;
                setConfigText(JSON.stringify(cfg, null, 2));
              } catch {
                setConfigText(JSON.stringify({ model: v, temperature: 0.3 }, null, 2));
              }
              setConfigEdited(true);
            }}
            options={modelOptions}
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Select
            label="Agent 类型"
            value={selectedType}
            onChange={(v) => handleTypeChange(v)}
            options={[
              { value: 'base', label: '基础 - 简单对话' },
              { value: 'react', label: 'ReAct - 推理+行动' },
              { value: 'plan', label: '规划型 - 任务分解' },
              { value: 'tool', label: '工具型 - 工具调用' },
            ]}
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <MultiSelect label="绑定技能" options={skillOptions} selected={skills} onChange={setSkills} />
          <MultiSelect label="绑定工具" options={toolOptions} selected={tools} onChange={setTools} />
        </div>

        {mcpOptions.length > 0 && <MultiSelect label="绑定 MCP" options={mcpOptions} selected={mcpIds} onChange={setMcpIds} hint="MCP 服务器提供的工具会全局注册到工具池" />}
        {workflowOptions.length > 0 && <MultiSelect label="绑定 Workflow" options={workflowOptions} selected={workflowIds} onChange={setWorkflowIds} />}
        {agentOptions.length > 0 && <MultiSelect label="绑定子 Agent" options={agentOptions} selected={agentIds} onChange={setAgentIds} hint="当前 Agent 可以将任务委派给选中的子 Agent" />}
        {kbOptions.length > 0 && <MultiSelect label="知识库（Wiki 集合）" options={kbOptions} selected={knowledgeBases} onChange={setKnowledgeBases} hint="指定 Agent 使用的 Wiki 知识库集合；不选则默认用 default" />}

        {template && (
          <Alert type="info" title={template.name}>
            {template.description}
          </Alert>
        )}

        <Textarea label="配置（JSON）" value={configText} onChange={(e: any) => { setConfigText(e.target.value); setConfigEdited(true); }} rows={10} />
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
        <Textarea label="memory_config（JSON，可选）" value={memoryConfigText} onChange={(e: any) => setMemoryConfigText(e.target.value)} rows={6} />
        <Textarea
          label="SOP（Markdown，可选）"
          value={sopText}
          onChange={(e: any) => setSopText(e.target.value)}
          rows={10}
          placeholder={'例如：\n1. 澄清问题与范围。\n2. 调用 knowledge_retrieval 检索证据。\n3. 综合生成答案并引用证据。'}
        />
        {genWarnings.length > 0 && (
          <Alert type="warning" title="自动生成提示">
            <ul className="list-disc pl-5 space-y-1">
              {genWarnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </Alert>
        )}
        <div className="text-xs text-gray-500">{configHint}</div>
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
          toast.success('已应用优化');
        } catch { toast.error('应用失败'); }
      }}
    />
    <Modal
      open={wizOpen}
      onClose={() => setWizOpen(false)}
       title="Agent 向导"
      width={760}
      footer={
        <>
          <Button variant="secondary" onClick={() => setWizOpen(false)} disabled={loading}>
            取消
          </Button>
          <Button
            variant="primary"
            onClick={() => {
              applySmartGenerate({ mode: wizMode, sources: wizSources, mayWrite: wizMayWrite });
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

export default AddAgentModal;
