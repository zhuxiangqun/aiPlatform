import React, { useMemo, useState } from 'react';
import { workspaceSkillApi } from '../../services/coreApi';
import { Button, Input, Modal, Select, Textarea, toast } from '../ui';

interface AddSkillModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

const SKILL_CATEGORIES = [
  { value: 'general', label: '通用' },
  { value: 'execution', label: '执行' },
  { value: 'retrieval', label: '检索' },
  { value: 'analysis', label: '分析' },
  { value: 'generation', label: '生成' },
  { value: 'transformation', label: '转换' },
];

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
    },
    sop: '1. 校验输入与权限边界。\n2. 生成工具调用计划（plan）。\n3. 若允许执行，交由 Agent 调用 MCP 工具；否则输出计划与下一步。',
  },
  general: {
    config: { timeout_seconds: 60, max_concurrent: 10, retry_count: 1 },
    input_schema: { input: { type: 'string', required: true, description: '输入' } },
    output_schema: { output: { type: 'string', required: true, description: '输出' } },
    sop: '1. 明确目标。\n2. 执行。\n3. 输出结果与下一步。',
  },
};

const AddSkillModal: React.FC<AddSkillModalProps> = ({ open, onClose, onSuccess }) => {
  const [loading, setLoading] = useState(false);
  const [name, setName] = useState('');
  const [category, setCategory] = useState('general');
  const [description, setDescription] = useState('');
  const [configText, setConfigText] = useState('');
  const [inputSchemaText, setInputSchemaText] = useState('{}');
  const [outputSchemaText, setOutputSchemaText] = useState('{}');
  const [sopText, setSopText] = useState('');

  const categoryOptions = useMemo(() => SKILL_CATEGORIES, []);

  const applyTemplate = (cat: string) => {
    const key = SKILL_TEMPLATES[cat] ? cat : 'general';
    const tmpl = SKILL_TEMPLATES[key];
    setConfigText(JSON.stringify(tmpl.config, null, 2));
    setInputSchemaText(JSON.stringify(tmpl.input_schema, null, 2));
    setOutputSchemaText(JSON.stringify(tmpl.output_schema, null, 2));
    setSopText(tmpl.sop);
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

      await workspaceSkillApi.create({
        name: name.trim(),
        category,
        description: description || '',
        config,
        input_schema,
        output_schema,
        template: category,
        sop: sopText || '',
      } as any);

      toast.success('已创建');
      onSuccess();
      onClose();
      setName('');
      setCategory('general');
      setDescription('');
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
      <div className="space-y-4">
        <Input label="名称" value={name} onChange={(e: any) => setName(e.target.value)} placeholder="例如：我的客服助手" />
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
        </div>
        <Input label="描述" value={description} onChange={(e: any) => setDescription(e.target.value)} placeholder="描述用途" />

        <Textarea label="config（JSON，可选）" rows={6} value={configText} onChange={(e: any) => setConfigText(e.target.value)} placeholder='{"timeout_seconds": 60}' />
        <Textarea label="input_schema（JSON）" rows={6} value={inputSchemaText} onChange={(e: any) => setInputSchemaText(e.target.value)} />
        <Textarea label="output_schema（JSON）" rows={6} value={outputSchemaText} onChange={(e: any) => setOutputSchemaText(e.target.value)} />
        <Textarea label="SOP（Markdown，可选）" rows={8} value={sopText} onChange={(e: any) => setSopText(e.target.value)} />
      </div>
    </Modal>
  );
};

export default AddSkillModal;
