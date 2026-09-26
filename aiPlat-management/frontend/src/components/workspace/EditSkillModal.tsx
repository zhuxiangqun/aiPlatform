import React, { useEffect, useMemo, useState } from 'react';
import {
  workspaceSkillApi,
  SKILL_CATEGORY_OPTIONS,
  SKILL_CATEGORY_HELP,
} from '../../services';
import type { Skill } from '../../services';
import { Button, Input, Modal, Select, Textarea, toast } from '../ui';
import PromptDiffModal from './PromptDiffModal';

interface EditSkillModalProps {
  open: boolean;
  skill: Skill | null;
  onClose: () => void;
  onSuccess: () => void;
}

type SchemaField = {
  key: string;
  name: string;
  type: string;
  required: boolean;
  description: string;
};

const FIELD_TYPES = [
  { value: 'string', label: '文本 string' },
  { value: 'integer', label: '整数 integer' },
  { value: 'number', label: '数字 number' },
  { value: 'boolean', label: '是/否 boolean' },
  { value: 'array', label: '列表 array' },
  { value: 'object', label: '对象 object' },
];

let _fieldSeq = 0;
const newFieldKey = () => `f${++_fieldSeq}_${Date.now().toString(36)}`;

function schemaToFields(schema: unknown): SchemaField[] {
  if (!schema || typeof schema !== 'object' || Array.isArray(schema)) return [];
  return Object.entries(schema as Record<string, any>).map(([name, def]) => {
    const d = def && typeof def === 'object' && !Array.isArray(def) ? def : {};
    return {
      key: newFieldKey(),
      name,
      type: String(d.type || 'string'),
      required: d.required === true,
      description: String(d.description || ''),
    };
  });
}

function fieldsToSchema(fields: SchemaField[]): Record<string, unknown> | null {
  const out: Record<string, unknown> = {};
  for (const f of fields) {
    const name = f.name.trim();
    if (!name) {
      toast.error('字段名不能为空');
      return null;
    }
    if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(name)) {
      toast.error(`字段名无效：${name}`, '请用英文 snake_case，如 outline、template_path');
      return null;
    }
    if (out[name]) {
      toast.error(`字段名重复：${name}`);
      return null;
    }
    out[name] = {
      type: f.type || 'string',
      required: !!f.required,
      description: f.description || '',
    };
  }
  return out;
}

function fieldsToSchemaLoose(fields: SchemaField[]): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const f of fields) {
    const name = f.name.trim();
    if (!name) continue;
    out[name] = {
      type: f.type || 'string',
      required: !!f.required,
      description: f.description || '',
    };
  }
  return out;
}

