import React, { useEffect, useState } from 'react';
import { agentApi, skillApi, toolApi } from '../../services';
import { workspaceMcpApi, workflowTemplateApi, workspaceAgentApi } from '../../services';
import type { Agent } from '../../services';
import { Button, Modal, MultiSelect, Textarea, toast } from '../ui';

interface EditAgentModalProps {
  open: boolean;
  agent: Agent | null;
  onClose: () => void;
  onSuccess: () => void;
}

const EditAgentModal: React.FC<EditAgentModalProps> = ({ open, agent, onClose, onSuccess }) => {
  const [loading, setLoading] = useState(false);
  const [configText, setConfigText] = useState('');
  const [skills, setSkills] = useState<string[]>([]);
  const [tools, setTools] = useState<string[]>([]);
  const [mcpIds, setMcpIds] = useState<string[]>([]);
  const [workflowIds, setWorkflowIds] = useState<string[]>([]);
  const [agentIds, setAgentIds] = useState<string[]>([]);
  const [skillOptions, setSkillOptions] = useState<Array<{ value: string; label: string }>>([]);
  const [toolOptions, setToolOptions] = useState<Array<{ value: string; label: string }>>([]);
  const [mcpOptions, setMcpOptions] = useState<Array<{ value: string; label: string }>>([]);
  const [workflowOptions, setWorkflowOptions] = useState<Array<{ value: string; label: string }>>([]);
  const [agentOptions, setAgentOptions] = useState<Array<{ value: string; label: string }>>([]);

  useEffect(() => {
    if (open && agent) {
      setConfigText(agent.metadata?.config ? JSON.stringify(agent.metadata.config, null, 2) : (agent as any)?.config ? JSON.stringify((agent as any).config, null, 2) : '');
      setSkills(agent.skills || []);
      setTools(agent.tools || []);
      setMcpIds((agent as any)?.mcp_ids || []);
      setWorkflowIds((agent as any)?.workflow_ids || []);
      setAgentIds((agent as any)?.agent_ids || []);
      fetchOptions();
    }
  }, [open, agent]);

  const fetchOptions = async () => {
    try {
      const [skillRes, toolRes] = await Promise.all([
        skillApi.list({ limit: 500 }),
        toolApi.list({ limit: 200 } as any),
      ]);
      setSkillOptions((skillRes.skills || []).map((s: any) => ({ value: s.id, label: s.name })));
      setToolOptions((toolRes.tools || []).map((t: any) => ({ value: t.name, label: t.description || t.name })));
    } catch {}
    try {
      const mcpRes = await workspaceMcpApi.listServers();
      setMcpOptions(((mcpRes as any).servers || []).map((s: any) => ({ value: s.name || s.id, label: `${s.name || s.id} (MCP)` })));
    } catch {}
    try {
      const wfRes = await workflowTemplateApi.list();
      setWorkflowOptions(((wfRes as any).templates || []).map((w: any) => ({ value: w.name, label: `${w.label || w.name} (Workflow)` })));
    } catch {}
    try {
      const agentRes = await workspaceAgentApi.list({ limit: 200 });
      setAgentOptions(((agentRes as any).agents || []).filter((a: any) => a.name && a.id !== agent?.id)
        .map((a: any) => ({ value: a.id || a.name, label: `${a.name || a.id} (Agent)` })));
    } catch {}
  };

  const handleSubmit = async () => {
    if (!agent) return;
    setLoading(true);
    try {
      let config: Record<string, unknown> = {};
      if (configText?.trim()) {
        try { config = JSON.parse(configText); }
        catch { toast.error('配置 JSON 格式错误'); setLoading(false); return; }
      }
      await agentApi.update(agent.id, {
        config,
        skills: skills.length ? skills : undefined,
        tools: tools.length ? tools : undefined,
        mcp_ids: mcpIds.length ? mcpIds : undefined,
        workflow_ids: workflowIds.length ? workflowIds : undefined,
        agent_ids: agentIds.length ? agentIds : undefined,
      });
      toast.success(`Agent "${agent.name}" 更新成功`);
      onSuccess(); onClose();
    } catch (e: any) { toast.error('更新失败', String(e?.message || '')); }
    finally { setLoading(false); }
  };

  return (
    <Modal open={open} onClose={onClose} title={`编辑 Engine Agent: ${agent?.name || ''}`} width={800}
      footer={<>
        <Button variant="secondary" onClick={onClose} disabled={loading}>取消</Button>
        <Button variant="primary" onClick={handleSubmit} loading={loading}>保存</Button>
      </>}>
      <div className="space-y-4">
        <div className="text-sm text-gray-100 bg-dark-bg border border-dark-border rounded-lg px-3 h-10 flex items-center">
          类型: {agent?.agent_type || '-'} | ID: {agent?.id || '-'}
        </div>

        <div className="grid grid-cols-2 gap-3">
          {skillOptions.length > 0 && <MultiSelect label="Skills" options={skillOptions} selected={skills} onChange={setSkills} />}
          {toolOptions.length > 0 && <MultiSelect label="Tools" options={toolOptions} selected={tools} onChange={setTools} />}
        </div>

        <div className="grid grid-cols-2 gap-3">
          {mcpOptions.length > 0 && <MultiSelect label="MCP 服务器" options={mcpOptions} selected={mcpIds} onChange={setMcpIds} />}
          {workflowOptions.length > 0 && <MultiSelect label="Workflow" options={workflowOptions} selected={workflowIds} onChange={setWorkflowIds} />}
        </div>

        {agentOptions.length > 0 && <MultiSelect label="子 Agent" options={agentOptions} selected={agentIds} onChange={setAgentIds} />}

        <Textarea label="配置（JSON）" value={configText} onChange={(e: any) => setConfigText(e.target.value)} rows={8} />
        <div className="text-xs text-gray-500">修改后自动写回 AGENT.md frontmatter</div>
      </div>
    </Modal>
  );
};

export default EditAgentModal;
