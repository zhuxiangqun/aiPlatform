import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Badge, Button, Input, Modal, Select, Textarea, toast } from '../ui';
import localSkillSpecV2Schema from '../../schemas/skillSpecV2.schema.json';
import { workspaceSkillApi } from '../../services/coreApi';

type SkillKind = 'rule' | 'executable';

export type SkillWizardV2Value = {
  name: string; // display name in UI (will map to display_name)
  skill_id?: string;
  display_name?: string;
  description: string;
  category: string;
  skill_kind: SkillKind;
  trigger_conditions: string[];
  permissions: string[];
  config: Record<string, unknown>;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  sop: string;
};

const CATEGORY_OPTIONS = [
  { value: 'general', label: '通用' },
  { value: 'execution', label: '执行' },
  { value: 'retrieval', label: '检索' },
  { value: 'analysis', label: '分析' },
  { value: 'generation', label: '生成' },
  { value: 'transformation', label: '转换' },
  { value: 'reasoning', label: '推理' },
  { value: 'coding', label: '编程' },
  { value: 'search', label: '搜索' },
  { value: 'tool', label: '工具' },
  { value: 'communication', label: '通信' },
];

type Schema = any;
const getDefaultSop = (schema: Schema): string => {
  try {
    return String(schema?.properties?.sop?.default || '');
  } catch {
    return '';
  }
};

const getProp = (schema: Schema, k: string): any => {
  try {
    return schema?.properties?.[k];
  } catch {
    return undefined;
  }
};

const getRequiredSet = (schema: Schema): Set<string> => new Set<string>(Array.isArray(schema?.required) ? schema.required : []);

const getOrder = (schema: Schema, k: string): number => {
  try {
    const v = schema?.properties?.[k]?.['x-ui']?.order;
    return typeof v === 'number' ? v : 999;
  } catch {
    return 999;
  }
};

const ensureMarkdownSchema = (out: Record<string, any>) => {
  const o: any = { ...(out || {}) };
  if (!o.markdown) {
    o.markdown = { type: 'string', required: true, description: '面向人阅读的 Markdown 输出，与结构化字段一致' };
  } else {
    o.markdown.type = 'string';
    o.markdown.required = true;
    if (!o.markdown.description) o.markdown.description = '面向人阅读的 Markdown 输出，与结构化字段一致';
  }
  return o;
};

const normalizeSkillId = (s: string) => {
  const t = (s || '').trim().toLowerCase().replace(/\s+/g, '_').replace(/-/g, '_');
  return t.replace(/[^a-z0-9_]/g, '');
};

const yamlLike = (obj: any, indent = 0): string => {
  const sp = '  '.repeat(indent);
  if (obj === null || obj === undefined) return `${sp}null`;
  if (Array.isArray(obj)) {
    if (obj.length === 0) return `${sp}[]`;
    return obj
      .map((it) => {
        if (typeof it === 'object' && it !== null) return `${sp}-\n${yamlLike(it, indent + 1)}`;
        return `${sp}- ${String(it)}`;
      })
      .join('\n');
  }
  if (typeof obj === 'object') {
    const keys = Object.keys(obj);
    if (keys.length === 0) return `${sp}{}`;
    return keys
      .map((k) => {
        const v = (obj as any)[k];
        if (typeof v === 'object' && v !== null) return `${sp}${k}:\n${yamlLike(v, indent + 1)}`;
        return `${sp}${k}: ${String(v)}`;
      })
      .join('\n');
  }
  return `${sp}${String(obj)}`;
};

const unifiedDiff = (a: string, b: string): string => {
  const aLines = String(a || '').split('\n');
  const bLines = String(b || '').split('\n');
  const max = Math.max(aLines.length, bLines.length);
  const out: string[] = [];
  for (let i = 0; i < max; i++) {
    const x = aLines[i];
    const y = bLines[i];
    if (x === y) {
      out.push(` ${x ?? ''}`);
    } else {
      if (x !== undefined) out.push(`-${x}`);
      if (y !== undefined) out.push(`+${y}`);
    }
  }
  return out.join('\n');
};

const stableJson = (obj: any): string => {
  try {
    return JSON.stringify(obj ?? null);
  } catch {
    return String(obj ?? '');
  }
};

const splitFrontmatterBody = (raw: string): { fm: string; body: string } => {
  const t = String(raw || '');
  if (!t.startsWith('---')) return { fm: '', body: t };
  const end = t.indexOf('\n---\n', 3);
  if (end === -1) return { fm: '', body: t };
  return { fm: t.slice(0, end + 5), body: t.slice(end + 5).replace(/^\n+/, '') };
};

const applySopTemplateIfEmpty = (s: string): string => {
  const t = (s || '').trim();
  if (t) return s;
  return '# 概述\n\n## 目标\n\n## 工作流程（SOP）\n\n## 验收清单（Checklist）\n- [ ] \n';
};

const ensureSopSections = (s: string): string => {
  let out = String(s || '');
  const ensure = (title: string, block: string) => {
    if (!out.includes(title)) {
      out = out.replace(/\s*$/, '\n\n' + block.trim() + '\n');
    }
  };
  ensure('## 目标', '## 目标\n\n（待补充）');
  ensure('## 何时使用 / 何时不用', '## 何时使用 / 何时不用\n\n（待补充）');
  ensure('## 输入 / 输出', '## 输入 / 输出\n\n（待补充）');
  ensure('## 工作流程（SOP）', '## 工作流程（SOP）\n\n1. 第一步……\n2. 第二步……\n3. 第三步……');
  ensure('## 异常处理与回滚', '## 异常处理与回滚\n\n（待补充）');
  ensure('## 验收清单（Checklist）', '## 验收清单（Checklist）\n- [ ] \n');
  return out.replace(/^\n+/, '');
};

