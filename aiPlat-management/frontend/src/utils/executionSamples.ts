/**
 * Shared smoke-test sample generators for Skill / Agent / Tool / MCP execute UIs.
 * Mirrors backend core.management.execution_examples heuristics.
 */

export type FieldSpec = {
  type?: string;
  description?: string;
  default?: unknown;
  enum?: string[];
  required?: boolean;
};

export function sampleValueForField(
  name: string,
  spec?: FieldSpec | null,
  opts?: { skillHint?: string },
): unknown {
  const key = String(name || '').trim().toLowerCase();
  const typ = String(spec?.type || '').toLowerCase();
  const desc = String(spec?.description || '');

  if (spec?.default !== undefined) return spec.default;
  if (Array.isArray(spec?.enum) && spec!.enum!.length > 0) return spec!.enum![0];

  if (key === 'outline') {
    return {
      title: 'aiPlat 产品介绍',
      sections: [
        {
          title: '背景与目标',
          pages: [
            { title: '我们要解决什么', bullets: ['交付慢', '知识难沉淀', '质量难度量'] },
            { title: '目标', bullets: ['缩短交付周期', '可治理执行'] },
          ],
        },
      ],
    };
  }

  const longArticle =
    '【产品周报｜2026-W38】\n' +
    '\n' +
    '一、本周进展\n' +
    '资产审批增加 Agent 上架硬门禁：绑定 Skill/MCP 须已发布或已上架，Tool 须在注册表可用，' +
    '否则拒绝上架并返回依赖明细。应用库 Skill/Agent/Tool/MCP 列表支持按名称与描述搜索。' +
    'PPT 生成 Skill 可按大纲与模版写出 .pptx；审批流已打通提交审核→通过→上架。\n' +
    '\n' +
    '二、问题与风险\n' +
    '1. 默认 PPT 模版视觉偏简，客户演示观感不足；\n' +
    '2. 部分 Skill 冒烟用例仍是一句话占位，难以验证长文压缩/结构化输出质量；\n' +
    '3. 若干 workspace Skill 停在 ready，阻塞依赖它们的 Agent 上架。\n' +
    '\n' +
    '三、下周计划\n' +
    '- 按能力类型丰富执行测试用例（摘要/检索/生成等给出可执行样例）\n' +
    '- 迭代 default.pptx 版式与拆页策略\n' +
    '- 清理待审核 Skill 队列，优先 unblock 被依赖项\n' +
    '\n' +
    '请输出：3 条要点 + 1 条风险 + 1 条行动建议（中文，条目化，勿编造原文没有的事实）。';

  void opts?.skillHint;

  const stringSamples: Record<string, string> = {
    query: '企业知识库里，关于资产审批硬门禁与 Skill 上架依赖校验的最新规范是什么？请给出出处要点。',
    topic: '为客户做一份「aiPlat 资产审批与上架治理」产品介绍，突出硬门禁与迭代路径',
    markdown:
      '# 资产审批周报\n\n' +
      '## 进展\n' +
      '- Agent 上架前校验 Skill/MCP/Tool 依赖\n' +
      '- 应用库支持名称/描述搜索\n\n' +
      '## 风险\n' +
      '- 默认 PPT 模版过简\n' +
      '- 冒烟用例偏弱\n\n' +
      '## 行动\n' +
      '- 丰富测试用例生成器\n' +
      '- 迭代 default.pptx\n',
    message: longArticle,
    prompt: longArticle,
    text: longArticle,
    content: longArticle,
    input: longArticle,
    template_name: 'default',
    template: 'default',
    url: 'https://example.com',
    path: '/tmp/example.txt',
    directory: '/tmp',
    command: 'echo hello',
    cmd: 'echo hello',
    name: 'demo',
    title: '资产审批与上架治理周报',
  };
  if (key in stringSamples) return stringSamples[key];

  if (key === 'template_path' || key === 'source_path' || key === 'file_path') return '';

  if (key.includes('max_chars')) return 200;

  if (typ === 'boolean' || typ === 'bool' || key.startsWith('is_') || key.startsWith('enable_')) {
    return true;
  }
  if (typ === 'integer' || typ === 'int' || key.endsWith('_count') || key.endsWith('_limit')) {
    return 3;
  }
  if (typ === 'number' || typ === 'float') return 1.0;
  if (typ === 'array' || typ === 'list') return ['示例项1', '示例项2'];
  if (typ === 'object' || typ === 'dict') return { key: 'value' };

  if (desc) return `示例：${desc.slice(0, 48)}`;
  return `示例_${key || 'value'}`;
}

