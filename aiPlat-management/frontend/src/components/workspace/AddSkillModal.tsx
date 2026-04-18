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
  const [wizOpen, setWizOpen] = useState(false);
  const [wizKind, setWizKind] = useState<'prompt' | 'retrieval' | 'execution' | 'transformation'>('prompt');
  const [wizStructured, setWizStructured] = useState(false);
  const [wizMayWrite, setWizMayWrite] = useState(false);
  const [genWarnings, setGenWarnings] = useState<string[]>([]);

  const categoryOptions = useMemo(() => SKILL_CATEGORIES, []);

  const applyTemplate = (cat: string) => {
    const key = SKILL_TEMPLATES[cat] ? cat : 'general';
    const tmpl = SKILL_TEMPLATES[key];
    setConfigText(JSON.stringify(tmpl.config, null, 2));
    setInputSchemaText(JSON.stringify(tmpl.input_schema, null, 2));
    setOutputSchemaText(JSON.stringify(tmpl.output_schema, null, 2));
    setSopText(tmpl.sop);
  };

  const openWizard = () => {
    setWizOpen(true);
    // best-effort guess
    const text = `${name} ${description}`.toLowerCase();
    if (text.includes('检索') || text.includes('召回') || text.includes('rag') || text.includes('知识库')) setWizKind('retrieval');
    else if (text.includes('执行') || text.includes('调用') || text.includes('自动化') || text.includes('创建') || text.includes('更新')) setWizKind('execution');
    else if (text.includes('转换') || text.includes('格式') || text.includes('抽取')) setWizKind('transformation');
    else setWizKind('prompt');
    setWizStructured(text.includes('json') || text.includes('结构化') || text.includes('schema'));
    setWizMayWrite(text.includes('写入') || text.includes('更新') || text.includes('创建') || text.includes('删除') || text.includes('修改'));
  };

  const applyWizardGenerate = () => {
    const nm = name.trim() || '新建Skill';
    const desc = description.trim();
    const structured = wizStructured;
    const mayWrite = wizMayWrite;
    let cat = category;

    // map wizard kind to category + template
    if (wizKind === 'retrieval') cat = 'retrieval';
    else if (wizKind === 'execution') cat = 'execution';
    else if (wizKind === 'transformation') cat = 'transformation';
    else cat = 'analysis';

    setCategory(cat);
    const key = SKILL_TEMPLATES[cat] ? cat : 'general';
    const base = SKILL_TEMPLATES[key];

    // config
    const cfg: any = { ...(base.config || {}) };
    cfg.timeout_seconds = cfg.timeout_seconds ?? (wizKind === 'execution' ? 120 : 60);
    if (mayWrite) cfg.require_confirmation = true;

    // schemas
    const input: any = { ...(base.input_schema || {}) };
    const output: any = { ...(base.output_schema || {}) };
    // ensure a minimal common input
    if (!input.input && wizKind === 'prompt') input.prompt = input.prompt || { type: 'string', required: true, description: '指令/要点' };
    if (!input.context) input.context = { type: 'object', required: false, description: '上下文/约束（可选）' };
    if (structured) {
      output.result = output.result || { type: 'object', required: true, description: '结构化结果' };
    }

    // SOP
    const sop = [
      `1. 明确目标与边界：${nm}${desc ? `（${desc}）` : ''}。`,
      wizKind === 'retrieval' ? '2. 明确检索数据域/filters，执行召回并返回证据片段。'
        : wizKind === 'execution' ? '2. 校验参数与权限边界，生成执行计划（plan），必要时要求二次确认。'
          : wizKind === 'transformation' ? '2. 明确输入格式与目标格式，执行抽取/转换并校验结果。'
            : '2. 提取关键信息与约束，按要求分析并给出可验证依据。',
      structured ? '3. 输出必须包含结构化 result 字段，并保持字段稳定。' : '3. 输出清晰结论与下一步建议。',
      '4. 自检：完整性、一致性、边界条件与失败提示。',
    ].join('\n');

    setConfigText(JSON.stringify(cfg, null, 2));
    setInputSchemaText(JSON.stringify(input, null, 2));
    setOutputSchemaText(JSON.stringify(output, null, 2));
    if (!sopText.trim()) setSopText(sop);

    // lint warnings
    const warns: string[] = [];
    if (!name.trim()) warns.push('建议先填写 Skill 名称，再生成模板。');
    if (wizKind === 'execution' && !mayWrite) warns.push('你选择了“执行类 Skill”，如果涉及写入外部系统建议勾选“可能写入/修改”。');
    if (wizKind === 'retrieval' && !desc) warns.push('检索类 Skill 建议在描述中写清楚数据域/权限边界。');
    setGenWarnings(warns);
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
          <Button variant="primary" onClick={openWizard} disabled={loading}>
            生成向导（推荐）
          </Button>
        </div>
        <Input label="描述" value={description} onChange={(e: any) => setDescription(e.target.value)} placeholder="描述用途" />

        <Textarea label="config（JSON，可选）" rows={6} value={configText} onChange={(e: any) => setConfigText(e.target.value)} placeholder='{"timeout_seconds": 60}' />
        <Textarea label="input_schema（JSON）" rows={6} value={inputSchemaText} onChange={(e: any) => setInputSchemaText(e.target.value)} />
        <Textarea label="output_schema（JSON）" rows={6} value={outputSchemaText} onChange={(e: any) => setOutputSchemaText(e.target.value)} />
        <Textarea label="SOP（Markdown，可选）" rows={8} value={sopText} onChange={(e: any) => setSopText(e.target.value)} />
        {genWarnings.length > 0 && (
          <div className="text-sm text-yellow-300">
            <div className="font-medium mb-1">生成提示</div>
            <ul className="list-disc pl-5 space-y-1">
              {genWarnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Modal>

    <Modal
      open={wizOpen}
      onClose={() => setWizOpen(false)}
      title="Skill 生成向导"
      width={760}
      footer={
        <>
          <Button variant="secondary" onClick={() => setWizOpen(false)} disabled={loading}>
            取消
          </Button>
          <Button
            variant="primary"
            onClick={() => {
              applyWizardGenerate();
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
        <div className="text-sm text-gray-300">
          通过向导明确 Skill 类型与输出形态，避免“检索/执行/分析”歧义。
        </div>

        <div>
          <div className="text-sm font-medium text-gray-300 mb-2">Skill 类型</div>
          <select
            value={wizKind}
            onChange={(e) => setWizKind(e.target.value as any)}
            className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100"
          >
            <option value="prompt">分析/提示式（不依赖外部系统）</option>
            <option value="retrieval">检索/召回式（知识库/RAG）</option>
            <option value="execution">执行式（生成执行计划/调用外部系统）</option>
            <option value="transformation">转换/抽取式（格式转换、字段抽取）</option>
          </select>
        </div>

        <div>
          <div className="text-sm font-medium text-gray-300 mb-2">输出是否需要结构化（JSON）？</div>
          <label className="flex items-center gap-2 text-sm text-gray-200">
            <input type="checkbox" checked={wizStructured} onChange={() => setWizStructured(!wizStructured)} />
            是（会补一个稳定的 result/object 输出结构）
          </label>
        </div>

        <div>
          <div className="text-sm font-medium text-gray-300 mb-2">是否可能写入/修改外部系统？</div>
          <label className="flex items-center gap-2 text-sm text-gray-200">
            <input type="checkbox" checked={wizMayWrite} onChange={() => setWizMayWrite(!wizMayWrite)} />
            可能（会在 config/SOP 里加入二次确认提示）
          </label>
        </div>
      </div>
    </Modal>
    </>
  );
};

export default AddSkillModal;
