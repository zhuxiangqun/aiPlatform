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

const SIZE_LIMIT_RE =
  /(?:不超过|不大于|最大|限制|max(?:imum)?|up\s*to|<=|<)\s*(\d+(?:\.\d+)?)\s*(gb|g|mb|m|kb|k|b|字节)?|(\d+(?:\.\d+)?)\s*(gb|mb|kb)\s*(?:以内|以下|限制)/i;
const UNIT_BYTES: Record<string, number> = {
  gb: 1024 ** 3,
  g: 1024 ** 3,
  mb: 1024 ** 2,
  m: 1024 ** 2,
  kb: 1024,
  k: 1024,
  b: 1,
  字节: 1,
};
const FILE_EXT_HINTS: Array<[string, string]> = [
  ['mp4', '.mp4'],
  ['mov', '.mov'],
  ['avi', '.avi'],
  ['mkv', '.mkv'],
  ['webm', '.webm'],
  ['pdf', '.pdf'],
  ['png', '.png'],
  ['jpeg', '.jpg'],
  ['jpg', '.jpg'],
  ['gif', '.gif'],
  ['wav', '.wav'],
  ['mp3', '.mp3'],
  ['csv', '.csv'],
  ['xlsx', '.xlsx'],
  ['json', '.json'],
  ['zip', '.zip'],
  ['txt', '.txt'],
];

function parseSizeLimitBytes(text?: string): number | null {
  const s = String(text || '').trim();
  if (!s) return null;
  const m = s.match(SIZE_LIMIT_RE);
  if (!m) return null;
  const n = Number(m[1] || m[3]);
  const unit = String(m[2] || m[4] || 'b').toLowerCase();
  if (!Number.isFinite(n) || n <= 0) return null;
  const mul = UNIT_BYTES[unit] ?? 1;
  const val = Math.trunc(n * mul);
  return val > 0 ? val : null;
}

function looksLikeByteSize(key: string, desc: string, typ: string): boolean {
  if (!['integer', 'int', 'number', 'float', ''].includes(typ)) return false;
  if (['_bytes', 'filesize', 'file_size', 'byte_size', 'content_length'].some((t) => key.includes(t))) return true;
  if (key.endsWith('_size') && !key.includes('page') && !key.includes('batch')) return true;
  const blob = `${key} ${desc}`.toLowerCase();
  return ['字节', 'bytes', 'byte'].some((t) => blob.includes(t));
}

function extFromDesc(desc: string, key = ''): string {
  const blob = `${desc} ${key}`.toLowerCase();
  for (const [needle, ext] of FILE_EXT_HINTS) {
    if (blob.includes(needle)) return ext;
  }
  if (['视频', 'video'].some((t) => blob.includes(t))) return '.mp4';
  if (['图片', 'image', 'photo'].some((t) => blob.includes(t))) return '.png';
  if (['音频', 'audio'].some((t) => blob.includes(t))) return '.wav';
  return '.bin';
}

function looksLikeFileRef(key: string, typ: string): boolean {
  if (['file', 'binary', 'blob', 'path'].includes(typ)) return true;
  if (['_size', '_count', '_limit', '_bytes'].some((t) => key.includes(t))) return false;
  return (
    ['file', 'filename', 'filepath', 'video', 'audio', 'image', 'attachment', 'upload', 'document', 'doc'].includes(key)
    || key.endsWith('_file')
    || key.endsWith('_path')
  );
}

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

  if (key === 'user_requirement' || key === 'requirement' || key === 'requirements' || key === 'prd_input'
      || key === 'instruction' || key === 'task' || key === 'brief' || key === 'scenario') {
    const label = String(opts?.skillHint || '本能力');
    const topic = String(spec?.description || key);
    const complex = String(opts?.skillHint || '').toLowerCase().includes('complex')
      || String(opts?.skillHint || '').includes('复杂');
    if (complex) {
      return (
        `【复杂冒烟｜${label}】\n` +
        `围绕字段「${key}」（${topic}）构造多约束场景：\n` +
        `- 角色/干系人 ≥2；\n` +
        `- 范围：主流程 + 边界；明确 2 件「本次不做」；\n` +
        `- 约束：同时覆盖「依赖未就绪」与「合规/安全」类边界（未知标待确认）；\n` +
        `- 验收：可计数/可复现；禁止「功能正常」；\n` +
        `禁止编造未提供的具体 SLA/密钥/渠道细节。`
      );
    }
    return (
      `【简单冒烟｜${label}】\n` +
      `围绕字段「${key}」（${topic}）给出最小可验收输入：\n` +
      `- 角色与目标；\n` +
      `- 范围：只做核心路径；明确 1 件不做；\n` +
      `- 约束：1 条可检查边界（未知标待确认）；\n` +
      `- 未知：1 个待确认问题；\n` +
      `请按契约返回可检查结果（勿空话）。`
    );
  }

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

  if (key === 'template_path') return '';
  if (looksLikeFileRef(key, typ) || key === 'source_path' || key === 'file_path') {
    return `/tmp/sample${extFromDesc(desc, key)}`;
  }
  if (key === 'duration' || key === 'time_str' || key === 'elapsed'
      || desc.toLowerCase().includes('hh:mm:ss') || desc.includes('HH:MM:SS')) {
    return '00:01:30';
  }
  if (key.includes('email') || desc.includes('邮箱')) return 'user@example.com';
  if (key.includes('resolution') || desc.includes('清晰度')) return '1080p';

  if (key.includes('max_chars')) return 200;

  if (typ === 'boolean' || typ === 'bool' || key.startsWith('is_') || key.startsWith('enable_')) {
    return true;
  }
  if (looksLikeByteSize(key, desc, typ)) {
    const limit = parseSizeLimitBytes(desc);
    if (limit) return Math.max(1, Math.min(Math.floor(limit / 8), 8 * 1024 * 1024));
    return 1024 * 1024;
  }
  if (typ === 'integer' || typ === 'int' || key.endsWith('_count') || key.endsWith('_limit')) {
    if (key.includes('percent') || desc.includes('进度') || desc.includes('百分比')) return 50;
    return 3;
  }
  if (typ === 'number' || typ === 'float') return 1.0;
  if (typ === 'array' || typ === 'list') return ['示例项1', '示例项2'];
  if (typ === 'object' || typ === 'dict') return { key: 'value' };

  return `sample_${key || 'value'}`;
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