/** Flatten JSON Schema {properties, required} or pass-through flat maps. */
export function flattenJsonSchema(schema: any): Record<string, FieldSpec> {
  if (!schema || typeof schema !== 'object') return {};
  const props = schema.properties;
  if (props && typeof props === 'object') {
    const required = new Set<string>((schema.required || []).map(String));
    const out: Record<string, FieldSpec> = {};
    for (const [k, v] of Object.entries(props as Record<string, any>)) {
      if (v && typeof v === 'object') {
        out[k] = { ...(v as FieldSpec), required: required.has(k) || !!(v as any).required };
      } else {
        out[k] = { type: 'string', required: required.has(k) };
      }
    }
    return out;
  }
  return schema as Record<string, FieldSpec>;
}

export function buildSampleParamsFromSchema(
  schema: any,
  opts?: { includeOptional?: boolean; skillHint?: string },
): Record<string, unknown> {
  const flat = flattenJsonSchema(schema);
  const includeOptional = opts?.includeOptional !== false;
  const skillHint = opts?.skillHint || '';
  const payload: Record<string, unknown> = {};
  for (const [k, spec] of Object.entries(flat)) {
    const isReq = !!spec?.required;
    if (includeOptional || isReq) {
      const sample = sampleValueForField(k, spec, { skillHint });
      if (typeof sample === 'object' && sample !== null) {
        payload[k] = sample;
      } else {
        payload[k] = sample;
      }
    }
  }
  if (!includeOptional && Object.keys(payload).length === 0) {
    for (const [k, spec] of Object.entries(flat)) {
      payload[k] = sampleValueForField(k, spec, { skillHint });
    }
  }
  return payload;
}

/** For Tool/MCP form fields: stringify object/array samples for textarea. */
export function buildFormParamsFromSchema(
  schema: any,
  opts?: { includeOptional?: boolean },
): Record<string, any> {
  const raw = buildSampleParamsFromSchema(schema, opts);
  const out: Record<string, any> = {};
  const flat = flattenJsonSchema(schema);
  for (const [k, v] of Object.entries(raw)) {
    const typ = String(flat[k]?.type || '').toLowerCase();
    if ((typ === 'object' || typ === 'array') && typeof v === 'object') {
      out[k] = JSON.stringify(v, null, 2);
    } else {
      out[k] = v;
    }
  }
  return out;
}

export function isGenericExampleSet(examples?: Array<{ title?: string; content?: string }> | null): boolean {
  if (!examples || examples.length === 0) return true;
  if (examples.every((e) => /^通用/.test(String(e?.title || '').trim()))) return true;
  // Legacy one-liner smoke placeholder — treat as generic so UI regenerates rich samples.
  const legacy = '请按本能力说明完成一次冒烟测试';
  return examples.every((e) => String(e?.content || '').includes(legacy));
}