const recommendSop = (args: { category: string; skillKind: string; name: string; description: string }): string => {
  const { category, skillKind, name, description } = args;
  const nm = (name || '').trim() || '该技能';
  const cat = String(category || 'general');
  const isExec = String(skillKind || 'rule') === 'executable';

  const goal = (description || '').trim()
    ? `帮助用户完成：${(description || '').trim()}`
    : `帮助用户使用「${nm}」完成目标任务，并保证输出契约稳定（JSON+Markdown）。`;

  const flows: Record<string, string[]> = {
    retrieval: [
      '确认检索意图：主题、时间范围、来源偏好（如有）。',
      '制定检索策略：关键词、过滤条件、去重规则。',
      '执行检索并整理证据：记录 sources（URL/标题/时间）。',
      '总结与回答：输出结构化字段 + 可读 Markdown，并在 Markdown 中引用 sources。',
    ],
    execution: [
      '澄清执行目标与影响范围（必要时二次确认）。',
      '生成执行计划（plan）并进行 dry_run（如适用）。',
      '执行工具调用/脚本：按步骤记录关键输入输出（可审计）。',
      '校验结果与回滚策略：失败时给出降级/重试/回滚建议。',
    ],
    analysis: [
      '确认分析目标与口径：数据范围、指标定义、约束条件。',
      '拆解问题并列出假设/不确定性。',
      '给出分析过程与结论：结构化要点 + Markdown 总结。',
      '提出下一步建议与风险提示。',
    ],
    generation: [
      '确认生成目标与风格：受众、语气、长度、格式。',
      '生成初稿并进行自检：一致性、事实性、敏感内容。',
      '给出最终输出：结构化字段 + Markdown 版本（可直接使用）。',
      '可选：提供 1-2 个变体供用户选择。',
    ],
    transformation: [
      '确认输入格式与目标格式（示例优先）。',
      '执行转换/抽取：保证字段对齐与类型稳定。',
      '输出校验：边界情况（空值/异常行/乱码）处理说明。',
      '返回结构化结果 + Markdown 说明与示例。',
    ],
    general: [
      '澄清用户目标与输入信息是否充分。',
      '按 SOP 执行：必要时调用工具/脚本。',
      '输出结构化结果与 Markdown 总结。',
      '提示用户下一步可做的操作。',
    ],
  };
  const flow = flows[cat] || flows.general;

  const execNotes = isExec
    ? '\n\n> 注意：该技能为 executable，请遵循最小权限原则；高风险操作建议启用 require_confirmation=true，并确保可回滚。\n'
    : '';

  return ensureSopSections(
    [
      '# 概述',
      '',
      '## 目标',
      goal,
      '',
      '## 何时使用 / 何时不用',
      `- ✅ 当用户需要使用「${nm}」完成与「${cat}」相关任务时使用。`,
      `- ❌ 当用户缺少关键输入（例如：范围/约束/目标格式）且拒绝补充时，不要盲目执行，先请求补全信息。`,
      '',
      '## 输入 / 输出',
      '- 输入：遵循 input_schema（必要时补充缺失字段）。',
      '- 输出：必须符合 output_schema，并包含 markdown 字段。',
      '',
      '## 工作流程（SOP）',
      ...flow.map((s, i) => `${i + 1}. ${s}`),
      execNotes.trimEnd(),
      '',
      '## 异常处理与回滚',
      '- 如果输入不完整：列出缺失信息并请求用户补充；提供示例。',
      '- 如果工具/脚本失败：给出错误摘要、重试建议、以及降级方案。',
      '- 如果结果不确定：明确不确定性来源，避免编造。',
      '',
      '## 验收清单（Checklist）',
      '- [ ] 输出包含 markdown，且与结构化字段一致',
      '- [ ] 关键步骤有明确说明（可复现/可审计）',
      '- [ ] 对异常情况有降级/重试/回滚说明',
      '',
    ].join('\n')
  );
};

type SopVariant = 'conservative' | 'detailed' | 'compliance';
const recommendSopVariant = (variant: SopVariant, args: { category: string; skillKind: string; name: string; description: string }): string => {
  const base = recommendSop(args);
  if (variant === 'conservative') {
    // Shorter, safer wording; emphasize clarification & uncertainty.
    return ensureSopSections(
      base
        .replace(/可选：提供 1-2 个变体供用户选择。/g, '如不确定，先询问用户补充信息再生成结果。')
        .replace(/执行工具调用\/脚本：按步骤记录关键输入输出（可审计）。/g, '执行前先 dry_run（如适用）；执行中记录关键输入输出（可审计）。')
        .replace(/明确不确定性来源，避免编造。/g, '明确不确定性来源；无法确认的内容不要编造。')
    );
  }
  if (variant === 'compliance') {
    // Add governance/compliance section (trustworthy).
    const extra =
      '\n\n## 治理与合规（Governance）\n' +
      '- 权限最小化：仅声明完成任务所需 permissions。\n' +
      '- 高风险操作：启用 require_confirmation=true；记录关键输入输出；支持回滚。\n' +
      '- 数据处理：避免在输出中暴露敏感信息；必要时脱敏/聚合。\n' +
      '- 引用与溯源：检索型技能必须提供 sources，并在 markdown 中引用。\n';
    return ensureSopSections(base + extra);
  }
  // detailed: more step granularity
  const more =
    '\n\n## 细化步骤（Detailed Steps）\n' +
    '1. 解析用户输入 → 映射到 input_schema（缺失字段列出并请求补全）。\n' +
    '2. 生成执行/检索计划（plan），如果存在高风险动作先请求确认。\n' +
    '3. 分步执行并记录中间结果；遇到错误先降级再重试。\n' +
    '4. 结构化输出（JSON）→ 同步生成 markdown（保持一致）。\n' +
    '5. 最终自检：schema 校验、关键结论核对、异常说明齐全。\n';
  return ensureSopSections(base + more);
};

type MdSections = {
  preamble: string; // content before first "## "
  order: string[]; // headings in appearance order
  sections: Record<string, string>; // heading -> content (without heading line)
};

const parseMdSections = (text: string): MdSections => {
  const lines = String(text || '').split('\n');
  const sections: Record<string, string> = {};
  const order: string[] = [];
  let preambleLines: string[] = [];
  let curTitle: string | null = null;
  let curBuf: string[] = [];

  const flush = () => {
    if (!curTitle) return;
    sections[curTitle] = curBuf.join('\n').replace(/^\n+/, '').replace(/\n+$/, '') + '\n';
    curBuf = [];
  };

  for (const line of lines) {
    if (line.startsWith('## ')) {
      flush();
      curTitle = line.slice(3).trim() || '(无标题)';
      if (!order.includes(curTitle)) order.push(curTitle);
      continue;
    }
    if (!curTitle) preambleLines.push(line);
    else curBuf.push(line);
  }
  flush();

  return {
    preamble: preambleLines.join('\n').replace(/\n+$/, '') + '\n',
    order,
    sections,
  };
};

const mergeMdSections = (current: string, recommended: string, selected: Set<string>): string => {
  const cur = parseMdSections(current);
  const rec = parseMdSections(recommended);

  const out: string[] = [];
  // preamble
  out.push((selected.has('__preamble__') ? rec.preamble : cur.preamble).replace(/\n+$/, ''));

  // sections in current order first
  for (const title of cur.order) {
    const body = selected.has(title) ? rec.sections[title] ?? cur.sections[title] : cur.sections[title];
    out.push(`## ${title}`);
    out.push((body || '').replace(/\n+$/, ''));
  }

  // append selected sections that exist only in recommended
  for (const title of rec.order) {
    if (cur.sections[title] !== undefined) continue;
    if (!selected.has(title)) continue;
    out.push(`## ${title}`);
    out.push((rec.sections[title] || '').replace(/\n+$/, ''));
  }

  return out.join('\n\n').replace(/\n{3,}/g, '\n\n').replace(/^\n+/, '') + '\n';
};

export interface SkillWizardV2ModalProps {
  open: boolean;
  initial?: Partial<SkillWizardV2Value>;
  onClose: () => void;
  onApply: (v: SkillWizardV2Value) => void;
}