function SchemaFieldsEditor({
  title,
  hint,
  fields,
  onChange,
  emptyHint,
}: {
  title: string;
  hint: string;
  fields: SchemaField[];
  onChange: (next: SchemaField[]) => void;
  emptyHint: string;
}) {
  const [showOptional, setShowOptional] = useState(false);
  const update = (key: string, patch: Partial<SchemaField>) => {
    onChange(fields.map((f) => (f.key === key ? { ...f, ...patch } : f)));
  };
  const remove = (key: string) => onChange(fields.filter((f) => f.key !== key));
  const add = (required = false) =>
    onChange([
      ...fields,
      { key: newFieldKey(), name: '', type: 'string', required, description: '' },
    ]);

  const requiredFields = fields.filter((f) => f.required);
  const optionalFields = fields.filter((f) => !f.required);

  const renderCard = (f: SchemaField, idxLabel: string) => (
    <div key={f.key} className="p-3 space-y-2 bg-dark-card border-t border-dark-border first:border-t-0">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-[11px] text-gray-500 shrink-0">{idxLabel}</span>
          {f.name ? (
            <code className="text-xs text-primary truncate">{f.name}</code>
          ) : (
            <span className="text-[11px] text-amber-400">未命名</span>
          )}
          {f.required ? (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-900/40 text-amber-200">必填</span>
          ) : (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-dark-bg text-gray-500">可选</span>
          )}
        </div>
        <button
          type="button"
          className="text-[11px] text-red-400 hover:text-red-300 shrink-0"
          onClick={() => remove(f.key)}
        >
          删除
        </button>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
        <div>
          <div className="text-[11px] text-gray-500 mb-1">字段名（英文）</div>
          <Input
            value={f.name}
            onChange={(e: any) => update(f.key, { name: e.target.value })}
            placeholder="outline"
          />
        </div>
        <div>
          <div className="text-[11px] text-gray-500 mb-1">类型</div>
          <Select
            value={f.type}
            onChange={(v: string) => update(f.key, { type: v })}
            options={FIELD_TYPES}
          />
        </div>
        <div className="flex items-end pb-1">
          <label className="flex items-center gap-2 text-xs text-gray-300 cursor-pointer">
            <input
              type="checkbox"
              checked={f.required}
              onChange={(e) => update(f.key, { required: e.target.checked })}
            />
            必填
          </label>
        </div>
      </div>
      <div>
        <div className="text-[11px] text-gray-500 mb-1">说明（给人看）</div>
        <Input
          value={f.description}
          onChange={(e: any) => update(f.key, { description: e.target.value })}
          placeholder="这个参数是做什么的"
        />
      </div>
    </div>
  );

  return (
    <div className="rounded-lg border border-dark-border overflow-hidden">
      <div className="px-3 py-2 bg-dark-bg border-b border-dark-border flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="text-sm text-gray-200 font-medium">{title}</div>
          <div className="text-[11px] text-gray-500 mt-0.5">{hint}</div>
          {fields.length > 0 && (
            <div className="text-[11px] text-gray-400 mt-1">
              必填 {requiredFields.length} · 可选 {optionalFields.length}
              {optionalFields.length > 0 ? '（可选可折叠，执行时可不填）' : ''}
            </div>
          )}
        </div>
        <Button size="sm" variant="secondary" onClick={() => add(false)}>
          + 添加字段
        </Button>
      </div>
      {fields.length === 0 ? (
        <div className="px-3 py-6 text-center text-xs text-gray-500">{emptyHint}</div>
      ) : (
        <div>
          {requiredFields.length > 0 ? (
            <div>
              <div className="px-3 py-1.5 text-[11px] text-amber-200/90 bg-amber-950/20 border-b border-dark-border">
                必填（执行时必须提供）
              </div>
              {requiredFields.map((f, i) => renderCard(f, `必填 ${i + 1}`))}
            </div>
          ) : (
            <div className="px-3 py-3 text-xs text-amber-300/80 border-b border-dark-border">
              还没有必填字段。日常至少保留一个主输入（如 outline / message）。
            </div>
          )}

          {optionalFields.length > 0 && (
            <div>
              <button
                type="button"
                className="w-full px-3 py-2 text-left text-[11px] text-gray-400 hover:text-gray-200 bg-dark-bg/60 border-t border-dark-border flex items-center justify-between"
                onClick={() => setShowOptional((v) => !v)}
              >
                <span>
                  可选字段（{optionalFields.length}）— 执行时可不填，有默认策略
                </span>
                <span className="text-gray-500">{showOptional ? '收起 ▲' : '展开 ▼'}</span>
              </button>
              {showOptional && optionalFields.map((f, i) => renderCard(f, `可选 ${i + 1}`))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const PERM_PRESETS = [
  { id: 'llm:generate', label: 'llm:generate', hint: '调用模型生成' },
  { id: 'tool:workspace_fs_write', label: '写文件', hint: '写出 pptx/docx 等' },
  { id: 'tool:websearch', label: '联网搜索', hint: '与「不联网」冲突时勿勾' },
  { id: 'tool:webfetch', label: '抓取网页', hint: '与「不联网」冲突时勿勾' },
  { id: 'tool:run_command', label: '跑命令', hint: '高风险，一般 PPT 不需要' },
];

/** Strip create-time empty scaffold that wraps a real SOP body. */
function cleanSopScaffold(body: string): { text: string; cleaned: boolean } {
  const raw = String(body || '');
  if (!raw.includes('用 1-3 句话说明此技能要达成的目标')) {
    return { text: raw, cleaned: false };
  }
  const markers = ['# 概述', '## 何时使用', '## 验收清单', '## 硬性要求'];
  let cut = -1;
  for (const m of markers) {
    const i = raw.indexOf(m);
    if (i > 40) {
      cut = i;
      break;
    }
  }
  if (cut < 0) return { text: raw, cleaned: false };
  let text = raw.slice(cut).trim();
  const trail = text.lastIndexOf('## 质量要求（Checklist）');
  if (trail > 0 && text.slice(trail).includes('覆盖所有输入范围与边界情况')) {
    if (text.includes('## 验收清单') || text.includes('## Checklist')) {
      text = text.slice(0, trail).trim();
    }
  }
  return { text, cleaned: text !== raw.trim() };
}

function parseJsonObject(label: string, text: string): Record<string, unknown> | null {
  const t = (text || '').trim();
  if (!t) return {};
  try {
    const v = JSON.parse(t);
    if (v && typeof v === 'object' && !Array.isArray(v)) return v as Record<string, unknown>;
    toast.error(`${label} 必须是 JSON 对象`);
    return null;
  } catch {
    toast.error(`${label} JSON 格式错误`);
    return null;
  }
}

const EditSkillModal: React.FC<EditSkillModalProps> = ({ open, skill, onClose, onSuccess }) => {
  const [loading, setLoading] = useState(false);
  const [fetching, setFetching] = useState(false);
  const [name, setName] = useState('');
  const [category, setCategory] = useState('general');
  const [description, setDescription] = useState('');
  const [skillKind, setSkillKind] = useState<'rule' | 'executable'>('rule');
  const [executionType, setExecutionType] = useState<'prompt' | 'handler' | 'python_class'>('prompt');
  const [permissions, setPermissions] = useState<string[]>([]);
  const [triggerText, setTriggerText] = useState('');
  const [negativeText, setNegativeText] = useState('');
  const [requireConfirmation, setRequireConfirmation] = useState(false);
  const [timeoutSeconds, setTimeoutSeconds] = useState('120');
  const [configExtraText, setConfigExtraText] = useState('{}');
  const [inputFields, setInputFields] = useState<SchemaField[]>([]);
  const [outputFields, setOutputFields] = useState<SchemaField[]>([]);
  const [inputSchemaText, setInputSchemaText] = useState('{}');
  const [outputSchemaText, setOutputSchemaText] = useState('{}');
  const [ioAdvanced, setIoAdvanced] = useState(false);
  const [sopText, setSopText] = useState('');
  const [sopOrig, setSopOrig] = useState('');
  const [sopCleanedHint, setSopCleanedHint] = useState(false);
  const [skillMdPath, setSkillMdPath] = useState('');
  const [metaBase, setMetaBase] = useState<Record<string, unknown>>({});
  const [optimizeOpen, setOptimizeOpen] = useState(false);
  const [optimizePrompt, setOptimizePrompt] = useState('');
  const [section, setSection] = useState<'basic' | 'gov' | 'io' | 'sop'>('basic');

  const syncSchemaTextsFromFields = (ins: SchemaField[], outs: SchemaField[]) => {
    setInputSchemaText(JSON.stringify(fieldsToSchemaLoose(ins), null, 2));
    setOutputSchemaText(JSON.stringify(fieldsToSchemaLoose(outs), null, 2));
  };

  const load = async (skillId: string, fallback?: Skill | null) => {
    setFetching(true);
    try {
      const [detail, md] = await Promise.all([
        workspaceSkillApi.get(skillId),
        workspaceSkillApi.getSkillMarkdown(skillId),
      ]);
      const data = detail as any;
      const meta = (data.metadata || fallback?.metadata || {}) as Record<string, any>;
      setMetaBase(meta && typeof meta === 'object' ? { ...meta } : {});

      const cat = data.category || data.type || fallback?.category || 'general';
      setName(data.name || fallback?.name || '');
      setCategory(cat);
      setDescription(data.description || fallback?.description || '');

      const perms: string[] = Array.isArray(meta.permissions)
        ? meta.permissions.map(String)
        : [];
      setPermissions(perms);
      const sk = String(meta.skill_kind || '').toLowerCase() === 'executable' ||
        perms.some((p) => /workspace_fs_write|run_command|file_operations/.test(p))
        ? 'executable'
        : 'rule';
      setSkillKind(sk);
      const et = String(meta.execution_type || '').toLowerCase();
      setExecutionType(
        et === 'handler' || et === 'python_class' || et === 'prompt'
          ? (et as any)
          : 'prompt',
      );
      const triggers = Array.isArray(meta.trigger_conditions) ? meta.trigger_conditions.map(String) : [];
      setTriggerText(triggers.join('\n'));
      const negs = Array.isArray(meta.negative_triggers) ? meta.negative_triggers.map(String) : [];
      setNegativeText(negs.join('\n'));

      const cfg = { ...(data.config || fallback?.config || {}) } as Record<string, unknown>;
      setRequireConfirmation(cfg.require_confirmation === true);
      setTimeoutSeconds(cfg.timeout_seconds != null ? String(cfg.timeout_seconds) : sk === 'executable' ? '120' : '');
      const rest = { ...cfg };
      delete rest.require_confirmation;
      delete rest.timeout_seconds;
      setConfigExtraText(Object.keys(rest).length ? JSON.stringify(rest, null, 2) : '{}');

      const inSchema = data.input_schema || fallback?.input_schema || {};
      const outSchema = data.output_schema || fallback?.output_schema || {};
      const ins = schemaToFields(inSchema);
      const outs = schemaToFields(outSchema);
      setInputFields(ins);
      setOutputFields(outs);
      setInputSchemaText(JSON.stringify(inSchema || {}, null, 2));
      setOutputSchemaText(JSON.stringify(outSchema || {}, null, 2));
      setIoAdvanced(false);

      const raw = String((md as any)?.content || '');
      let body = raw;
      if (body.startsWith('---')) {
        const end = body.indexOf('\n---\n', 3);
        if (end !== -1) body = body.slice(end + 5).replace(/^\n+/, '');
      }
      const cleaned = cleanSopScaffold(body);
      setSopText(cleaned.text);
      setSopOrig(cleaned.text);
      setSopCleanedHint(cleaned.cleaned);
      setSkillMdPath(String((md as any)?.path || ''));
    } catch {
      toast.error('加载 Skill 失败');
    } finally {
      setFetching(false);
    }
  };

  useEffect(() => {
    if (open && skill?.id) {
      setSection('basic');
      void load(skill.id, skill);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, skill?.id]);

  const togglePerm = (id: string) => {
    setPermissions((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const handleSubmit = async () => {
    if (!skill) return;
    if (!name.trim()) {
      toast.error('请输入 Skill 名称');
      return;
    }
    if (!category) {
      toast.error('请选择分类');
      return;
    }

    let input_schema: Record<string, unknown> | null;
    let output_schema: Record<string, unknown> | null;
    if (ioAdvanced) {
      input_schema = parseJsonObject('输入契约', inputSchemaText);
      if (input_schema === null) return;
      output_schema = parseJsonObject('输出契约', outputSchemaText);
      if (output_schema === null) return;
    } else {
      input_schema = fieldsToSchema(inputFields);
      if (input_schema === null) return;
      output_schema = fieldsToSchema(outputFields);
      if (output_schema === null) return;
    }

    const extra = parseJsonObject('额外配置', configExtraText);
    if (extra === null) return;

    const config: Record<string, unknown> = { ...extra };
    config.require_confirmation = requireConfirmation;
    const ts = Number(timeoutSeconds);
    if (Number.isFinite(ts) && ts > 0) config.timeout_seconds = Math.floor(ts);
    else delete config.timeout_seconds;

    const triggers = triggerText
      .split('\n')
      .map((x) => x.trim())
      .filter(Boolean);
    const negatives = negativeText
      .split('\n')
      .map((x) => x.trim())
      .filter(Boolean);

    setLoading(true);
    try {
      const nextMeta: Record<string, unknown> = {
        ...metaBase,
        skill_kind: skillKind,
        execution_type: executionType,
        permissions,
        trigger_conditions: triggers,
        negative_triggers: negatives,
      };
      const res = await workspaceSkillApi.update(skill.id, {
        name: name.trim(),
        category,
        description: description || '',
        config,
        input_schema,
        output_schema,
        metadata: nextMeta,
      });
      toast.success(`已保存「${name.trim()}」`);
      const sum = (res as any)?.lint?.summary;
      if (sum && (Number(sum.error_count || 0) > 0 || Number(sum.warning_count || 0) > 0)) {
        toast.warning('Skill Lint', `E${sum.error_count || 0}/W${sum.warning_count || 0}（risk=${sum.risk_level || 'low'}）`);
      }
      if (sopText !== sopOrig) {
        await workspaceSkillApi.updateSkillMarkdown(skill.id, { mode: 'replace_body', body: sopText || '' });
        setSopOrig(sopText);
        toast.success('SOP 已写入 SKILL.md');
      }
      onSuccess();
      onClose();
    } catch (error: any) {
      toast.error('更新失败', String(error?.message || error || ''));
    } finally {
      setLoading(false);
    }
  };

  const categoryOptions = useMemo(() => SKILL_CATEGORY_OPTIONS, []);

  const downloadText = (filename: string, content: string) => {
    try {
      const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch {
      // ignore
    }
  };

  const tabs: { id: typeof section; label: string; blurb: string }[] = [
    { id: 'basic', label: '基本信息', blurb: '叫什么、干什么' },
    { id: 'gov', label: '怎么跑', blurb: '形态、权限、触发' },
    { id: 'io', label: '入参出参', blurb: '填什么、返回什么' },
    { id: 'sop', label: '操作手册', blurb: '步骤与硬性要求' },
  ];

  const SectionTip: React.FC<{ children: React.ReactNode }> = ({ children }) => (
    <div className="rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-xs text-gray-400 leading-relaxed">
      {children}
    </div>
  );

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        title={`编辑 Skill：${name || skill?.id || ''}`}
        width={860}
        footer={
          <>
            <Button variant="ghost" size="sm" onClick={onClose} disabled={loading}>
              取消
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => skill?.id && load(skill.id, skill)}
              disabled={loading || fetching || !skill}
            >
              放弃修改并重新加载
            </Button>
            <Button variant="primary" onClick={handleSubmit} loading={loading} disabled={fetching}>
              保存
            </Button>
          </>
        }
      >
        {fetching ? (
          <div className="text-sm text-gray-500 py-8 text-center">加载中...</div>
        ) : (
          <div className="space-y-4 max-h-[75vh] overflow-y-auto pr-1">
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-gray-500">
              <span>改完点右下角「保存」即可。日常优先改：描述、入参出参、操作手册。</span>
              <button
                type="button"
                className="text-gray-500 hover:text-gray-300 underline underline-offset-2"
                disabled={loading || !skill}
                onClick={async () => {
                  if (!skill) return;
                  try {
                    const md = await workspaceSkillApi.getSkillMarkdown(skill.id);
                    downloadText(`${String((md as any)?.skill_id || skill.id)}.SKILL.md`, String((md as any)?.content || ''));
                    toast.success('已下载 SKILL.md');
                  } catch {
                    toast.error('下载失败');
                  }
                }}
              >
                下载 SKILL.md
              </button>
            </div>
            {skillMdPath ? (
              <div className="text-[11px] text-gray-600 break-all -mt-2">磁盘：{skillMdPath}</div>
            ) : null}

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {tabs.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setSection(t.id)}
                  className={`text-left px-3 py-2.5 rounded-xl border transition-colors ${
                    section === t.id
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-dark-border text-gray-400 hover:border-gray-500 hover:text-gray-200'
                  }`}
                >
                  <div className="text-sm font-medium">{t.label}</div>
                  <div className="text-[11px] mt-0.5 opacity-70">{t.blurb}</div>
                </button>
              ))}
            </div>

            {section === 'basic' && (
              <div className="space-y-3">
                <SectionTip>
                  这里管「对外怎么介绍」。多余约束、错误说法优先改<strong className="text-gray-300">描述</strong>；
                  详细步骤去「操作手册」。
                </SectionTip>
                <div className="rounded-xl border border-dark-border p-4 space-y-3">
                  <Input label="显示名称" value={name} onChange={(e: any) => setName(e.target.value)} />
                  {skill?.id ? (
                    <div className="text-[11px] text-gray-500">
                      ID：<code className="text-gray-400">{skill.id}</code>（一般不用改）
                    </div>
                  ) : null}
                  <div>
                    <div className="text-sm font-medium text-gray-300 mb-1.5">分类</div>
                    <Select value={category} onChange={(v: string) => setCategory(v)} options={categoryOptions} />
                    <div className="text-xs text-gray-500 mt-1">
                      只影响列表筛选。做 PPT / 文档类选 <span className="text-gray-300">generation</span>。
                    </div>
                    {SKILL_CATEGORY_HELP[category as keyof typeof SKILL_CATEGORY_HELP] && (
                      <div className="text-xs text-gray-400 mt-0.5">
                        {SKILL_CATEGORY_HELP[category as keyof typeof SKILL_CATEGORY_HELP]}
                      </div>
                    )}
                  </div>
                  <Textarea
                    label="描述（列表里看到的那段话）"
                    rows={7}
                    value={description}
                    onChange={(e: any) => setDescription(e.target.value)}
                    placeholder="输入是什么 → 怎么处理 → 输出什么 → 约束是什么（不要写无关限制）"
                  />
                  <div className="text-[11px] text-gray-500">
                    建议结构：输入 / 处理 / 输出 / 约束。约束只写真正要遵守的，多一条就会限制行为。
                  </div>
                </div>
              </div>
            )}

            {section === 'gov' && (
              <div className="space-y-3">
                <SectionTip>
                  PPT 一类「生成文件」的 Skill：选<strong className="text-gray-300">可写文件</strong> +
                  <strong className="text-gray-300">按手册执行</strong>，并勾选「写文件」权限即可。
                </SectionTip>

                <div className="rounded-xl border border-dark-border p-4 space-y-3">
                  <div className="text-sm text-gray-200 font-medium">这个 Skill 会不会写文件 / 调工具？</div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {(
                      [
                        { k: 'rule' as const, title: '只出文案', desc: '不写磁盘、不调外部工具，只靠模型按手册回答' },
                        { k: 'executable' as const, title: '可写文件 / 调工具', desc: '能生成 pptx 等文件，需要勾选权限' },
                      ] as const
                    ).map((opt) => (
                      <button
                        key={opt.k}
                        type="button"
                        onClick={() => {
                          setSkillKind(opt.k);
                          if (opt.k === 'executable' && executionType === 'handler') setExecutionType('prompt');
                        }}
                        className={`text-left rounded-xl border px-3 py-3 transition-colors ${
                          skillKind === opt.k
                            ? 'border-primary bg-primary/10'
                            : 'border-dark-border hover:border-gray-500'
                        }`}
                      >
                        <div className={`text-sm font-medium ${skillKind === opt.k ? 'text-primary' : 'text-gray-200'}`}>
                          {opt.title}
                        </div>
                        <div className="text-[11px] text-gray-500 mt-1">{opt.desc}</div>
                      </button>
                    ))}
                  </div>
                </div>

                <div className="rounded-xl border border-dark-border p-4 space-y-3">
                  <div className="text-sm text-gray-200 font-medium">怎么执行？</div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {(
                      [
                        { k: 'prompt' as const, title: '按操作手册执行（推荐）', desc: '读 SOP，用模型+已授权工具完成' },
                        { k: 'handler' as const, title: '专用程序（handler.py）', desc: '同目录必须有 handler.py，否则会失败' },
                      ] as const
                    ).map((opt) => (
                      <button
                        key={opt.k}
                        type="button"
                        onClick={() => setExecutionType(opt.k)}
                        className={`text-left rounded-xl border px-3 py-3 transition-colors ${
                          executionType === opt.k
                            ? 'border-primary bg-primary/10'
                            : 'border-dark-border hover:border-gray-500'
                        }`}
                      >
                        <div className={`text-sm font-medium ${executionType === opt.k ? 'text-primary' : 'text-gray-200'}`}>
                          {opt.title}
                        </div>
                        <div className="text-[11px] text-gray-500 mt-1">{opt.desc}</div>
                      </button>
                    ))}
                  </div>
                  {executionType === 'python_class' && (
                    <div className="text-xs text-amber-300">当前为 python_class（高级）。PPT 场景一般改回「按操作手册执行」。</div>
                  )}
                  <details className="text-xs text-gray-500">
                    <summary className="cursor-pointer hover:text-gray-300">其它执行方式</summary>
                    <div className="mt-2">
                      <Select
                        value={executionType}
                        onChange={(v: string) => setExecutionType(v as any)}
                        options={[
                          { value: 'prompt', label: 'prompt / 按手册' },
                          { value: 'handler', label: 'handler.py' },
                          { value: 'python_class', label: 'python_class' },
                        ]}
                      />
                    </div>
                  </details>
                </div>

                <div className="rounded-xl border border-dark-border p-4 space-y-3">
                  <div className="text-sm text-gray-200 font-medium">允许做什么？</div>
                  <div className="text-xs text-gray-500">只勾真正需要的。生成 pptx 至少勾「写文件」。</div>
                  <div className="space-y-2">
                    {PERM_PRESETS.map((p) => (
                      <label
                        key={p.id}
                        className={`flex items-start gap-3 rounded-lg border px-3 py-2.5 cursor-pointer transition-colors ${
                          permissions.includes(p.id)
                            ? 'border-primary/40 bg-primary/5'
                            : 'border-dark-border hover:border-gray-600'
                        }`}
                      >
                        <input
                          type="checkbox"
                          className="mt-1"
                          checked={permissions.includes(p.id)}
                          onChange={() => togglePerm(p.id)}
                        />
                        <span>
                          <span className="text-sm text-gray-100 block">{p.label}</span>
                          <span className="text-[11px] text-gray-500">{p.hint}</span>
                        </span>
                      </label>
                    ))}
                  </div>
                  <label className="flex items-start gap-2 text-xs text-amber-200/90 pt-1 cursor-pointer">
                    <input
                      type="checkbox"
                      className="mt-0.5"
                      checked={requireConfirmation}
                      onChange={(e) => setRequireConfirmation(e.target.checked)}
                    />
                    <span>
                      写文件前二次确认
                      <span className="block text-gray-500 mt-0.5">生产更安全；本机自测可不勾</span>
                    </span>
                  </label>
                  <div className="flex items-center gap-2 pt-1 max-w-xs">
                    <span className="text-xs text-gray-500 shrink-0">超时（秒）</span>
                    <Input value={timeoutSeconds} onChange={(e: any) => setTimeoutSeconds(e.target.value)} />
                  </div>
                </div>

                <div className="rounded-xl border border-dark-border p-4 space-y-3">
                  <div className="text-sm text-gray-200 font-medium">什么话会命中这个 Skill？</div>
                  <Textarea
                    label="正向说法（每行一条）"
                    rows={3}
                    value={triggerText}
                    onChange={(e: any) => setTriggerText(e.target.value)}
                    placeholder={'生成PPT\n做一份演示文稿'}
                  />
                  <Textarea
                    label="不要命中的说法（每行一条）"
                    rows={2}
                    value={negativeText}
                    onChange={(e: any) => setNegativeText(e.target.value)}
                    placeholder={'只要文字稿不要文件'}
                  />
                </div>

                <details className="rounded-xl border border-dark-border p-4">
                  <summary className="cursor-pointer text-xs text-gray-400 hover:text-gray-200">高级：其它配置 JSON</summary>
                  <Textarea
                    className="mt-2"
                    rows={4}
                    value={configExtraText}
                    onChange={(e: any) => setConfigExtraText(e.target.value)}
                  />
                  <div className="text-[11px] text-gray-500 mt-1">
                    超时、二次确认请用上面的开关，不要在 JSON 里重复写。
                  </div>
                </details>
              </div>
            )}

            {section === 'io' && (
              <div className="space-y-4">
                <SectionTip>
                  <div><span className="text-gray-200">入参</span> = 执行时要填的内容。列表可能较长，但<strong className="text-gray-300 font-medium">只有勾了「必填」的才必须填</strong>。</div>
                  <div className="mt-0.5"><span className="text-gray-200">出参</span> = 跑完系统返回什么（给程序/诊断看）。日常执行不必手填；建议保留 <code className="text-primary">result</code> + <code className="text-primary">markdown</code>。</div>
                  <div className="mt-0.5 text-gray-500">以 PPT 为例：入参真正必填通常只有 <code className="text-primary">outline</code>；模版路径、字数上限都是可选。出参里的页数/时间/告警是结果元数据，不是你要再填一遍的表单项。</div>
                </SectionTip>

                {!ioAdvanced ? (
                  <>
                    <SchemaFieldsEditor
                      title="入参（执行时要填）"
                      hint="必填会展开；可选默认折叠"
                      fields={inputFields}
                      emptyHint="还没有入参。点「添加字段」开始。"
                      onChange={(next) => {
                        setInputFields(next);
                        syncSchemaTextsFromFields(next, outputFields);
                      }}
                    />
                    <SchemaFieldsEditor
                      title="出参（执行结果，系统返回）"
                      hint="描述返回结构；执行时不用填这些"
                      fields={outputFields}
                      emptyHint="还没有出参。点「添加字段」开始。"
                      onChange={(next) => {
                        setOutputFields(next);
                        syncSchemaTextsFromFields(inputFields, next);
                      }}
                    />
                    <button
                      type="button"
                      className="text-xs text-gray-500 hover:text-gray-300 underline underline-offset-2"
                      onClick={() => {
                        syncSchemaTextsFromFields(inputFields, outputFields);
                        setIoAdvanced(true);
                      }}
                    >
                      高级：用 JSON 编辑契约
                    </button>
                  </>
                ) : (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-xs text-amber-300/90">高级 JSON 模式</div>
                      <button
                        type="button"
                        className="text-xs text-primary hover:underline"
                        onClick={() => {
                          const i = parseJsonObject('输入契约', inputSchemaText);
                          const o = parseJsonObject('输出契约', outputSchemaText);
                          if (i === null || o === null) return;
                          setInputFields(schemaToFields(i));
                          setOutputFields(schemaToFields(o));
                          setIoAdvanced(false);
                        }}
                      >
                        ← 切回表单
                      </button>
                    </div>
                    <Textarea
                      label="input_schema（JSON）"
                      rows={10}
                      value={inputSchemaText}
                      onChange={(e: any) => setInputSchemaText(e.target.value)}
                    />
                    <Textarea
                      label="output_schema（JSON）"
                      rows={10}
                      value={outputSchemaText}
                      onChange={(e: any) => setOutputSchemaText(e.target.value)}
                    />
                  </div>
                )}
              </div>
            )}

            {section === 'sop' && (
              <div className="space-y-3">
                <SectionTip>
                  这里是执行时真正遵守的步骤。想删多余约束，重点看
                  <strong className="text-gray-300">「何时不用」「硬性要求」「验收清单」</strong>。
                  改完记得保存。
                </SectionTip>

                {sopCleanedHint && (
                  <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-xs text-amber-200">
                    已去掉创建时留下的空模板外壳。确认内容无误后点保存。
                    <Button className="ml-2" size="sm" variant="secondary" onClick={() => setSopCleanedHint(false)}>
                      知道了
                    </Button>
                  </div>
                )}

                <div className="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => {
                      const cleaned = cleanSopScaffold(sopText);
                      setSopText(cleaned.text);
                      setSopCleanedHint(cleaned.cleaned);
                      if (cleaned.cleaned) toast.success('已清理空模板外壳');
                      else toast.info('未检测到可清理的空模板');
                    }}
                  >
                    清理空模板外壳
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      if (!sopText.trim()) {
                        toast.warning('SOP 为空，无法优化');
                        return;
                      }
                      setOptimizePrompt(sopText);
                      setOptimizeOpen(true);
                    }}
                  >
                    AI 优化文案
                  </Button>
                </div>

                <div className="rounded-xl border border-dark-border overflow-hidden">
                  <div className="px-3 py-2 bg-dark-bg border-b border-dark-border text-xs text-gray-500">
                    操作手册正文 · 写入 SKILL.md
                  </div>
                  <Textarea
                    rows={18}
                    value={sopText}
                    onChange={(e: any) => setSopText(e.target.value)}
                    className="rounded-none border-0"
                  />
                </div>
              </div>
            )}
          </div>
        )}
      </Modal>

      <PromptDiffModal
        open={optimizeOpen}
        title="AI 优化 Skill SOP"
        original={optimizePrompt}
        onClose={() => setOptimizeOpen(false)}
        onApply={(optimized) => {
          setSopText(optimized);
          toast.success('已应用优化，请保存');
        }}
      />
    </>
  );
};

export default EditSkillModal;