/** Build click-to-fill examples (mirrors backend build_examples_from_input_schema). */
export function buildExamplesFromSchema(
  schema: any,
  label = '本能力',
  opts?: { skillHint?: string },
): Array<{ title: string; content: string }> {
  const flat = flattenJsonSchema(schema);
  if (!flat || Object.keys(flat).length === 0) return [];

  const skillHint = opts?.skillHint || label;
  const required = buildSampleParamsFromSchema(flat, { includeOptional: false, skillHint });
  const full = buildSampleParamsFromSchema(flat, { includeOptional: true, skillHint });
  const name = (label || '本能力').trim() || '本能力';
  const examples: Array<{ title: string; content: string }> = [
    { title: `${name}（必填字段）`, content: JSON.stringify(required, null, 2) },
  ];
  if (JSON.stringify(required) !== JSON.stringify(full)) {
    examples.push({ title: `${name}（含可选字段）`, content: JSON.stringify(full, null, 2) });
  }

  const primaryTextKeys = new Set(['message', 'prompt', 'query', 'topic', 'markdown', 'text', 'content', 'input']);
  for (const [k, spec] of Object.entries(flat)) {
    if (primaryTextKeys.has(k.toLowerCase())) {
      const sample = sampleValueForField(k, spec, { skillHint });
      if (typeof sample === 'string') {
        examples.push({ title: `${name}（纯文本）`, content: sample });
        break;
      }
    }
  }
  if (flat.outline && !examples.some((e) => e.title.includes('纯文本') || e.title.includes('大纲文本'))) {
    examples.push({
      title: `${name}（大纲文本）`,
      content:
        '标题：aiPlat 产品介绍\n\n一、背景与目标\n- 交付慢、知识难沉淀\n- 目标：缩短交付周期、可治理执行\n\n二、方案概览\n- 八层架构：本体底座 / 知识引擎 / 上下文总线\n',
    });
  }
  return examples;
}

/** Agent smoke cases from bound skills/tools (mirrors backend build_agent_task_examples). */
export function buildAgentTaskExamples(opts: {
  displayName?: string;
  description?: string;
  skillIds?: string[];
  toolIds?: string[];
}): Array<{ title: string; content: string }> {
  const label = (opts.displayName || 'Agent').trim() || 'Agent';
  const skills = new Set((opts.skillIds || []).map((s) => String(s).toLowerCase()));
  const tools = new Set((opts.toolIds || []).map((t) => String(t).toLowerCase()));
  const desc = (opts.description || '').trim();
  const taskHint = desc ? `任务背景：${desc}\n` : '';

  if ([...skills].some((s) => ['ppt_generation', 'pptx_generation', 'slide_generation'].includes(s))) {
    const outlineText =
      `${taskHint}` +
      '请根据以下大纲生成 PPT：\n' +
      '标题：aiPlat 产品介绍\n' +
      '一、背景与目标\n' +
      '- 交付慢、知识难沉淀\n' +
      '- 目标：缩短交付周期\n' +
      '二、方案概览\n' +
      '- 八层架构要点\n';
    return [
      { title: `${label}（PPT 文本）`, content: outlineText },
      { title: `${label}（PPT JSON）`, content: JSON.stringify({ message: outlineText.trim() }, null, 2) },
    ];
  }

  if (skills.has('site_tester') || [...skills].some((s) => s.includes('browser')) || tools.has('browser')) {
    const msg = `${taskHint}请对 https://example.com 做一次冒烟巡检，输出通过/失败摘要。`;
    return [
      { title: `${label}（URL 文本）`, content: msg },
      {
        title: `${label}（JSON）`,
        content: JSON.stringify({ message: msg.trim(), url: 'https://example.com' }, null, 2),
      },
    ];
  }

  if (tools.has('file_operations')) {
    const msg = `${taskHint}请列出 /tmp 下最近修改的文件，并给出简要说明。`;
    return [
      { title: `${label}（目录任务）`, content: msg },
      {
        title: `${label}（JSON）`,
        content: JSON.stringify({ message: msg.trim(), directory: '/tmp' }, null, 2),
      },
    ];
  }

  const msg =
    `${taskHint}` +
    '请完成以下任务：\n按本 Agent 的职责做一次冒烟验证（说明你做了什么、结果如何）。';
  return [
    { title: `${label}（文本）`, content: msg },
    { title: `${label}（JSON）`, content: JSON.stringify({ message: msg.trim() }, null, 2) },
  ];
}
