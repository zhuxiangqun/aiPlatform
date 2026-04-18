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

  useEffect(() => {
    if (open && agent) {
      setName(agent.name || '');
      setDescription(String((agent as any)?.metadata?.description || ''));
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
            <Button variant="secondary" onClick={applySmartGenerate} disabled={loading}>
              智能生成（根据名称/描述）
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
        <Alert type="info" title="说明">
          {configHint} {configHint2}
        </Alert>
      </div>
    </Modal>
  );
};

export default EditAgentModal;
