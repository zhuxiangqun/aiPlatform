import React, { useMemo, useState } from 'react';
import { workspaceSkillApi, SKILL_CATEGORIES as SKILL_CAT_NAMES } from '../../services';
import { Button, Input, Modal, Select, Textarea, toast } from '../ui';
import { diagnosticsApi } from '../../services';
import SkillWizardV2Modal, { type SkillWizardV2Value } from './SkillWizardV2Modal';
import PromptDiffModal from './PromptDiffModal';

interface AddSkillModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

const SKILL_CATEGORIES = SKILL_CAT_NAMES.map(v => ({ value: v, label: v }));

const SKILL_TEMPLATES: Record<
  string,
  { config: Record<string, unknown>; input_schema: Record<string, unknown>; output_schema: Record<string, unknown>; sop: string }
> = {
  retrieval: {
    config: { timeout_seconds: 60, max_concurrent: 10, retry_count: 2 },
    input_schema: {
      query: { type: 'string', required: true, description: '检索问题/关键词' },
      top_k: { type: 'integer', required: false, description: '召回数量（默认 5）' },
      filters: { type: 'object', required: false, description: '过滤条件' },
    },
    output_schema: {
      passages: { type: 'array', required: true, description: '召回片段（含文本与元信息）' },
      markdown: { type: 'string', required: true, description: '面向人阅读的 Markdown 输出，与结构化字段一致' },
    },
    sop: '1. 解析 query 与 filters，确定数据域/权限。\n2. 执行召回（top_k）。\n3. 输出 passages（带元信息），供上游引用证据。',
  },
  analysis: {
    config: { timeout_seconds: 120, max_concurrent: 10, retry_count: 1 },
    input_schema: {
      input: { type: 'string', required: true, description: '待分析内容' },
      constraints: { type: 'object', required: false, description: '约束（口径/指标/维度）' },
    },
    output_schema: {
      summary: { type: 'string', required: true, description: '结论摘要' },
      details: { type: 'string', required: false, description: '分析细节' },
      markdown: { type: 'string', required: true, description: '面向人阅读的 Markdown 输出，与结构化字段一致' },
    },
    sop: '1. 明确分析目标与口径。\n2. 提取关键信息与假设。\n3. 给出结论与可验证依据，必要时输出步骤/推导。',
  },
  generation: {
    config: { timeout_seconds: 60, max_concurrent: 10, retry_count: 1 },
    input_schema: {
      prompt: { type: 'string', required: true, description: '生成指令/要点' },
      style: { type: 'string', required: false, description: '风格/语气' },
      format: { type: 'string', required: false, description: '输出格式要求' },
    },
    output_schema: {
      text: { type: 'string', required: true, description: '生成文本' },
      markdown: { type: 'string', required: true, description: '面向人阅读的 Markdown 输出，与结构化字段一致' },
    },
    sop: '1. 复述目标与输出格式。\n2. 按要求生成。\n3. 自检（完整性/一致性/敏感信息）。',
  },
  execution: {
    config: { timeout_seconds: 120, max_concurrent: 5, retry_count: 0 },
    input_schema: {
      action: { type: 'string', required: true, description: '要执行的动作（业务语义）' },
      params: { type: 'object', required: false, description: '动作参数' },
      dry_run: { type: 'boolean', required: false, description: '是否仅生成执行计划（默认 true）' },
    },
    output_schema: {
      plan: { type: 'object', required: false, description: '工具调用计划（推荐：tool_name + arguments）' },
      result: { type: 'string', required: false, description: '执行结果/说明' },
      markdown: { type: 'string', required: true, description: '面向人阅读的 Markdown 输出，与结构化字段一致' },
    },
    sop: '1. 校验输入与权限边界。\n2. 生成工具调用计划（plan）。\n3. 若允许执行，交由 Agent 调用 MCP 工具；否则输出计划与下一步。',
  },
  general: {
    config: { timeout_seconds: 60, max_concurrent: 10, retry_count: 1 },
    input_schema: { input: { type: 'string', required: true, description: '输入' } },
    output_schema: {
      output: { type: 'string', required: true, description: '输出' },
      markdown: { type: 'string', required: true, description: '面向人阅读的 Markdown 输出，与结构化字段一致' },
    },
    sop: '1. 明确目标。\n2. 执行。\n3. 输出结果与下一步。',
  },
};

