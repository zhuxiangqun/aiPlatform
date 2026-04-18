import React, { useEffect, useMemo, useState } from 'react';
import { workspaceAgentApi, workspaceSkillApi } from '../../services/coreApi';
import { modelApi, toolApi, type Model } from '../../services';
import { Alert, Button, Input, Modal, Textarea, toast } from '../ui';

interface AgentConfigTemplate {
  name: string;
  description: string;
  config: Record<string, unknown>;
}

const AGENT_TYPE_TEMPLATES: Record<string, AgentConfigTemplate> = {
  base: {
    name: '基础Agent',
    description: '最基础的对话Agent，适用于简单问答场景',
    config: { model: 'gpt-4', temperature: 0.7, max_tokens: 2048, system_prompt: '你是一个有帮助的AI助手。' },
  },
  react: {
    name: 'ReAct Agent',
    description: '使用ReAct（Reasoning + Acting）模式，具备推理和工具调用能力',
    config: { model: 'gpt-4', temperature: 0.0, max_tokens: 4096, reasoning_steps: 3, system_prompt: '你是一个使用ReAct模式的推理Agent。' },
  },
  plan: {
    name: '规划型Agent',
    description: '具备任务分解和规划能力，适合复杂多步骤任务',
    config: { model: 'gpt-4', temperature: 0.1, max_tokens: 8192, planning_enabled: true, max_subtasks: 10, system_prompt: '你是一个任务规划Agent。' },
  },
  tool: {
    name: '工具型Agent',
    description: '专注于工具调用和自动化执行的Agent',
    config: { model: 'gpt-4', temperature: 0.0, max_tokens: 2048, system_prompt: '你是一个工具型Agent。' },
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
  const [configText, setConfigText] = useState('');
  const [memoryConfigText, setMemoryConfigText] = useState('{\n  "type": "short_term",\n  "recall_count": 5\n}');
  const [sopText, setSopText] = useState('');
  const [skillOptions, setSkillOptions] = useState<Array<{ value: string; label: string }>>([]);
  const [toolOptions, setToolOptions] = useState<Array<{ value: string; label: string }>>([]);
  const [modelOptions, setModelOptions] = useState<Array<{ value: string; label: string }>>([]);
  const [selectedModel, setSelectedModel] = useState<string>('');

  // Disambiguation wizard
  const [wizOpen, setWizOpen] = useState(false);
  const [wizMode, setWizMode] = useState<'manual' | 'auto'>('manual');
  const [wizSources, setWizSources] = useState<string[]>([]);
  const [wizMayWrite, setWizMayWrite] = useState(false);
  const [genWarnings, setGenWarnings] = useState<string[]>([]);

  useEffect(() => {
    if (open) {
      setSelectedType('base');
      setName('');
      setDescription('');
      setSkills([]);
      setTools([]);
      setConfigText(JSON.stringify(AGENT_TYPE_TEMPLATES.base.config, null, 2));
      setMemoryConfigText('{\n  "type": "short_term",\n  "recall_count": 5\n}');
      setSopText('');
      fetchOptions();
    }
  }, [open]);

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
    setSelectedType(type);
    const template = AGENT_TYPE_TEMPLATES[type];
    if (template) {
      const next: any = { ...(template.config || {}) };
      if (selectedModel) next.model = selectedModel;
      setConfigText(JSON.stringify(next, null, 2));
    }
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

      const metadata: Record<string, unknown> = {};
      if (description.trim()) metadata.description = description.trim();

      const created = await workspaceAgentApi.create({ name: name.trim(), agent_type: selectedType, config, skills, tools, memory_config, metadata });
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
      <div className="space-y-4">
        <Input label="名称" value={name} onChange={(e: any) => setName(e.target.value)} placeholder="例如：数据分析助手" />
        <Input label="描述（可选）" value={description} onChange={(e: any) => setDescription(e.target.value)} placeholder="这个 Agent 的职责边界与适用场景" />

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
                  setConfigText(JSON.stringify({ model: v, temperature: 0.3 }, null, 2));
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
              variant="secondary"
              onClick={() => {
                const a = detectAmbiguity();
                // open wizard when content indicates possible auto mode needs
                const hinted = a.wantsFs || a.wantsBrowser || a.wantsHttp || a.wantsDb || a.wantsWeb || a.wantsWrite;
                if (hinted) {
                  setWizOpen(true);
                  setWizMode(a.wantsFs || a.wantsBrowser || a.wantsHttp || a.wantsDb || a.wantsWeb ? 'auto' : 'manual');
                  const src: string[] = [];
                  if (a.wantsFs) src.push('filesystem');
                  if (a.wantsHttp) src.push('http');
                  if (a.wantsDb) src.push('database');
                  if (a.wantsBrowser) src.push('browser');
                  if (a.wantsWeb) src.push('web');
                  setWizSources(src);
                  setWizMayWrite(a.wantsWrite);
                } else {
                  applySmartGenerate();
                }
              }}
              disabled={loading}
            >
              智能生成（根据名称/描述）
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <div className="text-sm font-medium text-gray-300 mb-2">类型</div>
            <select
              value={selectedType}
              onChange={(e) => handleTypeChange(e.target.value)}
              className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100"
            >
              <option value="base">基础 - 简单对话</option>
              <option value="react">ReAct - 推理+行动</option>
              <option value="plan">规划型 - 任务分解</option>
              <option value="tool">工具型 - 工具调用</option>
            </select>
          </div>

          <div>
            <div className="text-sm font-medium text-gray-300 mb-2">绑定技能（多选）</div>
            <select
              multiple
              value={skills}
              onChange={(e) => setSkills(Array.from(e.target.selectedOptions).map((o) => (o as any).value))}
              className="w-full h-28 px-3 py-2 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100"
            >
              {skillOptions.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
            <div className="text-xs text-gray-500 mt-1">按住 Ctrl/Cmd 可多选</div>
          </div>
        </div>

        <div>
          <div className="text-sm font-medium text-gray-300 mb-2">绑定工具（多选）</div>
          <select
            multiple
            value={tools}
            onChange={(e) => setTools(Array.from(e.target.selectedOptions).map((o) => (o as any).value))}
            className="w-full h-28 px-3 py-2 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100"
          >
            {toolOptions.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>

        {template && (
          <Alert type="info" title={template.name}>
            {template.description}
          </Alert>
        )}

        <Textarea label="配置（JSON）" value={configText} onChange={(e: any) => setConfigText(e.target.value)} rows={10} />
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