const SkillWizardV2Modal: React.FC<SkillWizardV2ModalProps> = ({ open, initial, onClose, onApply }) => {
  const [step, setStep] = useState(0);
  const [remoteSchema, setRemoteSchema] = useState<any>(null);
  const [schemaVersion, setSchemaVersion] = useState<string>('');
  const [schemaLoading, setSchemaLoading] = useState(false);
  const [schemaSource, setSchemaSource] = useState<'remote' | 'cache' | 'local'>('local');
  const [schemaNewVersion, setSchemaNewVersion] = useState<string>('');

  const activeSchema: any = remoteSchema || (localSkillSpecV2Schema as any);

  const [name, setName] = useState(initial?.name || '');
  const [skillId, setSkillId] = useState(initial?.skill_id || '');
  const [displayName, setDisplayName] = useState(initial?.display_name || '');
  const [description, setDescription] = useState(initial?.description || '');
  const [category, setCategory] = useState(initial?.category || 'general');
  const [skillKind, setSkillKind] = useState<SkillKind>(initial?.skill_kind || 'rule');
  const [triggerText, setTriggerText] = useState((initial?.trigger_conditions || []).join('\n'));
  const [permissionsText, setPermissionsText] = useState(JSON.stringify(initial?.permissions || ['llm:generate'], null, 0));

  const [configText, setConfigText] = useState(JSON.stringify(initial?.config || {}, null, 2));
  const [inputSchemaText, setInputSchemaText] = useState(JSON.stringify(initial?.input_schema || {}, null, 2));
  const [outputSchemaText, setOutputSchemaText] = useState(JSON.stringify(ensureMarkdownSchema(initial?.output_schema || {}), null, 2));

  const [sopText, setSopText] = useState(ensureSopSections((initial?.sop || getDefaultSop(localSkillSpecV2Schema as any) || '').trim()));
  const [previewOpen, setPreviewOpen] = useState(false);
  const [diffOpen, setDiffOpen] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [govPreview, setGovPreview] = useState<any>(null);
  const [govLoading, setGovLoading] = useState(false);
  const [customPerm, setCustomPerm] = useState('');
  const [selectedPerm, setSelectedPerm] = useState<string>('llm:generate');
  const [permCatalog, setPermCatalog] = useState<any[] | null>(null);
  const [permCatalogLoading, setPermCatalogLoading] = useState(false);
  const [permCatalogVersion, setPermCatalogVersion] = useState<string>('');
  const [permCatalogSource, setPermCatalogSource] = useState<'remote' | 'cache' | 'local'>('local');
  const [permCatalogNewVersion, setPermCatalogNewVersion] = useState<string>('');
  const [sopSuggestOpen, setSopSuggestOpen] = useState(false);
  const [sopSuggestTitle, setSopSuggestTitle] = useState('');
  const [sopSuggestText, setSopSuggestText] = useState('');
  const [sopSelected, setSopSelected] = useState<Record<string, boolean>>({});

  const steps = useMemo(() => ['基础信息', '治理与触发', '输入输出契约', 'SOP（可精修）', '预览与生成'], []);

  const required = useMemo(() => getRequiredSet(activeSchema), [activeSchema]);

  useEffect(() => {
    if (!open) return;
    if (schemaLoading) return;

    const tenantId = (() => {
      try {
        return localStorage.getItem('active_tenant_id') || 'default';
      } catch {
        return 'default';
      }
    })();
    const channel = 'stable';
    const cacheKey = `skillSpecV2Schema:${tenantId}:${channel}`;

    if (!remoteSchema) {
      // 1) load cache immediately (fast path)
      try {
        const raw = localStorage.getItem(cacheKey);
        if (raw) {
          const obj = JSON.parse(raw);
          if (obj?.schema && obj?.version) {
            setRemoteSchema(obj.schema);
            setSchemaVersion(String(obj.version));
            setSchemaSource('cache');
          }
        }
      } catch {
        // ignore
      }
    }

    (async () => {
      try {
        setSchemaLoading(true);
        const res = await workspaceSkillApi.skillSpecV2Schema();
        const sc = (res as any)?.schema;
        const ver = String((res as any)?.version || '');
        if (sc && typeof sc === 'object') {
          // If version changed, show update hint (do not break user flow)
          const curVer = schemaVersion || '';
          if (curVer && ver && curVer !== ver) setSchemaNewVersion(ver);
          setRemoteSchema(sc);
          setSchemaVersion(ver);
          setSchemaSource('remote');
          try {
            localStorage.setItem(cacheKey, JSON.stringify({ version: ver, schema: sc, fetched_at: Date.now() }));
          } catch {
            // ignore
          }
          // only fill sop if empty (don't overwrite user input)
          if (!(sopText || '').trim()) {
            const sopDef = getDefaultSop(sc) || getDefaultSop(localSkillSpecV2Schema as any);
            if (sopDef) setSopText(ensureSopSections(sopDef));
          }
        }
      } catch {
        // ignore, fallback to local schema
        if (!remoteSchema) setSchemaSource('local');
      } finally {
        setSchemaLoading(false);
      }
    })();
  }, [open]);

  const validateStep = (): boolean => {
    if (step === 0) {
      if (!name.trim()) return toast.error('请填写名称（显示名称）'), false;
      const minDesc = Number(getProp(activeSchema, 'description')?.minLength || 0) || 0;
      if (minDesc > 0 && (description || '').trim().length < minDesc) return toast.error(`描述建议至少 ${minDesc} 个字（用于路由与可解释性）`), false;
      return true;
    }
    if (step === 1) {
      if (skillKind === 'executable') {
        const p = (permissionsText || '').trim();
        if (!p) return toast.error('executable 技能必须声明 permissions'), false;
      }
      return true;
    }
    if (step === 2) {
      try {
        JSON.parse(inputSchemaText || '{}');
      } catch {
        return toast.error('input_schema JSON 格式错误'), false;
      }
      try {
        const out = ensureMarkdownSchema(JSON.parse(outputSchemaText || '{}'));
        setOutputSchemaText(JSON.stringify(out, null, 2));
      } catch {
        return toast.error('output_schema JSON 格式错误'), false;
      }
      return true;
    }
    if (step === 3) {
      if (!(sopText || '').trim()) {
        setSopText(ensureSopSections(getDefaultSop(activeSchema)));
      }
      return true;
    }
    return true;
  };

  const toValue = (): SkillWizardV2Value => {
    const trigger_conditions = (triggerText || '')
      .split('\n')
      .map((x) => x.trim())
      .filter(Boolean);

    let permissions: string[] = [];
    try {
      const v = JSON.parse(permissionsText || '[]');
      permissions = Array.isArray(v) ? v.map((x) => String(x)).filter((x) => x.trim()) : [];
    } catch {
      permissions = (permissionsText || '')
        .split(/[\n,]/g)
        .map((x) => x.trim())
        .filter(Boolean);
    }

    const config = JSON.parse(configText || '{}');
    const input_schema = JSON.parse(inputSchemaText || '{}');
    const output_schema = ensureMarkdownSchema(JSON.parse(outputSchemaText || '{}'));

    return {
      name: name.trim(),
      skill_id: skillId.trim() || undefined,
      display_name: (displayName.trim() || name.trim()) || undefined,
      description: (description || '').trim(),
      category,
      skill_kind: skillKind,
      trigger_conditions,
      permissions,
      config,
      input_schema,
      output_schema,
      sop: ensureSopSections(sopText || ''),
    };
  };

  // Real-time governance hint: front-end heuristic + server preview (approval rules).
  const localRisk = useMemo(() => {
    const txt = (permissionsText || '').toLowerCase();
    if (txt.includes('tool:run_command') || txt.includes('tool:workspace_fs_write') || txt.includes('tool:file_operations') || txt.includes('database')) return 'high';
    if (txt.includes('webfetch') || txt.includes('websearch') || txt.includes('tool:') || txt.includes('mcp:')) return 'medium';
    return skillKind === 'executable' ? 'medium' : 'low';
  }, [permissionsText, skillKind]);

  useEffect(() => {
    if (!open) return;
    // only meaningful when on governance step or later
    if (step < 1) return;
    const timer = setTimeout(async () => {
      try {
        setGovLoading(true);
        // best-effort parse permissions
        let permissions: string[] = [];
        try {
          const v = JSON.parse(permissionsText || '[]');
          permissions = Array.isArray(v) ? v.map((x) => String(x)) : [];
        } catch {
          permissions = (permissionsText || '')
            .split(/[\n,]/g)
            .map((x) => x.trim())
            .filter(Boolean);
        }
        let config: any = {};
        try {
          config = JSON.parse(configText || '{}');
        } catch {
          config = {};
        }
        const res = await workspaceSkillApi.governancePreview({
          skill_kind: skillKind,
          permissions,
          config,
          tenant_id: 'ops',
          actor_id: 'admin',
          session_id: 'wizard',
        });
        setGovPreview(res);
      } catch {
        setGovPreview(null);
      } finally {
        setGovLoading(false);
      }
    }, 450);
    return () => clearTimeout(timer);
  }, [open, step, skillKind, permissionsText, configText]);

  useEffect(() => {
    if (!open) return;
    if (step < 1) return;
    if (permCatalogLoading) return;
    if (permCatalog && permCatalog.length > 0) return;
    const tenantId = (() => {
      try {
        return localStorage.getItem('active_tenant_id') || 'default';
      } catch {
        return 'default';
      }
    })();
    const channel = 'stable';
    const cacheKey = `permissionsCatalog:${tenantId}:${channel}`;

    // 1) cache fast path
    try {
      const raw = localStorage.getItem(cacheKey);
      if (raw) {
        const obj = JSON.parse(raw);
        if (Array.isArray(obj?.items)) {
          setPermCatalog(obj.items);
          setPermCatalogVersion(String(obj.version || ''));
          setPermCatalogSource('cache');
        }
      }
    } catch {
      // ignore
    }
    (async () => {
      try {
        setPermCatalogLoading(true);
        const res = await workspaceSkillApi.permissionsCatalog();
        const items = Array.isArray((res as any)?.items) ? (res as any).items : [];
        const ver = String((res as any)?.version || '');
        setPermCatalog(items);
        setPermCatalogVersion(ver);
        setPermCatalogSource('remote');
        const curVer = permCatalogVersion || '';
        if (curVer && ver && curVer !== ver) setPermCatalogNewVersion(ver);
        try {
          localStorage.setItem(cacheKey, JSON.stringify({ version: ver, items, fetched_at: Date.now() }));
        } catch {
          // ignore
        }
      } catch {
        setPermCatalog(null);
        if (!permCatalog) setPermCatalogSource('local');
      } finally {
        setPermCatalogLoading(false);
      }
    })();
  }, [open, step]);

  const applyTriggerRecommendations = () => {
    const nm = (name || '').trim();
    const verbsByCat: Record<string, string[]> = {
      retrieval: ['帮我查', '帮我检索', '搜索', '查一下'],
      execution: ['帮我执行', '帮我创建', '帮我更新', '帮我删除'],
      analysis: ['分析', '总结', '提取要点', '对比'],
      generation: ['帮我写', '生成', '润色', '改写'],
      transformation: ['转换', '抽取', '格式化', '解析'],
      general: ['帮我', '使用', '处理'],
    };
    const verbs = verbsByCat[category] || verbsByCat.general;
    const cand = [
      nm,
      nm ? `使用${nm}` : '',
      nm ? `帮我用${nm}` : '',
      ...verbs.map((v) => (nm ? `${v}${nm}` : v)),
      ...verbs.map((v) => v),
    ]
      .map((x) => String(x || '').trim())
      .filter(Boolean);
    const uniq: string[] = [];
    for (const x of cand) if (!uniq.includes(x)) uniq.push(x);
    setTriggerText(uniq.slice(0, 10).join('\n'));
    toast.success('已生成触发词推荐');
  };

  const parsePermissions = (): string[] => {
    try {
      const v = JSON.parse(permissionsText || '[]');
      return Array.isArray(v) ? v.map((x) => String(x)).filter((x) => x.trim()) : [];
    } catch {
      return (permissionsText || '')
        .split(/[\n,]/g)
        .map((x) => x.trim())
        .filter(Boolean);
    }
  };

  const setPermissionsArray = (arr: string[]) => {
    const uniq: string[] = [];
    for (const x of arr.map((s) => String(s).trim()).filter(Boolean)) if (!uniq.includes(x)) uniq.push(x);
    setPermissionsText(JSON.stringify(uniq, null, 0));
  };

  const openSopSuggestion = (title: string, txt: string) => {
    const cur = parseMdSections(sopText || '');
    const rec = parseMdSections(txt || '');
    const allTitles = Array.from(new Set<string>(['__preamble__', ...cur.order, ...rec.order]));
    const next: Record<string, boolean> = {};
    for (const t of allTitles) next[t] = true; // default apply-all (user can uncheck)
    setSopSelected(next);
    setSopSuggestTitle(title);
    setSopSuggestText(txt);
    setSopSuggestOpen(true);
  };

  const baselineValue = (): SkillWizardV2Value => {
    // Baseline for diff:
    // - prefer initial values
    // - otherwise use schema defaults where available
    const defPerm = (() => {
      try {
        const p = getProp(activeSchema, 'permissions')?.default;
        return Array.isArray(p) ? p.map((x: any) => String(x)) : ['llm:generate'];
      } catch {
        return ['llm:generate'];
      }
    })();
    const defKind = (getProp(activeSchema, 'skill_kind')?.default as SkillKind) || 'rule';
    const defCat = (getProp(activeSchema, 'category')?.enum?.[0] as string) || 'general';
    const defOut = (() => {
      try {
        return ensureMarkdownSchema(getProp(activeSchema, 'output_schema')?.default || {});
      } catch {
        return ensureMarkdownSchema({});
      }
    })();

    const nm = (initial?.name || '').trim();
    const desc = (initial?.description || '').trim();
    const cat = String(initial?.category || defCat);
    const kind = (initial?.skill_kind as SkillKind) || defKind;
    const trig = initial?.trigger_conditions || [];
    const perm = initial?.permissions || defPerm;
    const cfg = initial?.config || {};
    const ins = initial?.input_schema || {};
    const outs = ensureMarkdownSchema(initial?.output_schema || defOut);
    const sop = ensureSopSections(applySopTemplateIfEmpty(initial?.sop || getDefaultSop(activeSchema)));
    return {
      name: nm || '',
      skill_id: initial?.skill_id,
      display_name: initial?.display_name,
      description: desc || '',
      category: cat,
      skill_kind: kind,
      trigger_conditions: trig,
      permissions: perm,
      config: cfg,
      input_schema: ins,
      output_schema: outs,
      sop,
    };
  };

  const buildSkillMdPreview = (v: SkillWizardV2Value): string => {
    const fmObj: any = {
      name: (v.skill_id || '').trim() || normalizeSkillId(v.name),
      display_name: v.display_name || v.name,
      description: v.description,
      category: v.category,
      status: 'enabled',
      skill_kind: v.skill_kind,
      trigger_conditions: v.trigger_conditions,
      permissions: v.permissions,
      input_schema: v.input_schema,
      output_schema: v.output_schema,
    };
    const header = yamlLike(fmObj, 0);
    const body = v.sop || '';
    return `---\n${header}\n---\n\n${body.replace(/^\n+/, '')}`.replace(/\n{3,}/g, '\n\n');
  };

  const renderField = (key: string) => {
    const p = getProp(activeSchema, key) || {};
    const isReq = required.has(key);
    const title = String(p.title || key) + (isReq ? ' *' : '');
    const help = String(p?.['x-ui']?.help || '');
    const placeholder = String(p?.['x-ui']?.placeholder || '');
    const widget = String(p?.['x-ui']?.widget || '');

    if (key === 'category') {
      return <Select label={title} value={category} onChange={(v: string) => setCategory(v)} options={CATEGORY_OPTIONS} />;
    }
    if (key === 'skill_kind') {
      return (
        <Select
          label={title}
          value={skillKind}
          onChange={(v: string) => setSkillKind(v as any)}
          options={[
            { value: 'rule', label: 'rule（纯 SOP）' },
            { value: 'executable', label: 'executable（可执行/需权限）' },
          ]}
        />
      );
    }
    if (key === 'trigger_conditions') {
      return (
        <div>
          <Textarea label={title} rows={5} value={triggerText} onChange={(e: any) => setTriggerText(e.target.value)} placeholder={placeholder || '每行一条'} />
          {help && <div className="text-xs text-gray-500 mt-1">{help}</div>}
        </div>
      );
    }
    if (key === 'permissions') {
      const PRESET: Array<{ value: string; label: string; risk: 'low' | 'medium' | 'high'; desc: string; defaultSelected?: boolean }> =
        Array.isArray(permCatalog) && permCatalog.length > 0
          ? permCatalog.map((it: any) => ({
              value: String(it.permission || it.value || ''),
              label: String(it.label || it.permission || it.value || ''),
              risk: (String(it.risk_level || 'low') as any) || 'low',
              desc: String(it.description || ''),
              defaultSelected: Boolean(it.default_selected),
            }))
          : [
              { value: 'llm:generate', label: 'llm:generate', risk: 'low', desc: '模型生成能力（常规）', defaultSelected: true },
              { value: 'tool:websearch', label: 'tool:websearch', risk: 'medium', desc: '联网搜索（外部信息）' },
              { value: 'tool:webfetch', label: 'tool:webfetch', risk: 'medium', desc: '网页抓取（外部内容）' },
              { value: 'tool:run_command', label: 'tool:run_command', risk: 'high', desc: '执行命令（高风险）' },
              { value: 'tool:workspace_fs_write', label: 'tool:workspace_fs_write', risk: 'high', desc: '写入文件（高风险）' },
            ];
      const cur = new Set(parsePermissions());
      const toggle = (v: string) => {
        const next = new Set(cur);
        if (next.has(v)) next.delete(v);
        else next.add(v);
        setPermissionsArray(Array.from(next));
        setSelectedPerm(v);
      };
      const riskBadge = (r: string) => (r === 'high' ? 'error' : r === 'medium' ? 'warning' : 'success');
      const risk = String(govPreview?.risk_level || localRisk);
      const approvalRequired = Boolean(govPreview?.approval?.required);
      const requiresConfirmation = Boolean(govPreview?.requires_confirmation);
      const impacts: string[] = [];
      if (approvalRequired) impacts.push(`命中审批规则：${govPreview?.approval?.matched_rule_name || '需要审批'}`);
      if (requiresConfirmation) impacts.push('建议/需要二次确认（require_confirmation=true）');
      if (Array.isArray(govPreview?.hints) && govPreview.hints.length > 0) impacts.push(...govPreview.hints.slice(0, 3));
      const suggestionFor = (p: string): string | null => {
        const pl = p.toLowerCase();
        if (pl === 'tool:run_command') return '建议优先用更窄的专用工具/脚本替代通用命令执行，或仅允许只读命令。';
        if (pl === 'tool:workspace_fs_write') return '建议限制写入目录/文件类型，并启用二次确认与回滚（保留 revisions）。';
        if (pl === 'tool:webfetch' || pl === 'tool:websearch') return '建议输出中附带 sources，并说明时间/来源范围，避免幻觉。';
        return null;
      };

      const selectedInfo = (() => {
        const p = String(selectedPerm || '').trim();
        const hit = PRESET.find((x) => x.value === p);
        const server = (govPreview?.permission_details && p && govPreview.permission_details[p]) || null;
        const risk0: string =
          String(server?.risk_level || '') ||
          hit?.risk ||
          (p.toLowerCase().includes('run_command') || p.toLowerCase().includes('workspace') || p.toLowerCase().includes('database')
            ? 'high'
            : p.toLowerCase().startsWith('tool:') || p.toLowerCase().startsWith('mcp:')
              ? 'medium'
              : 'low');
        const desc0 = String(server?.description || '') || hit?.desc || '自定义权限';
        const suggest0 = (Array.isArray(server?.suggestions) && server.suggestions.length > 0 ? server.suggestions.join('；') : null) || suggestionFor(p);
        const category0 = String(server?.category || '');
        const ops0 = Array.isArray(server?.implied_operations) ? server.implied_operations : [];
        return { p, risk0, desc0, suggest0, category0, ops0 };
      })();

      return (
        <div className="space-y-2">
          <div className="text-sm font-medium text-gray-300">{title}</div>
          {permCatalogLoading && <div className="text-xs text-gray-500">正在加载权限目录…</div>}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {/* left: selector */}
            <div className="space-y-2">
              {PRESET.map((p0) => (
                <label
                  key={p0.value}
                  className={`flex items-center justify-between gap-3 bg-dark-card border rounded-lg px-3 py-2 cursor-pointer ${
                    selectedPerm === p0.value ? 'border-blue-500' : 'border-dark-border'
                  }`}
                  onClick={() => setSelectedPerm(p0.value)}
                >
                  <div className="flex items-center gap-2">
                    <input type="checkbox" checked={cur.has(p0.value)} onChange={() => toggle(p0.value)} onClick={(e) => e.stopPropagation()} />
                    <code className="text-gray-200">{p0.label}</code>
                    <Badge variant={riskBadge(p0.risk) as any}>{p0.risk}</Badge>
                  </div>
                  <div className="text-xs text-gray-500">{p0.desc}</div>
                </label>
              ))}

              <div className="flex items-end gap-2">
                <Input
                  label="自定义权限（可选）"
                  value={customPerm}
                  onChange={(e: any) => setCustomPerm(e.target.value)}
                  placeholder="例如：mcp:github 或 tool:database"
                />
                <Button
                  variant="secondary"
                  onClick={() => {
                    const v = String(customPerm || '').trim();
                    if (!v) return;
                    setPermissionsArray([...Array.from(cur), v]);
                    setSelectedPerm(v);
                    setCustomPerm('');
                    toast.success('已添加权限');
                  }}
                >
                  添加
                </Button>
              </div>

              <Textarea
                label="（高级）permissions 原始 JSON"
                rows={3}
                value={permissionsText}
                onChange={(e: any) => setPermissionsText(e.target.value)}
                placeholder={placeholder || '["llm:generate"]'}
              />
              {help && <div className="text-xs text-gray-500 mt-1">{help}</div>}
            </div>

            {/* right: impact panel */}
            <div className="space-y-2">
              <Alert
                type={(selectedInfo.risk0 === 'high' ? 'warning' : selectedInfo.risk0 === 'medium' ? 'info' : 'success') as any}
                title={`权限说明：${selectedInfo.p || '(未选择)'}（risk=${selectedInfo.risk0}）`}
              >
                <div className="space-y-1">
                  <div className="text-sm">{selectedInfo.desc0}</div>
                  {selectedInfo.category0 && <div className="text-xs text-gray-500">类别：{selectedInfo.category0}</div>}
                  {selectedInfo.ops0 && selectedInfo.ops0.length > 0 && <div className="text-xs text-gray-500">可能触发 operation：{selectedInfo.ops0.join(', ')}</div>}
                  {selectedInfo.suggest0 && <div className="text-xs text-gray-500">建议：{selectedInfo.suggest0}</div>}
                </div>
              </Alert>

              <Alert type={(risk === 'high' ? 'warning' : risk === 'medium' ? 'info' : 'success') as any} title={`组合影响（risk=${risk}${govLoading ? ' · 检查中…' : ''}）`}>
                <div className="space-y-1">
                  {impacts.length > 0 ? impacts.map((t: string, i: number) => <div key={i} className="text-sm">{t}</div>) : <div className="text-sm">当前权限组合风险较低。</div>}
                  {(approvalRequired || requiresConfirmation) && (
                    <div className="text-xs text-gray-500">
                      {approvalRequired ? '建议走审批或降低权限范围；' : ''}
                      {requiresConfirmation ? '建议开启 require_confirmation=true。' : ''}
                    </div>
                  )}
                </div>
              </Alert>
            </div>
          </div>
        </div>
      );
    }
    if (key === 'config') return <Textarea label={title} rows={6} value={configText} onChange={(e: any) => setConfigText(e.target.value)} placeholder={placeholder || '{}'} />;
    if (key === 'input_schema') return <Textarea label={title} rows={10} value={inputSchemaText} onChange={(e: any) => setInputSchemaText(e.target.value)} placeholder={placeholder || '{}'} />;
    if (key === 'output_schema') {
      return (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <div className="text-sm font-medium text-gray-300">{title}</div>
            <Button
              variant="secondary"
              onClick={() => {
                try {
                  const out = ensureMarkdownSchema(JSON.parse(outputSchemaText || '{}'));
                  setOutputSchemaText(JSON.stringify(out, null, 2));
                  toast.success('已补齐 markdown 输出字段');
                } catch {
                  toast.error('output_schema JSON 格式错误');
                }
              }}
            >
              一键补齐 markdown
            </Button>
          </div>
          <Textarea rows={10} value={outputSchemaText} onChange={(e: any) => setOutputSchemaText(e.target.value)} placeholder={placeholder || '{}'} />
          {help && <div className="text-xs text-gray-500">{help}</div>}
          <div className="text-xs text-gray-500">
            说明：平台强约束 output_schema 必须包含 <code>markdown</code> 字段（JSON+Markdown 输出）。
          </div>
        </div>
      );
    }
    if (key === 'sop') {
      return (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <Button variant="secondary" onClick={() => setSopText(ensureSopSections(sopText))}>
              补齐章节模板
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setSopText(
                  recommendSop({
                    category,
                    skillKind,
                    name: displayName || name,
                    description,
                  })
                );
                toast.success('已生成 SOP 推荐');
              }}
            >
              一键生成 SOP（推荐）
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                const txt = recommendSopVariant('conservative', { category, skillKind, name: displayName || name, description });
                openSopSuggestion('SOP 推荐：保守版', txt);
              }}
            >
              保守版
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                const txt = recommendSopVariant('detailed', { category, skillKind, name: displayName || name, description });
                openSopSuggestion('SOP 推荐：详细版', txt);
              }}
            >
              详细版
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                const txt = recommendSopVariant('compliance', { category, skillKind, name: displayName || name, description });
                openSopSuggestion('SOP 推荐：合规版', txt);
              }}
            >
              合规版
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                const sopDef = getDefaultSop(activeSchema) || getDefaultSop(localSkillSpecV2Schema as any) || '';
                setSopText(ensureSopSections(sopDef));
              }}
            >
              使用默认 SOP 模板
            </Button>
          </div>
          <Textarea label={title} rows={18} value={sopText} onChange={(e: any) => setSopText(e.target.value)} />
          {help && <div className="text-xs text-gray-500">{help}</div>}

          <Modal
            open={sopSuggestOpen}
            onClose={() => setSopSuggestOpen(false)}
            title={sopSuggestTitle || 'SOP 推荐'}
            width={980}
            footer={
              <>
                <Button variant="secondary" onClick={() => setSopSuggestOpen(false)}>
                  关闭
                </Button>
                <Button
                  variant="secondary"
                  onClick={async () => {
                    try {
                      await navigator.clipboard.writeText(sopSuggestText || '');
                      toast.success('已复制 SOP 推荐');
                    } catch {
                      toast.error('复制失败');
                    }
                  }}
                  disabled={!sopSuggestText}
                >
                  复制推荐
                </Button>
                <Button
                  variant="primary"
                  onClick={() => {
                    const selected = new Set<string>(Object.entries(sopSelected).filter(([, v]) => v).map(([k]) => k));
                    // allow preamble selection
                    const merged = mergeMdSections(sopText || '', sopSuggestText || '', selected);
                    setSopText(ensureSopSections(merged));
                    setSopSuggestOpen(false);
                    toast.success('已按所选章节应用 SOP 推荐');
                  }}
                  disabled={!sopSuggestText}
                >
                  按所选章节应用
                </Button>
              </>
            }
          >
            <div className="space-y-3">
              {(() => {
                const cur = parseMdSections(sopText || '');
                const rec = parseMdSections(sopSuggestText || '');
                const allTitles = Array.from(new Set<string>(['__preamble__', ...cur.order, ...rec.order]));
                const selected = new Set<string>(Object.entries(sopSelected).filter(([, v]) => v).map(([k]) => k));
                const merged = mergeMdSections(sopText || '', sopSuggestText || '', selected);
                const diff = unifiedDiff(sopText || '', merged);
                return (
                  <>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <div className="space-y-2">
                        <div className="text-sm font-medium text-gray-300">选择要应用的章节</div>
                        <label className="flex items-center gap-2 text-sm text-gray-300">
                          <input
                            type="checkbox"
                            checked={allTitles.every((t) => Boolean(sopSelected[t]))}
                            onChange={(e) => {
                              const on = Boolean((e.target as any).checked);
                              const next: Record<string, boolean> = {};
                              for (const t of allTitles) next[t] = on;
                              setSopSelected(next);
                            }}
                          />
                          全选
                        </label>
                        <div className="max-h-[280px] overflow-auto space-y-1 border border-dark-border rounded-lg p-2">
                          {allTitles
                            .filter((t) => t !== '(无标题)')
                            .map((t) => (
                              <label key={t} className="flex items-center gap-2 text-sm text-gray-300">
                                <input
                                  type="checkbox"
                                  checked={Boolean(sopSelected[t])}
                                  onChange={(e) => setSopSelected((p) => ({ ...(p || {}), [t]: Boolean((e.target as any).checked) }))}
                                />
                                <span className="truncate">{t === '__preamble__' ? '（前言/概述区）' : t}</span>
                              </label>
                            ))}
                        </div>
                        <div className="text-xs text-gray-500">说明：将把所选章节从推荐稿合并到当前 SOP（未选章节保持不变）。</div>
                      </div>
                      <div className="space-y-2">
                        <Textarea label="推荐文本（只读）" rows={12} value={sopSuggestText} readOnly />
                      </div>
                    </div>
                    <Textarea label="应用后 Diff（基于所选章节）" rows={14} value={diff} readOnly />
                  </>
                );
              })()}
              <div className="text-xs text-gray-500">说明：先预览与 Diff 对比，再决定是否应用。</div>
            </div>
          </Modal>
        </div>
      );
    }
    if (key === 'name') return <Input label={title} value={name} onChange={(e: any) => setName(e.target.value)} placeholder={placeholder} />;
    if (key === 'skill_id') return <Input label={title} value={skillId} onChange={(e: any) => setSkillId(e.target.value)} placeholder={placeholder} />;
    if (key === 'display_name') return <Input label={title} value={displayName} onChange={(e: any) => setDisplayName(e.target.value)} placeholder={placeholder} />;
    if (key === 'description') return <Textarea label={title} rows={3} value={description} onChange={(e: any) => setDescription(e.target.value)} placeholder={placeholder} />;

    // fallback
    if (widget === 'json' || p.type === 'object') return <Textarea label={title} rows={8} value={''} readOnly />;
    return <Input label={title} value={''} readOnly />;
  };

  const content = () => {
    // Schema-driven step fields (x-ui.step + x-ui.advanced)
    const stepFields: Record<number, { basic: string[]; advanced?: string[]; intro?: string }> = {};
    const props = (activeSchema?.properties && typeof activeSchema.properties === 'object') ? activeSchema.properties : {};
    for (const k of Object.keys(props)) {
      const ui = props?.[k]?.['x-ui'] || {};
      const st = typeof ui.step === 'number' ? ui.step : undefined;
      if (typeof st !== 'number') continue;
      stepFields[st] = stepFields[st] || { basic: [], advanced: [] };
      if (ui.advanced) stepFields[st].advanced!.push(k);
      else stepFields[st].basic.push(k);
    }
    if (!stepFields[1]?.intro) stepFields[1] = { ...(stepFields[1] || { basic: [], advanced: [] }), intro: '先明确“形态/治理边界”，再填触发与权限；executable 将触发更严格的权限校验与门控。' };
    if (stepFields[step]) {
      const def = stepFields[step];
      const ordered = (xs: string[]) => [...xs].sort((a, b) => getOrder(activeSchema, a) - getOrder(activeSchema, b));
      const basic = ordered(def.basic as any);
      const adv = ordered((def.advanced || []) as any);
      const canShowAdv = step === 1;
      const hideAdvWhenRule = step === 1 && skillKind !== 'executable';
      const advVisible = canShowAdv ? (showAdvanced || !hideAdvWhenRule) : true;
      const risk = String(govPreview?.risk_level || localRisk);
      const alertType = risk === 'high' ? 'warning' : risk === 'medium' ? 'info' : 'success';
      const approvalRequired = Boolean(govPreview?.approval?.required);
      return (
        <div className="space-y-4">
          {def.intro && <div className="text-sm text-gray-400">{def.intro}</div>}
          {schemaLoading && <div className="text-xs text-gray-500">正在加载 schema…</div>}
          {schemaVersion && (
            <div className="text-xs text-gray-500">
              schema version: {schemaVersion}（source={schemaSource}）
              {schemaNewVersion && <span className="ml-2 text-yellow-500">检测到新版本：{schemaNewVersion}（已自动更新）</span>}
            </div>
          )}
          {permCatalogVersion && step === 1 && (
            <div className="text-xs text-gray-500">
              permissions catalog: {permCatalogVersion || 'default'}（source={permCatalogSource}）
              {permCatalogNewVersion && <span className="ml-2 text-yellow-500">检测到新版本：{permCatalogNewVersion}（已自动更新）</span>}
            </div>
          )}
          {step === 1 && (
            <Alert type={alertType as any} title={`治理提示（risk=${risk}${govLoading ? ' · 检查中…' : ''}）`}>
              <div className="space-y-1">
                {skillKind === 'executable' && !permissionsText.trim() && <div>executable 技能必须声明 permissions（建议至少 llm:generate）。</div>}
                {approvalRequired && <div>命中审批规则：{govPreview?.approval?.matched_rule_name || '需要审批'}。</div>}
                {Boolean(govPreview?.requires_confirmation) && <div>建议/需要二次确认：require_confirmation=true。</div>}
                {Array.isArray(govPreview?.hints) && govPreview.hints.length > 0 && (
                  <div className="text-xs text-gray-500">提示：{govPreview.hints.slice(0, 3).join('；')}</div>
                )}
                <div className="mt-2 flex items-center gap-2">
                  <Button variant="secondary" onClick={applyTriggerRecommendations}>
                    一键推荐触发词
                  </Button>
                </div>
              </div>
            </Alert>
          )}
          {basic.map((k) => (
            <div key={k}>{renderField(k)}</div>
          ))}
          {canShowAdv && adv.length > 0 && (
            <div className="flex items-center justify-between border-t border-dark-border pt-3">
              <div className="text-sm text-gray-400">高级选项（权限/配置）</div>
              <Button variant="secondary" onClick={() => setShowAdvanced((v) => !v)}>
                {advVisible ? '收起' : '展开'}
              </Button>
            </div>
          )}
          {advVisible &&
            adv.map((k) => (
              <div key={k}>{renderField(k)}</div>
            ))}
          {step === 1 && skillKind === 'executable' && (
            <div className="text-xs text-gray-500">
              提示：executable 的 permissions 建议遵循最小权限原则；若涉及写入/执行工具，将触发更严格的治理与审批。
            </div>
          )}
        </div>
      );
    }
    // preview
    const v = toValue();
    const md = buildSkillMdPreview(v);
    const { fm, body } = splitFrontmatterBody(md);
    const base = baselineValue();
    const baseMd = buildSkillMdPreview(base);
    const { fm: baseFm, body: baseBody } = splitFrontmatterBody(baseMd);
    const fmDiff = unifiedDiff(baseFm, fm);
    const bodyDiff = unifiedDiff(baseBody, body);
    const fullDiff = unifiedDiff(baseMd, md);

    const diffSummary = [
      { k: 'name', label: '名称', a: base.name, b: v.name },
      { k: 'skill_id', label: 'Skill ID', a: base.skill_id || '', b: v.skill_id || '' },
      { k: 'display_name', label: 'display_name', a: base.display_name || '', b: v.display_name || '' },
      { k: 'category', label: '分类', a: base.category, b: v.category },
      { k: 'description', label: '描述', a: base.description, b: v.description },
      { k: 'skill_kind', label: '形态', a: base.skill_kind, b: v.skill_kind },
      { k: 'trigger_conditions', label: '触发词数量', a: String(base.trigger_conditions?.length || 0), b: String(v.trigger_conditions?.length || 0) },
      { k: 'permissions', label: '权限数量', a: String(base.permissions?.length || 0), b: String(v.permissions?.length || 0) },
      { k: 'input_schema', label: 'input_schema', a: stableJson(base.input_schema), b: stableJson(v.input_schema) },
      { k: 'output_schema', label: 'output_schema', a: stableJson(base.output_schema), b: stableJson(v.output_schema) },
      { k: 'sop', label: 'SOP', a: stableJson(base.sop), b: stableJson(v.sop) },
    ].filter((x) => x.a !== x.b);

    return (
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="text-sm font-medium text-gray-200">生成预览（SKILL.md）</div>
          <div className="flex items-center gap-2">
            <Badge variant={'success' as any}>v2</Badge>
            <Button
              variant="secondary"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(md);
                  toast.success('已复制 SKILL.md');
                } catch {
                  toast.error('复制失败');
                }
              }}
            >
              复制 SKILL.md
            </Button>
            <Button variant="secondary" onClick={() => setDiffOpen(true)}>
              查看 Diff
            </Button>
            <Button variant="secondary" onClick={() => setPreviewOpen(true)}>
              全屏预览
            </Button>
          </div>
        </div>
        <Textarea label="Frontmatter（预览）" rows={8} value={fm} readOnly />
        <Textarea label="Body（预览）" rows={10} value={body} readOnly />

        <Modal open={previewOpen} onClose={() => setPreviewOpen(false)} title="SKILL.md 预览" width={900}>
          <Textarea rows={26} value={md} readOnly />
        </Modal>

        <Modal open={diffOpen} onClose={() => setDiffOpen(false)} title="Diff 预览（基线=向导初始值/默认值）" width={980}>
          <div className="space-y-3">
            <div className="text-sm text-gray-300">
              <div className="font-medium text-gray-200 mb-1">变更摘要（结构化）</div>
              {diffSummary.length === 0 ? (
                <div className="text-sm text-gray-500">无变更（生成结果与基线一致）</div>
              ) : (
                <div className="space-y-1">
                  {diffSummary.slice(0, 12).map((it) => (
                    <div key={it.k} className="text-xs text-gray-400">
                      <span className="text-gray-300">{it.label}：</span>
                      <span className="text-gray-500">old=</span>
                      <code className="text-gray-300">{String(it.a).slice(0, 120)}</code>
                      <span className="text-gray-500"> new=</span>
                      <code className="text-gray-300">{String(it.b).slice(0, 120)}</code>
                    </div>
                  ))}
                  {diffSummary.length > 12 && <div className="text-xs text-gray-500">（仅展示前 12 条变更）</div>}
                </div>
              )}
            </div>
            <Textarea label="Frontmatter Diff" rows={10} value={fmDiff} readOnly />
            <Textarea label="SOP Diff" rows={10} value={bodyDiff} readOnly />
            <Textarea label="Full Diff" rows={12} value={fullDiff} readOnly />
            <div className="text-xs text-gray-500">说明：这是轻量级行对比，用于“确认我将生成什么”。后续可升级为更精细的结构化 diff。</div>
          </div>
        </Modal>
      </div>
    );
  };

  const footer = (
    <>
      <Button
        variant="secondary"
        onClick={() => {
          if (step === 0) onClose();
          else setStep((s) => Math.max(0, s - 1));
        }}
      >
        {step === 0 ? '取消' : '上一步'}
      </Button>
      {step < steps.length - 1 ? (
        <Button
          variant="primary"
          onClick={() => {
            if (!validateStep()) return;
            setStep((s) => Math.min(steps.length - 1, s + 1));
          }}
        >
          下一步
        </Button>
      ) : (
        <Button
          variant="primary"
          onClick={() => {
            if (!validateStep()) return;
            const v = toValue();
            onApply(v);
            toast.success('已生成（可继续修改后点击创建）');
            onClose();
            setStep(0);
          }}
        >
          生成到表单
        </Button>
      )}
    </>
  );

  return (
    <Modal
      open={open}
      onClose={() => {
        onClose();
        setStep(0);
      }}
      title={`Skill 向导 v2（${step + 1}/${steps.length}）：${steps[step]}`}
      width={880}
      footer={footer}
    >
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {steps.map((t, i) => (
          <Badge key={t} variant={(i === step ? ('primary' as any) : ('secondary' as any))}>
            {i + 1}. {t}
          </Badge>
        ))}
      </div>
      {content()}
    </Modal>
  );
};

export default SkillWizardV2Modal;