const AddSkillModal: React.FC<AddSkillModalProps> = ({ open, onClose, onSuccess }) => {
  const [loading, setLoading] = useState(false);
  const [name, setName] = useState('');
  const [skillId, setSkillId] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [category, setCategory] = useState('general');
  const [description, setDescription] = useState('');
  const [skillKind, setSkillKind] = useState<'rule' | 'executable'>('rule');
  const [triggerText, setTriggerText] = useState('');
  const [permissionsText, setPermissionsText] = useState('["llm:generate"]');
  const [configText, setConfigText] = useState('');
  const [inputSchemaText, setInputSchemaText] = useState('{}');
  const [outputSchemaText, setOutputSchemaText] = useState('{}');
  const [sopText, setSopText] = useState('');
  const [autoSmoke, setAutoSmoke] = useState(true);
  const [optimizeOpen, setOptimizeOpen] = useState(false);
  const [optimizePrompt, setOptimizePrompt] = useState('');
  const [wizV2Open, setWizV2Open] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);

  const categoryOptions = useMemo(() => SKILL_CATEGORIES, []);

  const handleAiFill = async () => {
    if (!name.trim() || !description.trim()) return;
    setAiLoading(true);
    try {
      const res = await workspaceSkillApi.autoFill({ name: name.trim(), description: description.trim() });
      if (res.error) { toast.error('AI 生成失败', res.error); return; }
      setDisplayName(res.display_name || name);
      setDescription(res.description || description);
      setCategory(res.category || 'general');
      setSkillKind((res.skill_kind === 'executable' ? 'executable' : 'rule') as any);
      setTriggerText(JSON.stringify(res.trigger_conditions || [], null, 2));
      setPermissionsText(JSON.stringify(res.permissions || [], null, 2));
      setInputSchemaText(JSON.stringify(res.input_schema || {}, null, 2));
      setOutputSchemaText(JSON.stringify(res.output_schema || {}, null, 2));
      setSopText(res.sop || '');
      toast.success('AI 已生成 Skill 模板');
    } catch (e: any) {
      toast.error('AI 生成失败', e?.detail || e?.message || String(e));
    } finally { setAiLoading(false); }
  };

  const applyTemplate = (cat: string) => {
    const key = SKILL_TEMPLATES[cat] ? cat : 'general';
    const tmpl = SKILL_TEMPLATES[key];
    setConfigText(JSON.stringify(tmpl.config, null, 2));
    setInputSchemaText(JSON.stringify(tmpl.input_schema, null, 2));
    setOutputSchemaText(JSON.stringify(tmpl.output_schema, null, 2));
    setSopText(tmpl.sop);
    setSkillKind(cat === 'execution' ? 'executable' : 'rule');
  };

  const handleSubmit = async () => {
    if (!name.trim()) {
      toast.error('请输入 Skill 名称');
      return;
    }
    setLoading(true);
    try {
      let config: Record<string, unknown> = {};
      let input_schema: Record<string, unknown> = {};
      let output_schema: Record<string, unknown> = {};

      if (configText.trim()) {
        try {
          config = JSON.parse(configText);
        } catch {
          toast.error('config JSON 格式错误');
          setLoading(false);
          return;
        }
      }

      if (inputSchemaText.trim()) {
        try {
          input_schema = JSON.parse(inputSchemaText);
        } catch {
          toast.error('input_schema JSON 格式错误');
          setLoading(false);
          return;
        }
      }

      if (outputSchemaText.trim()) {
        try {
          output_schema = JSON.parse(outputSchemaText);
        } catch {
          toast.error('output_schema JSON 格式错误');
          setLoading(false);
          return;
        }
      }

      let permissions: string[] | undefined;
      if (permissionsText.trim()) {
        try {
          const v = JSON.parse(permissionsText);
          permissions = Array.isArray(v) ? v.map((x) => String(x)).filter((x) => x.trim()) : undefined;
        } catch {
          permissions = permissionsText
            .split(/[\n,]/g)
            .map((x) => x.trim())
            .filter(Boolean);
        }
      }
      const trigger_conditions = triggerText
        .split('\n')
        .map((x) => x.trim())
        .filter(Boolean);

      const res = await workspaceSkillApi.create({
        name: name.trim(),
        ...(skillId.trim() ? { skill_id: skillId.trim() } : {}),
        ...(displayName.trim() ? { display_name: displayName.trim() } : { display_name: name.trim() }),
        category,
        description: description || '',
        skill_kind: skillKind,
        ...(permissions ? { permissions } : {}),
        ...(trigger_conditions.length > 0 ? { trigger_conditions } : {}),
        config,
        input_schema,
        output_schema,
        template: category,
        sop: sopText || '',
      } as any);

      toast.success('已创建');
      const sum = (res as any)?.lint?.summary;
      if (sum && (Number(sum.error_count || 0) > 0 || Number(sum.warning_count || 0) > 0)) {
        toast.warning('Skill Lint', `E${sum.error_count || 0}/W${sum.warning_count || 0}（risk=${sum.risk_level || 'low'}）`);
      }
      onSuccess();
      if (autoSmoke) {
        try {
          const smoke = await diagnosticsApi.runE2ESmoke({ tenant_id: 'ops_smoke', actor_id: 'admin', agent_model: 'deepseek-reasoner' });
          toast.success(smoke?.ok ? '全链路冒烟通过' : '全链路冒烟失败');
        } catch (e: any) {
          toast.error('全链路冒烟失败', String(e?.message || 'unknown'));
        }
      }
      onClose();
      setName('');
      setSkillId('');
      setDisplayName('');
      setCategory('general');
      setDescription('');
      setSkillKind('rule');
      setTriggerText('');
      setPermissionsText('["llm:generate"]');
      setConfigText('');
      setInputSchemaText('{}');
      setOutputSchemaText('{}');
      setSopText('');
    } catch (e: any) {
      toast.error('创建失败', String(e?.message || ''));
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
    <Modal
      open={open}
      onClose={onClose}
      title="创建应用库 Skill"
      width={820}
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
      <label className="mb-3 flex items-center gap-2 text-sm text-gray-400">
        <input type="checkbox" checked={autoSmoke} onChange={(e) => setAutoSmoke(e.target.checked)} />
        创建后自动运行全链路冒烟（会创建/清理资源）
      </label>
      <div className="space-y-4">
        <div className="flex gap-2 items-end">
          <div className="flex-1"><Input label="名称" value={name} onChange={(e: any) => setName(e.target.value)} placeholder="例如：我的客服助手" /></div>
          <Button variant="secondary" size="sm" onClick={handleAiFill} loading={aiLoading}
            disabled={!name.trim() || !description.trim() || aiLoading}>AI 生成</Button>
        </div>
        <Input label="Skill ID（可选，留空则自动生成）" value={skillId} onChange={(e: any) => setSkillId(e.target.value)} placeholder="例如：customer_support（建议小写/下划线）" />
        <div className="flex items-end justify-between gap-3">
          <div className="flex-1">
            <Select
              label="分类"
              value={category}
              onChange={(v) => {
                setCategory(v);
                applyTemplate(v);
              }}
              options={categoryOptions}
            />
          </div>
          <Button variant="secondary" onClick={() => applyTemplate(category)} disabled={loading}>
            应用模板
          </Button>
          <Button variant="primary" onClick={() => setWizV2Open(true)} disabled={loading}>
            向导 v2（推荐）
          </Button>
        </div>
        <Select
          label="形态"
          value={skillKind}
          onChange={(v) => setSkillKind(v as any)}
          options={[
            { value: 'rule', label: 'rule（纯 SOP）' },
            { value: 'executable', label: 'executable（可执行/需权限）' },
          ]}
        />
        <Input label="描述" value={description} onChange={(e: any) => setDescription(e.target.value)} placeholder="描述用途" />
        <Textarea label="trigger_conditions（每行一条，可选）" rows={3} value={triggerText} onChange={(e: any) => setTriggerText(e.target.value)} placeholder="例如：\n帮我查一下...\n检索..." />
        <Textarea
          label="permissions（JSON 数组或逗号/换行分隔）"
          rows={3}
          value={permissionsText}
          onChange={(e: any) => setPermissionsText(e.target.value)}
          placeholder='["llm:generate"]'
        />

        <Textarea label="config（JSON，可选）" rows={6} value={configText} onChange={(e: any) => setConfigText(e.target.value)} placeholder='{"timeout_seconds": 60}' />
        <Textarea label="input_schema（JSON）" rows={6} value={inputSchemaText} onChange={(e: any) => setInputSchemaText(e.target.value)} />
        <Textarea label="output_schema（JSON）" rows={6} value={outputSchemaText} onChange={(e: any) => setOutputSchemaText(e.target.value)} />
        <Textarea label="SOP（Markdown，可选）" rows={8} value={sopText} onChange={(e: any) => setSopText(e.target.value)} />
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" onClick={() => {
            if (!sopText.trim()) { toast.warning('SOP 为空，无法优化'); return; }
            setOptimizePrompt(sopText);
            setOptimizeOpen(true);
          }}>🤖 AI 优化 SOP</Button>
        </div>
      </div>
    </Modal>

    <SkillWizardV2Modal
      open={wizV2Open}
      onClose={() => setWizV2Open(false)}
      initial={{
        name,
        skill_id: skillId,
        display_name: displayName,
        description,
        category,
        skill_kind: skillKind,
        trigger_conditions: triggerText ? triggerText.split('\n').map((x) => x.trim()).filter(Boolean) : [],
        permissions: (() => {
          try {
            const v = JSON.parse(permissionsText || '[]');
            return Array.isArray(v) ? v : ['llm:generate'];
          } catch {
            return ['llm:generate'];
          }
        })(),
        config: (() => {
          try {
            return JSON.parse(configText || '{}');
          } catch {
            return {};
          }
        })(),
        input_schema: (() => {
          try {
            return JSON.parse(inputSchemaText || '{}');
          } catch {
            return {};
          }
        })(),
        output_schema: (() => {
          try {
            return JSON.parse(outputSchemaText || '{}');
          } catch {
            return {};
          }
        })(),
        sop: sopText,
      }}
      onApply={(v: SkillWizardV2Value) => {
        setName(v.name);
        setSkillId(v.skill_id || '');
        setDisplayName(v.display_name || '');
        setDescription(v.description);
        setCategory(v.category);
        setSkillKind(v.skill_kind);
        setTriggerText((v.trigger_conditions || []).join('\n'));
        setPermissionsText(JSON.stringify(v.permissions || ['llm:generate']));
        setConfigText(JSON.stringify(v.config || {}, null, 2));
        setInputSchemaText(JSON.stringify(v.input_schema || {}, null, 2));
        setOutputSchemaText(JSON.stringify(v.output_schema || {}, null, 2));
        setSopText(v.sop || '');
        setWizV2Open(false);
      }}
    />

    <PromptDiffModal
      open={optimizeOpen}
      title="AI 优化 Skill SOP"
      original={optimizePrompt}
      onClose={() => setOptimizeOpen(false)}
      onApply={(optimized) => {
        setSopText(optimized);
        toast.success('已应用优化');
      }}
    />
    </>
  );
};

export default AddSkillModal;