/** Extra instruction for LLM generate: typed required fields + optional input-box draft. */
export function buildExampleRefineHint(schema?: any, draft?: string): string {
  const lines: string[] = [];
  const flat = flattenJsonSchema(schema);
  const required = Object.entries(flat)
    .filter(([, spec]) => !!spec?.required)
    .map(([k]) => k);
  if (required.length) {
    lines.push(`必填字段：${required.join('、')}。至少一条 content 为覆盖这些键的合法 JSON。`);
  }
  for (const [k, spec] of Object.entries(flat)) {
    const typ = String(spec?.type || '').toLowerCase();
    const desc = String(spec?.description || '');
    const key = k.toLowerCase();
    if (looksLikeFileRef(key, typ)) {
      lines.push(`「${k}」必须是路径（如 /tmp/sample.mp4），禁止填写字段说明或「示例：」+ 说明。`);
    }
    if (looksLikeByteSize(key, desc, typ)) {
      lines.push(`「${k}」必须是字节整数，遵守描述中的「不超过」上限；禁止填 3 这类占位。`);
    }
  }
  const draftS = String(draft || '').trim();
  if (draftS) {
    lines.push(`用户当前输入框草稿（可参考，错误占位不要照抄）：\n${draftS.slice(0, 1500)}`);
  }
  return lines.join('\n');
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

const EXAMPLE_PREFIX_RE = /^示例[：:]\s*/;

function fieldDescriptions(schema: any): string[] {
  const out: string[] = [];
  for (const spec of Object.values(flattenJsonSchema(schema))) {
    const d = String((spec as FieldSpec)?.description || '').trim();
    if (d) out.push(d);
  }
  return out;
}

export function valueCopiesFieldDescription(
  value: unknown,
  spec?: FieldSpec | null,
  allDescs?: string[],
): boolean {
  if (typeof value !== 'string') return false;
  const s = value.trim();
  if (!s) return false;
  const body = s.replace(EXAMPLE_PREFIX_RE, '').trim();
  const descs: string[] = [];
  const own = String(spec?.description || '').trim();
  if (own) descs.push(own);
  for (const d of allDescs || []) {
    if (d && !descs.includes(d)) descs.push(d);
  }
  const prefixed = EXAMPLE_PREFIX_RE.test(s);
  if (prefixed && descs.length === 0) return true;
  for (const d of descs) {
    if (d.length < 4) continue;
    if (s === d || body === d || body === d.slice(0, 48)) return true;
    if (prefixed && d.slice(0, Math.min(12, d.length)) && s.includes(d.slice(0, Math.min(12, d.length))) && s.length <= d.length + 12) {
      return true;
    }
  }
  return false;
}

export function rewriteCopiedDescriptionValues(
  obj: Record<string, unknown>,
  schema: any,
  skillHint = '',
): Record<string, unknown> {
  const flat = flattenJsonSchema(schema);
  const allDescs = fieldDescriptions(schema);
  const out: Record<string, unknown> = { ...obj };
  for (const [k, v] of Object.entries(out)) {
    const spec = (flat[k] && typeof flat[k] === 'object') ? flat[k] : { type: 'string' };
    const keyL = String(k).toLowerCase();
    const typ = String(spec?.type || '').toLowerCase();
    const desc = String(spec?.description || '');
    if (v && typeof v === 'object' && !Array.isArray(v) && ['object', 'dict', ''].includes(typ)) {
      out[k] = rewriteCopiedDescriptionValues(v as Record<string, unknown>, spec, skillHint);
      continue;
    }
    if (valueCopiesFieldDescription(v, spec, allDescs)) {
      out[k] = sampleValueForField(k, spec, { skillHint });
      continue;
    }
    if (looksLikeByteSize(keyL, desc, typ) && typeof v === 'number' && v > 0 && v < 1024) {
      out[k] = sampleValueForField(k, spec, { skillHint });
    }
  }
  return out;
}

/** Rewrite persisted/API chips so field descriptions are never used as values. */
export function sanitizeExecutionExamples(
  examples: Array<{ title?: string; content?: string }> | null | undefined,
  schema: any,
  skillHint = '',
): Array<{ title: string; content: string }> {
  const out: Array<{ title: string; content: string }> = [];
  const allDescs = fieldDescriptions(schema);
  for (const e of examples || []) {
    const title = String(e?.title || '').trim();
    const content = e?.content;
    if (!title || content == null) continue;
    let obj: unknown = null;
    if (typeof content === 'object') obj = content;
    else {
      try { obj = JSON.parse(String(content)); } catch { obj = null; }
    }
    let contentS: string;
    if (obj && typeof obj === 'object' && !Array.isArray(obj)) {
      contentS = JSON.stringify(
        rewriteCopiedDescriptionValues(obj as Record<string, unknown>, schema, skillHint),
        null,
        2,
      );
    } else {
      contentS = String(content).trim();
      if (valueCopiesFieldDescription(contentS, null, allDescs)) continue;
    }
    if (contentS) out.push({ title: title.slice(0, 80), content: contentS.slice(0, 8000) });
  }
  return out;
}

export function isGenericExampleSet(examples?: Array<{ title?: string; content?: string }> | null): boolean {
  if (!examples || examples.length === 0) return true;
  const hasExamplePrefix = examples.some((e) => {
    const raw = String(e?.content || '').trim();
    try {
      const obj = JSON.parse(raw);
      if (obj && typeof obj === 'object' && !Array.isArray(obj)) {
        return Object.values(obj).some((v) => typeof v === 'string' && EXAMPLE_PREFIX_RE.test(v.trim()));
      }
    } catch {
      /* not json */
    }
    return EXAMPLE_PREFIX_RE.test(raw);
  });
  if (hasExamplePrefix) return true;
  // Legacy placeholder titles were literally "通用…" — not display names like「通用助手」
  const legacyGenericTitle = (t: string) => {
    const s = String(t || '').trim();
    if (!s.startsWith('通用')) return false;
    const rest = s.slice(2);
    if (!rest) return true;
    return ['（', '(', '-', '—', ' ', '示', '冒'].includes(rest[0]);
  };
  if (examples.every((e) => legacyGenericTitle(String(e?.title || '')))) return true;
  const legacyMarkers = [
    '请按本能力说明完成一次冒烟测试',
    '按本 Agent 的职责做一次冒烟验证',
  ];
  if (examples.every((e) => {
    const c = String(e?.content || '');
    return legacyMarkers.some((m) => c.includes(m));
  })) {
    return true;
  }
  if (examples.some((e) => {
    const s = String(e?.content || '').trim();
    if (/^示例[：:]/.test(s)) return true;
    try {
      const obj = JSON.parse(s);
      if (obj && typeof obj === 'object' && !Array.isArray(obj)) {
        return Object.values(obj).some((v) => typeof v === 'string' && /^示例[：:]/.test(String(v).trim()));
      }
    } catch {
      /* not json */
    }
    return false;
  })) {
    return true;
  }
  // Stale FE samples that still ask for FastAPI/Pydantic (backend) — regenerate to TS module.
  // Do not treat「禁止 Python/FastAPI」as backend-shaped — that is the isolated FE recipe.
  if (
    examples.some((e) => {
      const title = String(e?.title || '');
      const c = String(e?.content || '');
      const feTitle = /前端/.test(title) || /frontend/i.test(title);
      if (/禁止\s*Python\/FastAPI|单独测·可组装切片/.test(c) || /单独测/.test(title)) {
        return false;
      }
      const backendShape =
        /Pydantic\s*model/i.test(c) ||
        (/路由\s*\+\s*Pydantic/.test(c) && /FastAPI|APIRouter|curl\s+-X\s+POST/i.test(c)) ||
        (/报障 API·小切片/.test(title) && !/TS\s*客户端|可组装/.test(title));
      const staleClientOnly =
        feTitle &&
        /apiClient|api\/apiClient/i.test(c) &&
        !/types\.ts/i.test(c) &&
        !/pages\/.*\.tsx|ReportFaultPage/i.test(c);
      return (feTitle && backendShape) || staleClientOnly;
    })
  ) {
    return true;
  }
  // Thin JSON one-liners (e.g. 「做个搜索」) — regenerate
  const thin = (content: string) => {
    const s = String(content || '').trim();
    try {
      const obj = JSON.parse(s);
      if (obj && typeof obj === 'object' && !Array.isArray(obj)) {
        const vals = Object.values(obj);
        if (vals.some((v) => typeof v === 'string' && /^示例[：:]/.test(String(v).trim()))) return true;
        const typed = vals.filter((v) => {
          if (typeof v === 'boolean' || typeof v === 'number') return true;
          if (typeof v === 'string') {
            const t = v.trim();
            return /^(\.?\.?\/|https?:\/\/|\/tmp\/|sample_)/.test(t);
          }
          return !!v && typeof v === 'object';
        }).length;
        if (typed >= Math.max(1, Math.ceil(vals.length / 2))) return false;
        const leaves = vals.filter((v) => typeof v === 'string' || typeof v === 'number');
        if (leaves.length && leaves.every((v) => String(v).length < 60) && s.length < 220) return true;
      }
    } catch {
      /* not json */
    }
    if (s.length < 80) return true;
    return false;
  };
  return examples.every((e) => thin(String(e?.content || '')));
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
  const skillL = skillHint.toLowerCase();
  const name = (label || '本能力').trim() || '本能力';

  if (
    skillL.includes('requirement_analysis') ||
    skillL.includes('prd') ||
    skillL.includes('需求分析') ||
    skillL.includes('需求文档') ||
    (flat.user_requirement &&
      (skillL.includes('需求') || skillL.includes('requirement') || skillL.includes('analysis')))
  ) {
    const primary = flat.user_requirement ? 'user_requirement' : Object.keys(flat)[0];
    const simple = sampleValueForField(primary, flat[primary], { skillHint: 'generic' });
    const complex = sampleValueForField(primary, flat[primary], { skillHint: 'requirement_analysis' });
    return [
      {
        title: `${name} - 简单示例（含边界）`,
        content: JSON.stringify({ [primary]: simple }, null, 2),
      },
      {
        title: `${name} - 复杂示例（多约束）`,
        content: JSON.stringify({ [primary]: complex }, null, 2),
      },
    ];
  }

  const required = buildSampleParamsFromSchema(flat, { includeOptional: false, skillHint });
  const full = buildSampleParamsFromSchema(flat, { includeOptional: true, skillHint });
  const boundary = buildBoundaryParamsFromSchema(flat, { skillHint });
  const examples: Array<{ title: string; content: string }> = [
    { title: `${name}（主路径·必填）`, content: JSON.stringify(required, null, 2) },
    { title: `${name}（边界/异常）`, content: JSON.stringify(boundary, null, 2) },
  ];
  if (JSON.stringify(required) !== JSON.stringify(full)) {
    const complex = { ...full };
    for (const [k, v] of Object.entries(complex)) {
      if (
        typeof v === 'string' &&
        v.length < 100 &&
        ['message', 'prompt', 'query', 'topic', 'text', 'content', 'input', 'user_requirement'].includes(k.toLowerCase())
      ) {
        complex[k] = sampleValueForField(k, flat[k], { skillHint: `${skillHint} 复杂` });
      }
    }
    examples.push({ title: `${name}（复杂·全量）`, content: JSON.stringify(complex, null, 2) });
  }

  const primaryTextKeys = new Set(['message', 'prompt', 'query', 'topic', 'markdown', 'text', 'content', 'input']);
  for (const [k, spec] of Object.entries(flat)) {
    if (primaryTextKeys.has(k.toLowerCase())) {
      const sample = sampleValueForField(k, spec, { skillHint });
      if (typeof sample === 'string' && sample.length >= 80) {
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

/** Boundary / negative smoke values for Tool/MCP schema fields. */
export function boundaryValueForField(name: string, spec: FieldSpec | null | undefined, happy: unknown): unknown {
  const key = String(name || '').trim().toLowerCase();
  const typ = String(spec?.type || '').toLowerCase();
  if (Array.isArray(spec?.enum) && spec!.enum!.length >= 2) return spec!.enum![spec!.enum!.length - 1];
  if (typ === 'boolean' || typ === 'bool' || key.startsWith('is_') || key.startsWith('enable_')) {
    return happy === true ? false : true;
  }
  if (looksLikeByteSize(key, String(spec?.description || ''), typ)) {
    const limit = parseSizeLimitBytes(String(spec?.description || ''));
    if (limit) return limit + 1;
    return 0;
  }
  if (typ === 'integer' || typ === 'int' || key.endsWith('_count') || key.endsWith('_limit')) return 0;
  if (typ === 'number' || typ === 'float') return -1.0;
  if (typ === 'array' || typ === 'list') return [];
  if (typ === 'object' || typ === 'dict') return {};
  if (key.includes('url') || key === 'uri' || key === 'endpoint' || key === 'href') {
    return 'http://127.0.0.1:9/should-be-unreachable';
  }
  if (
    looksLikeFileRef(key, typ)
    || ['path', 'file_path', 'source_path', 'template_path', 'directory'].includes(key)
  ) {
    return '/tmp/__aiplat_missing_path__.txt';
  }
  if (key === 'command' || key === 'cmd') return 'false';
  if (typeof happy === 'string') return happy.length > 40 ? '' : ' ';
  return happy ?? '';
}

export function buildBoundaryParamsFromSchema(
  schema: any,
  opts?: { skillHint?: string },
): Record<string, unknown> {
  const flat = flattenJsonSchema(schema);
  const happy = buildSampleParamsFromSchema(flat, { includeOptional: false, skillHint: opts?.skillHint });
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(happy)) {
    out[k] = boundaryValueForField(k, flat[k], v);
  }
  if (Object.keys(out).length === 0) {
    for (const [k, spec] of Object.entries(flat)) {
      const sample = sampleValueForField(k, spec, { skillHint: opts?.skillHint });
      out[k] = boundaryValueForField(k, spec, sample);
    }
  }
  return out;
}

/** Tool/MCP execute chips — mirrors backend build_param_smoke_examples. */
export function buildParamSmokeExamples(
  schema: any,
  label = 'Tool',
  opts?: { skillHint?: string },
): Array<{ title: string; content: string }> {
  return buildExamplesFromSchema(schema, label, opts);
}

/** Workflow start-node smoke chips. */
export function buildWorkflowStartExamples(opts: {
  startInputs?: Array<{ key?: string; name?: string; value?: string }>;
  workflowName?: string;
}): Array<{ title: string; content: string }> {
  const label = (opts.workflowName || 'Workflow').trim() || 'Workflow';
  let keys = (opts.startInputs || [])
    .map((r) => String(r.key || r.name || '').trim())
    .filter(Boolean);
  if (!keys.length) keys = ['message', 'query'];

  const valueFor = (key: string, mode: 'happy' | 'boundary' | 'complex'): unknown => {
    const spec: FieldSpec = { type: 'string' };
    if (mode === 'boundary') {
      const happy = sampleValueForField(key, spec, { skillHint: label });
      return boundaryValueForField(key, spec, happy);
    }
    if (mode === 'complex') {
      return sampleValueForField(key, spec, { skillHint: `${label} 复杂` });
    }
    return sampleValueForField(key, spec, { skillHint: label });
  };

  const asJson = (mode: 'happy' | 'boundary' | 'complex') =>
    JSON.stringify(Object.fromEntries(keys.map((k) => [k, valueFor(k, mode)])), null, 2);

  return [
    { title: `${label}（主路径）`, content: asJson('happy') },
    { title: `${label}（边界/异常）`, content: asJson('boundary') },
    { title: `${label}（复杂·多约束）`, content: asJson('complex') },
  ];
}

export function workflowExampleToStartInputs(content: string): Array<{ key: string; value: string }> {
  try {
    const obj = JSON.parse(content);
    if (obj && typeof obj === 'object' && !Array.isArray(obj)) {
      return Object.entries(obj).map(([k, v]) => ({
        key: String(k),
        value: v == null ? '' : typeof v === 'string' ? v : JSON.stringify(v),
      }));
    }
  } catch {
    /* not json */
  }
  return [{ key: 'message', value: String(content || '') }];
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
  const labelBlob = `${label} ${desc}`.toLowerCase();

  if ([...skills].some((s) => ['ppt_generation', 'pptx_generation', 'slide_generation'].includes(s))) {
    const outlineText =
      `${taskHint}` +
      '请根据以下大纲生成 PPT（有默认模版也须先确认再生成）：\n' +
      '标题：aiPlat 产品介绍\n' +
      '一、背景与目标\n' +
      '- 交付慢、知识难沉淀\n' +
      '- 目标：缩短交付周期\n' +
      '二、方案概览\n' +
      '- 八层架构要点\n' +
      '三、下一步\n' +
      '- 试点范围与成功指标\n' +
      '\n' +
      '约束：不编造数据；输出 pptx 绝对路径；生成前列出将使用的模版路径请用户确认。';
    return [
      { title: `${label}（PPT 大纲）`, content: outlineText },
      { title: `${label}（PPT JSON）`, content: JSON.stringify({ message: outlineText.trim() }, null, 2) },
    ];
  }

  const isResearch =
    skills.has('last30days') ||
    skills.has('knowledge_multi_query') ||
    ['调研', 'research', '竞品', 'paper_monitor', 'competitor'].some((k) => labelBlob.includes(k));
  if (isResearch) {
    const researchMsg =
      `${taskHint}` +
      '【调研任务】话题：企业级 Agent 平台的「技能上架审批」实践（最近 30 天）。\n\n' +
      '请完成一次可验收的调研冒烟（不要只堆链接）：\n' +
      '1. 从至少 3 类来源检索（如 HN / Reddit / 技术博客 / 文档站；没有某源就跳过并说明）；\n' +
      '2. 输出结构化报告：共识观点 / 争议焦点 / 新兴趋势 / 可能偏见；\n' +
      '3. 每个观点至少标注 1 个可点击来源（标题+URL）；\n' +
      '4. 末尾给「对我们产品的 3 条可执行建议」。\n' +
      '禁止编造未检索到的来源。';
    const narrowMsg =
      `${taskHint}` +
      '只做开场规划：话题「本地 LLM 推理网关选型」。\n' +
      '- 列出检索关键词（中英各 4 个）与计划访问的来源清单；\n' +
      '- 说明成功标准（报告章节骨架）；\n' +
      '- 暂不抓全文，等用户确认后再深挖。';
    return [
      { title: `${label}（技能上架·调研报告）`, content: researchMsg },
      { title: `${label}（选题·检索规划）`, content: narrowMsg },
      { title: `${label}（调研 JSON）`, content: JSON.stringify({ message: researchMsg.trim() }, null, 2) },
    ];
  }

  const nameL = label.toLowerCase();
  const isPm =
    skills.has('requirement_analysis') ||
    ['产品经理', 'pm_agent', 'product manager', '产品负责人'].some((k) => nameL.includes(k));
  if (isPm) {
    const prdMsg =
      `${taskHint}` +
      '【客户口述｜请按产品经理职责做草稿轮/冒烟，不要 PRD_READY】\n' +
      '客户：江苏某制造企业，想做一个「现场巡检报障」小应用。\n' +
      '- 一线工人用手机拍照上报设备异常；班组长审批后派维修。\n' +
      '- 希望和现有钉钉账号打通，但暂时没有开放 API 文档。\n' +
      '- 管理层要看「本周报障量 / 平均闭环时长」两个数。\n' +
      '- 上线时间：希望 6 周内能试点 1 个车间；预算与编制未定。\n' +
      '- 合规：照片可能含产线布局，不能传到公网。\n' +
      '\n' +
      '请完成一次可验收的需求分析草稿（不要只回「已验证」）：\n' +
      '1. 列出至少 5 个必须向客户追问的澄清问题（按优先级，每题说明为什么问）；\n' +
      '2. 基于已知信息起草结构化 PRD 草稿，至少包含：\n' +
      '   - 背景与目标 / 用户与场景 / 功能需求(FR-001…) / 非功能需求 / 验收标准(AC) /\n' +
      '     待确认问题 / 里程碑假设（分期切片，勿把开放问题当里程碑）；\n' +
      '3. 每条 FR 给出可验证 AC（禁止「清晰可见/功能正常/实际操作测试」）；\n' +
      '4. 信息不足一律标「待确认」；禁止编造多语言、具体 SLA、加密方案、\n' +
      '   「已在钉钉应用内完成全流程」等未口述边界。\n' +
      '\n' +
      '【硬性自检——缺任一条视为失败】\n' +
      '- 正文必须显式保留「照片不能传到公网 / 不上公网」（不得弱化成笼统合规）；\n' +
      '- 正文必须显式保留「钉钉 API 文档未开放 / 集成方式待确认」；\n' +
      '- 不要输出 <!-- PRD_READY -->；不要在文末再套一层 markdown 代码块复读全文。\n' +
      '优先调用技能 requirement_analysis；输出一份中文 Markdown 即可。';
    const clarifyingMsg =
      `${taskHint}` +
      '用户只说了一句：「我们想做个智能客服，能回答知识库里的制度问题。」\n' +
      '\n' +
      '请以产品经理身份开场澄清（不要直接写完整 PRD）：\n' +
      '- 用 6～8 个选择题/填空题把范围钉住（渠道、知识源、权限、幻觉处理、转人工、成功指标）；\n' +
      '- 每题说明「为什么要问」；\n' +
      '- 最后给一版「若用户全选默认值」的范围摘要（≤8 行），方便下一轮生成 PRD。\n';
    return [
      { title: `${label}（巡检报障·PRD 草稿）`, content: prdMsg },
      { title: `${label}（智能客服·澄清开场）`, content: clarifyingMsg },
      { title: `${label}（PRD JSON）`, content: JSON.stringify({ message: prdMsg.trim() }, null, 2) },
    ];
  }

  const isArchitect =
    skills.has('architecture_design') || ['架构师', 'architect'].some((k) => nameL.includes(k));
  if (isArchitect) {
    const archMsg =
      `${taskHint}` +
      '【输入｜精简 PRD 摘要】\n' +
      '目标：现场巡检报障小应用（拍照上报 → 班组长审批 → 派修 → 看板）。\n' +
      '约束：照片不可上公网；希望对接钉钉但暂无 API 文档；6 周试点一个车间。\n\n' +
      '请按架构师职责输出一版可评审的架构草稿：\n' +
      '1. 上下文与假设（标明待确认）；\n' +
      '2. 逻辑架构 + 关键组件职责；\n' +
      '3. 数据流（上报/审批/派修/看板）与存储选型理由；\n' +
      '4. 对外 API 契约草案（3～5 个端点：方法/路径/请求响应要点）；\n' +
      '5. 安全与合规（照片落地、脱敏、内网边界）；\n' +
      '6. 6 周试点的分期切片与风险。\n' +
      '禁止编造未给定的第三方接口细节。';
    const reviewMsg =
      `${taskHint}` +
      '已有一版架构说「全部用公有云对象存储存巡检照片」。\n' +
      '请做架构评审：指出与「照片不可上公网」的冲突，给出 2 套可落地替代方案及取舍。';
    return [
      { title: `${label}（巡检报障·架构草稿）`, content: archMsg },
      { title: `${label}（合规冲突·架构评审）`, content: reviewMsg },
      { title: `${label}（架构 JSON）`, content: JSON.stringify({ message: archMsg.trim() }, null, 2) },
    ];
  }

  // Eval engineer before QA — also binds test_case_generation.
  const isEval =
    skills.has('eval_code_generator') ||
    ['评估工程师', 'eval_engineer'].some((k) => nameL.includes(k));
  if (isEval) {
    const target = 'qa_agent';
    const evalMsg =
      `${taskHint}` +
      '请为已上架 Agent 生成评估代码（Amazon Eval Agent 方法）。\n\n' +
      `target_agent_id: ${target}\n\n` +
      '要求：\n' +
      `1. 读取 \`~/.aiplat/agents/${target}/AGENT.md\` 与最近执行轨迹；\n` +
      '2. 调用技能 eval_code_generator，产出 ≤5 个任务质量指标；\n' +
      `3. 写入 \`~/.aiplat/eval/${target}/eval_metric.py\` 与 \`eval_runner.py\`；\n` +
      '4. scoring_dimensions 已有且合理则不要覆盖；引擎内置 Agent 可跳过；\n' +
      `5. 尽量跑通 \`python eval_runner.py --agent_id=${target}\`（最多 3 轮修复）；\n` +
      '6. 输出：指标列表 + 文件路径 + 试跑结果摘要。\n' +
      '禁止编造不存在的轨迹或库 API。';
    const evalJson = {
      message: '为 Agent 生成评估代码并试跑。已有评分维度合理则勿覆盖。',
      target_agent_id: target,
      max_traces: 5,
    };
    const skipMsg =
      `${taskHint}` +
      'target_agent_id: programmer_agent\n' +
      '该 Agent 若已有合理 scoring_dimensions，请说明并跳过生成；' +
      '若只有维度没有评估代码，则只补 eval_metric.py / eval_runner.py。';
    return [
      { title: `${label}（按 agent_id 评估·qa_agent）`, content: evalMsg },
      { title: `${label}（target_agent_id JSON）`, content: JSON.stringify(evalJson, null, 2) },
      { title: `${label}（已有维度则跳过）`, content: skipMsg },
    ];
  }

  const isQa =
    (skills.has('test_case_generation') ||
      ['测试经理', 'qa_agent', '测试工程师'].some((k) => nameL.includes(k))) &&
    !skills.has('eval_code_generator') &&
    !['评估工程师', 'eval_engineer'].some((k) => nameL.includes(k));
  if (isQa) {
    const qaMsg =
      `${taskHint}` +
      '【被测对象｜巡检报障】能力：工人拍照上报、班组长审批、派修、周看板。\n\n' +
      '请设计可执行的冒烟用例集（不要空话）：\n' +
      '1. 至少 8 条用例：编号 / 前置 / 步骤 / 期望 / 优先级；\n' +
      '2. 覆盖主路径 + 至少 3 条异常（无权限、照片超限、审批驳回）；\n' +
      '3. 另附 3 条接口级用例（若契约未知则标「待契约确认」并写假设）；\n' +
      '4. 给出首轮冒烟的执行顺序（≤15 分钟能跑完）。';
    const agentQa =
      `${taskHint}` +
      '被测 Agent：产品经理（输入自然语言需求 → 输出 PRD Markdown）。\n' +
      '请设计 5 条「Agent 对话」用例，每条含：用户输入样例、期望结构检查点、失败判据。';
    return [
      { title: `${label}（巡检报障·用例集）`, content: qaMsg },
      { title: `${label}（Agent 对话用例）`, content: agentQa },
      { title: `${label}（用例 JSON）`, content: JSON.stringify({ message: qaMsg.trim() }, null, 2) },
    ];
  }

  const isFrontend =
    skills.has('app_page_generation') ||
    ['前端程序员', 'frontend_developer', '前端工程师', 'frontend_engineer'].some((k) =>
      nameL.includes(k),
    );
  if (isFrontend) {
    // Coding FE agent: TypeScript client — not FastAPI/Pydantic (backend sample).
    if (
      skills.has('code_generation') ||
      ['前端工程师', 'frontend_engineer'].some((k) => nameL.includes(k))
    ) {
      const feCode =
        `${taskHint}` +
        '【单独测·可组装切片】本用例测业务模块，不是 Vite 工程。不要生成 package.json / vite.config；不要用能否 `npm run dev` 判断成败。\n\n' +
        '【验收标准】\n' +
        '- 至少 3 个页面：ReportFaultPage / ApproveFaultPage / DispatchRepairPage\n' +
        '- apiClient 覆盖下方每一条 method+path；页面禁止裸 fetch\n' +
        '- types.ts 覆盖契约模型；鉴权标 `// TODO: auth`\n' +
        '- 使用 `## FILE:`；禁止重写 Vite；禁止 Python/FastAPI\n' +
        '- 禁止交付 App.tsx / main.tsx / package.json（那是「有脚手架挂路由」或 scaffold）\n\n' +
        '【输入摘要】\n' +
        '- PRD：巡检报障（上报 / 审批 / 派修）\n' +
        '- 无 project_scaffold（单独测 Agent，不跑研发团队）\n\n' +
        '【api_contracts】\n' +
        '- POST /api/v1/inspection/reports  上报\n' +
        '  body: reporter_id, equipment_id, description, photo_uris[]\n' +
        '  response: { id, status }\n' +
        '- GET  /api/v1/inspection/reports  待审批列表\n' +
        '  item: { id, reporter_id, equipment_id, description, status }\n' +
        '- POST /api/v1/inspection/reports/{id}/approve  审批\n' +
        '  body: approved, comment\n' +
        '  response: { id, status }\n' +
        '- POST /api/v1/inspection/reports/{id}/dispatch 派修\n' +
        '  body: assignee_id\n' +
        '  response: { id, status }\n\n' +
        '请交付：\n' +
        '1. `## FILE: frontend/src/types.ts`\n' +
        '2. `## FILE: frontend/src/api/apiClient.ts`（上列每个 endpoint 一个函数）\n' +
        '3. `## FILE: frontend/src/pages/ReportFaultPage.tsx` 上报\n' +
        '4. `## FILE: frontend/src/pages/ApproveFaultPage.tsx` 审批列表/详情\n' +
        '5. `## FILE: frontend/src/pages/DispatchRepairPage.tsx` 派修\n' +
        '可加 components。缺接口标 BLOCKED，不要编造 path。附成功+失败示例。\n' +
        '调用 code_generation → autoreview → DONE。';
      const feScaffold =
        `${taskHint}` +
        '【单独测·有脚手架时挂路由】假定 Vite 骨架已存在（frontend/src/App.tsx + react-router）。不要重写 package.json。\n\n' +
        '【验收标准】切片同「可组装切片」+ 必须改 App.tsx 挂三页路由。\n' +
        '【api_contracts】\n' +
        '- POST /api/v1/inspection/reports  body: reporter_id, equipment_id, description, photo_uris[]  response: { id, status }\n' +
        '- GET  /api/v1/inspection/reports  item: { id, reporter_id, equipment_id, description, status }\n' +
        '- POST /api/v1/inspection/reports/{id}/approve  body: approved, comment  response: { id, status }\n' +
        '- POST /api/v1/inspection/reports/{id}/dispatch  body: assignee_id  response: { id, status }\n\n' +
        '交付 types.ts + apiClient.ts + 三页 + `## FILE: frontend/src/App.tsx`。\n' +
        '调用 code_generation → autoreview → DONE。';
      const reviewMsg =
        `${taskHint}` +
        '下面伪代码把照片 URL 直接拼到公网 CDN。请指出问题并用最小 diff 思路给出内网存储修正方案（文字即可）。';
      return [
        { title: `${label}（单独测·可组装切片·无脚手架）`, content: feCode },
        { title: `${label}（单独测·有脚手架挂路由）`, content: feScaffold },
        { title: `${label}（安全·代码评审）`, content: reviewMsg },
        { title: `${label}（编码 JSON）`, content: JSON.stringify({ message: feCode.trim() }, null, 2) },
      ];
    }
    const pageMsg =
      `${taskHint}` +
      '【输入】为「巡检报障」Agent 应用生成使用页布局描述（app_page.json 风格）。\n' +
      '角色：一线工人（上报）+ 班组长（审批列表）。\n\n' +
      '请输出：\n' +
      '1. 页面信息架构（路由/区块）；\n' +
      '2. 关键组件与绑定的 Agent/Skill 动作；\n' +
      '3. 一份可粘贴的 JSON 草稿（字段名清晰）；\n' +
      '4. 列出 3 个需产品确认的交互问题。\n' +
      '不要生成完整前端工程代码。';
    return [
      { title: `${label}（巡检报障·页面草稿）`, content: pageMsg },
      { title: `${label}（页面 JSON）`, content: JSON.stringify({ message: pageMsg.trim() }, null, 2) },
    ];
  }

  const isCoder =
    skills.has('code_generation') ||
    ['程序员', 'programmer', '后端开发', 'backend_developer', '后端工程师'].some((k) =>
      nameL.includes(k),
    );
  if (isCoder) {
    const codeMsg =
      `${taskHint}` +
      '【单独测·可组装切片】测 API 模块，不是完整 uvicorn 工程。不要用能否单独启动服务判断成败（工程骨架属 scaffold_agent）。\n\n' +
      '【验收标准】\n' +
      '- 四条契约各一路由：POST/GET /api/v1/inspection/reports，POST .../reports/{id}/approve，POST .../reports/{id}/dispatch\n' +
      '- Pydantic 字段与契约一致；400/404；鉴权 TODO；禁止假对接钉钉\n' +
      '- ## FILE: 切片（routes + schemas）；不要重写 Vite/package.json\n' +
      '- 禁止交付 App.tsx / main.tsx / 完整 uvicorn 工程（属 scaffold_agent）\n\n' +
      '【输入摘要】\n' +
      '- PRD：巡检报障（上报/审批/派修）\n' +
      '- 无 project_scaffold（单独测 Agent）\n\n' +
      '【api_contracts】\n' +
      '- POST /api/v1/inspection/reports  body: reporter_id, equipment_id, description, photo_uris[]  response: { id, status }\n' +
      '- GET  /api/v1/inspection/reports  item: { id, reporter_id, equipment_id, description, status }\n' +
      '- POST /api/v1/inspection/reports/{id}/approve  body: approved, comment  response: { id, status }\n' +
      '- POST /api/v1/inspection/reports/{id}/dispatch  body: assignee_id  response: { id, status }\n\n' +
      '调用 code_generation → autoreview → DONE。';
    const reviewMsg =
      `${taskHint}` +
      '下面伪代码把照片 URL 直接拼到公网 CDN。请指出问题并用最小 diff 思路给出内网存储修正方案（文字即可）。';
    return [
      { title: `${label}（单独测·可组装切片·无脚手架）`, content: codeMsg },
      { title: `${label}（安全·代码评审）`, content: reviewMsg },
      { title: `${label}（编码 JSON）`, content: JSON.stringify({ message: codeMsg.trim() }, null, 2) },
    ];
  }

  const isBrowser =
    skills.has('site_tester') ||
    ((tools.has('browser') || [...skills].some((s) => s === 'browser' || s.endsWith('_browser'))) &&
      !skills.has('last30days'));
  if (isBrowser) {
    const msg =
      `${taskHint}` +
      '请对 https://example.com 做一次可验收冒烟巡检：\n' +
      '1. 打开首页，记录标题与主 CTA 是否可见；\n' +
      '2. 检查控制台是否有明显 JS error（有则摘录）；\n' +
      '3. 输出：通过/失败 + 证据截图或 DOM 要点 + 阻塞项。\n' +
      '不要声称访问了未打开的页面。';
    return [
      { title: `${label}（站点冒烟）`, content: msg },
      {
        title: `${label}（JSON）`,
        content: JSON.stringify({ message: msg.trim(), url: 'https://example.com' }, null, 2),
      },
    ];
  }

  if (skills.has('summarize') || skills.has('summarization')) {
    const article = String(sampleValueForField('message', { type: 'string' }));
    const msg =
      `${taskHint}` +
      '请阅读以下材料并输出结构化摘要（3 条要点 + 1 条风险 + 1 条行动，勿编造原文没有的事实）：\n\n' +
      article;
    return [
      { title: `${label}（长文摘要）`, content: msg },
      { title: `${label}（JSON）`, content: JSON.stringify({ message: msg.trim() }, null, 2) },
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
    `【简单冒烟｜${label}】\n` +
    `角色：你是「${label}」。\n` +
    '- 目标：按本 Agent 职责完成一次最小可交付输出；\n' +
    '- 范围：只做核心路径；明确 1 件「本次不做」；\n' +
    '- 约束：信息不足标「待确认」，禁止编造未提供的事实；\n' +
    '- 验收：输出须含「步骤摘要 + 结果要点 + 1 个风险/阻塞」；禁止只回「已完成/已验证」。\n';
  const complexMsg =
    `${taskHint}` +
    `【复杂冒烟｜${label}】\n` +
    `角色/干系人：一线用户 + 审批/管理者（你以「${label}」身份服务）。\n` +
    '- 场景：现场巡检报障小应用相关任务，需同时考虑主流程与边界；\n' +
    '- 范围：主路径 + 至少 1 个异常分支；明确 2 件「本次不做」；\n' +
    '- 约束：同时覆盖「依赖未就绪（如钉钉 API 未开放）」与「合规（照片不上公网）」；未知标待确认；\n' +
    '- 验收：可复现步骤 + 可对照检查点；禁止「功能正常/清晰可见」；\n' +
    '- 输出：结构化结果（标题/要点/待确认/下一步），勿空话。\n';
  return [
    { title: `${label}（简单·可验收）`, content: msg },
    { title: `${label}（复杂·多约束）`, content: complexMsg },
    { title: `${label}（复杂 JSON）`, content: JSON.stringify({ message: complexMsg.trim() }, null, 2) },
  ];
}
