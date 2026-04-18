import React, { useEffect, useMemo, useState } from 'react';
import { workspaceAgentApi, workspaceSkillApi } from '../../services/coreApi';
import { modelApi, toolApi, type Model } from '../../services';
import type { Agent } from '../../services';
import { Alert, Button, Input, Modal, Textarea, toast } from '../ui';

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
  const [configText, setConfigText] = useState('');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [memoryConfigText, setMemoryConfigText] = useState('');
  const [sopText, setSopText] = useState('');
  const [sopLoading, setSopLoading] = useState(false);
  const [skillOptions, setSkillOptions] = useState<Array<{ value: string; label: string }>>([]);
  const [toolOptions, setToolOptions] = useState<Array<{ value: string; label: string }>>([]);
  const [modelOptions, setModelOptions] = useState<Array<{ value: string; label: string }>>([]);
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [defaultToolset, setDefaultToolset] = useState<string>('workspace_default');

  // Disambiguation wizard
  const [wizOpen, setWizOpen] = useState(false);
  const [wizMode, setWizMode] = useState<'manual' | 'auto'>('manual');
  const [wizSources, setWizSources] = useState<string[]>([]);
  const [wizMayWrite, setWizMayWrite] = useState(false);
  const [genWarnings, setGenWarnings] = useState<string[]>([]);

  useEffect(() => {
    if (open && agent) {
      setName(agent.name || '');
      setDescription(String((agent as any)?.metadata?.description || ''));
      setDefaultToolset(String((agent as any)?.metadata?.toolset || 'workspace_default'));
      setSkills(agent.skills || []);
      setTools(agent.tools || []);
      setConfigText(agent.metadata?.config ? JSON.stringify(agent.metadata.config, null, 2) : (agent as any)?.config ? JSON.stringify((agent as any).config, null, 2) : '');
      setMemoryConfigText((agent as any)?.memory_config ? JSON.stringify((agent as any).memory_config, null, 2) : '');
      setSopText('');
      fetchOptions();
      fetchSop();
      // init selectedModel from config if possible
      try {
        const cfg = (agent as any)?.config || {};
        if (cfg?.model) setSelectedModel(String(cfg.model));
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

  const openDisambiguationWizard = () => {
    const a = detectAmbiguity();
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
  };

  const fetchSop = async () => {
    if (!agent) return;
    setSopLoading(true);
    try {
      const res = await workspaceAgentApi.getSop(agent.id);
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
        agent ? workspaceAgentApi.getSkills(agent.id) : Promise.resolve({ skill_ids: [] as string[] } as any),
        agent ? workspaceAgentApi.getTools(agent.id) : Promise.resolve({ tool_ids: [] as string[] } as any),
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

      // models from infra layer
      try {
        const modelRes = await modelApi.list({ enabled: true, status: 'available' });
        const models = ((modelRes as any).models || []) as Model[];
        const modelOpts = models.map((m) => ({ value: m.name, label: m.displayName || m.name }));
        setModelOptions(modelOpts);
        if (!selectedModel) {
          const prefer = models.find((m) => (m.displayName || '').toLowerCase().includes('deepseek') && (m.displayName || '').toLowerCase().includes('reasoner'))
            || models.find((m) => (m.name || '').toLowerCase().includes('deepseek') && (m.name || '').toLowerCase().includes('reasoner'));
          const fallback = prefer?.name || models[0]?.name || '';
          if (fallback) setSelectedModel(fallback);
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

  const applySmartGenerate = () => {
    const nm = name.trim() || agent?.name || 'Agent';
    const desc = description.trim();
    const modelName = selectedModel || 'DeepSeek Reasoner';

    const sys = [
      `你是“${nm}”。`,
      desc ? `职责与边界：${desc}` : '',
      '请先澄清目标与约束，再给出结构化输出。',
      '输出要求：给出结论、依据（如有）、以及下一步建议。',
      '如果缺少上下文，请提出需要的材料（文件/接口/数据范围）。',
    ].filter(Boolean).join('\n');

    const sop = [
      '1. 澄清问题与范围（目标/输入/约束/权限）。',
      '2. 结合已绑定技能/工具执行必要的检索或动作。',
      '3. 组织答案：结论 → 依据/引用 → 建议/下一步。',
      '4. 自检：一致性、可执行性、风险与不确定性提示。',
    ].join('\n');

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
    if (!sopText.trim()) setSopText(sop);
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
      mode === 'auto' ? '你需要在回答前主动获取必要信息（通过已绑定工具/MCP），不要默认要求用户粘贴大段数据。' : '请先澄清目标与约束，再给出结构化输出。',
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

      await workspaceAgentApi.update(agent.id, { name: name.trim() || undefined, config, memory_config, metadata });

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
        <Input label="描述（可选）" value={description} onChange={(e: any) => setDescription(e.target.value)} />

        <div>
          <div className="text-sm font-medium text-gray-300 mb-2">默认 Toolset（运行时工具集）</div>
          <select
            value={defaultToolset}
            onChange={(e) => setDefaultToolset(e.target.value)}
            className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100"
          >
            <option value="workspace_default">workspace_default（默认）</option>
            <option value="safe_readonly">safe_readonly（只读）</option>
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
            <Button variant="primary" onClick={openDisambiguationWizard} disabled={loading}>
              生成向导（推荐）
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                const a = detectAmbiguity();
                const hinted = a.wantsFs || a.wantsBrowser || a.wantsHttp || a.wantsDb || a.wantsWeb || a.wantsWrite;
                if (hinted) {
                  openDisambiguationWizard();
                } else {
                  applySmartGenerate();
                }
              }}
              disabled={loading}
            >
              快速生成
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
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
        </div>

        <Textarea label="配置（JSON）" value={configText} onChange={(e: any) => setConfigText(e.target.value)} rows={10} />
        <Textarea label="memory_config（JSON，可选）" value={memoryConfigText} onChange={(e: any) => setMemoryConfigText(e.target.value)} rows={6} />
        <Textarea
          label="SOP（Markdown，可选）"
          value={sopText}
          onChange={(e: any) => setSopText(e.target.value)}
          rows={10}
          placeholder={'例如：\n1. 澄清问题与范围。\n2. 调用 knowledge_retrieval 检索证据。\n3. 综合生成答案并引用证据。'}
        />
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

export default EditAgentModal;
