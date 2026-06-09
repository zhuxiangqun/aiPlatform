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
  // Import mode
  const [sourceMode, setSourceMode] = useState<'manual' | 'url' | 'file'>('manual');
  const [importUrl, setImportUrl] = useState('');
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importDetecting, setImportDetecting] = useState(false);
  const [importResult, setImportResult] = useState<any>(null);
  const [importMeta, setImportMeta] = useState<Record<string, any>>({});
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  // Reset import state when switching modes; clear stale template defaults for import
  React.useEffect(() => {
    setImportUrl('');
    setImportFile(null);
    setImportResult(null);
    setImportMeta({});
    if (sourceMode !== 'manual') {
      setConfigText('');
      setDescription('');
      setCategory('general');
    }
  }, [sourceMode]);

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

  const handleImportDetect = async () => {
    if (sourceMode === 'url' && !importUrl.trim()) { toast.warning('请输入 GitHub URL'); return; }
    if (sourceMode === 'file' && !importFile) { toast.warning('请选择本地 Zip 文件'); return; }
    setImportDetecting(true);
    setImportResult(null);
    try {
      const payload: any = { name: name.trim() || '', description: description.trim() || '' };
      if (sourceMode === 'url') {
        payload.url = importUrl.trim();
      } else if (sourceMode === 'file' && importFile) {
        const buf = await importFile.arrayBuffer();
        const bytes = new Uint8Array(buf);
        let binary = '';
        for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
        payload.file_content = btoa(binary);
      }
      const res = await workspaceSkillApi.importDetect(payload);
      if (res.error) { toast.error('检测失败', res.error); return; }
      setImportResult(res);
      if (res.detected_name && !name) setName(res.detected_name);
      if (res.detected_description && !description) setDescription(res.detected_description);
      if (res.category) setCategory(res.category);
      if (res.display_name) setDisplayName(res.display_name);
      if (res.sop_body) setSopText(res.sop_body);
      if (res.input_schema && Object.keys(res.input_schema).length > 0) setInputSchemaText(JSON.stringify(res.input_schema, null, 2));
      if (res.output_schema && Object.keys(res.output_schema).length > 0) setOutputSchemaText(JSON.stringify(res.output_schema, null, 2));
      if (res.permissions?.length) setPermissionsText(JSON.stringify(res.permissions, null, 2));
      else if (sourceMode !== 'manual') setPermissionsText('[]');
      if (res.trigger_conditions?.length) setTriggerText(res.trigger_conditions.join('\n'));
      else if (sourceMode !== 'manual') setTriggerText('');
      if (res.timeout) {
        try {
          const cfg = configText.trim() ? JSON.parse(configText) : {};
          cfg.timeout_seconds = res.timeout;
          setConfigText(JSON.stringify(cfg, null, 2));
        } catch { setConfigText(JSON.stringify({ timeout_seconds: res.timeout }, null, 2)); }
      }
      if (res.execution_type) {
        setSkillKind(res.execution_type === 'handler' ? 'executable' : 'rule');
      }
      setImportMeta({
        tools: res.tools || [],
        execution_type: res.execution_type || 'prompt',
        timeout: res.timeout,
        ...(sourceMode === 'url' && importUrl.trim() ? { source_url: importUrl.trim() } : {}),
      });
      // Store separate for file mode (binary content)
      if (sourceMode === 'file' && importFile) {
        try {
          const buf2 = await importFile.arrayBuffer();
          const bytes2 = new Uint8Array(buf2);
          let binary2 = '';
          for (let i = 0; i < bytes2.length; i++) binary2 += String.fromCharCode(bytes2[i]);
          setImportMeta((prev: any) => ({ ...prev, source_file_content: btoa(binary2) }));
        } catch { }
      }
      toast.success('AI 检测完成');
    } catch (e: any) {
      toast.error('检测失败', e?.detail || e?.message || String(e));
    } finally { setImportDetecting(false); }
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
        metadata: importMeta,
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

      {/* ── Source / Import ── */}
      <div className="flex items-center gap-4 mb-3">
        <span className="text-sm text-gray-400">来源:</span>
        <label className="flex items-center gap-1 text-sm cursor-pointer">
          <input type="radio" name="sourceMode" checked={sourceMode === 'manual'} onChange={() => setSourceMode('manual')} />
          <span className="text-gray-300">✏️ 手动创建</span>
        </label>
        <label className="flex items-center gap-1 text-sm cursor-pointer">
          <input type="radio" name="sourceMode" checked={sourceMode === 'url'} onChange={() => setSourceMode('url')} />
          <span className="text-gray-300">🔗 从 GitHub 导入</span>
        </label>
        <label className="flex items-center gap-1 text-sm cursor-pointer">
          <input type="radio" name="sourceMode" checked={sourceMode === 'file'} onChange={() => setSourceMode('file')} />
          <span className="text-gray-300">📦 从本地导入</span>
        </label>
      </div>

      {(sourceMode === 'url' || sourceMode === 'file') && (
        <div className="p-4 rounded-lg border border-blue-500/30 bg-blue-500/5 mb-3">
          <div className="flex gap-2 items-end">
            <div className="flex-1">
              {sourceMode === 'url' ? (
                <Input label="GitHub URL" value={importUrl} onChange={(e: any) => setImportUrl(e.target.value)}
                  placeholder="https://github.com/user/skill-repo" />
              ) : (
                <div>
                  <div className="text-xs font-medium text-gray-300 mb-1">本地 Zip 文件</div>
                  <div className="flex gap-2 items-center">
                    <Button variant="secondary" size="sm" onClick={() => fileInputRef.current?.click()} disabled={importDetecting}>
                      📁 选择文件
                    </Button>
                    <input ref={fileInputRef} type="file" accept=".zip" style={{ display: 'none' }}
                      onChange={(e) => { const f = e.target.files?.[0]; if (f) { setImportFile(f); setImportUrl(''); } }} />
                    <span className="text-xs text-gray-400">{importFile ? importFile.name : '未选择文件'}</span>
                  </div>
                </div>
              )}
            </div>
            <Button variant="primary" size="sm" onClick={handleImportDetect} loading={importDetecting}
              disabled={(sourceMode === 'url' && !importUrl.trim()) || (sourceMode === 'file' && !importFile)}>
              🔍 AI 检测
            </Button>
          </div>

          {importResult && !importResult.error && (
            <div className="mt-3 p-3 rounded-lg border border-green-500/30 bg-green-500/5">
              <div className="text-sm font-medium text-green-300 mb-2">✨ AI 推荐配置（基于 SOP 分析）</div>
              <div className="grid grid-cols-2 gap-2 text-xs text-gray-300">
                <div><span className="text-gray-500">执行方式:</span> {importResult.execution_type || '-'}</div>
                <div><span className="text-gray-500">超时:</span> {importResult.timeout ? `${importResult.timeout}s` : '-'}</div>
                <div><span className="text-gray-500">分类:</span> {importResult.category || '-'}</div>
                <div><span className="text-gray-500">绑定工具:</span> {(importResult.tools || []).join(', ') || '-'}</div>
              </div>
              {importResult.reasoning && (
                <div className="text-xs text-gray-400 mt-2 italic">"{(importResult.reasoning as string).slice(0, 200)}"</div>
              )}
              <div className="text-xs text-gray-500 mt-2">以上配置已自动填入表单</div>
              {(importResult.tools_missing || []).length > 0 && (
                <div className="mt-2 p-2 rounded border border-amber-500/30 bg-amber-500/5 text-xs text-amber-300">
                  ⚠️ 系统缺少以下工具: <strong>{(importResult.tools_missing as string[]).join(', ')}</strong>
                  <div className="mt-1 text-amber-400">技能可能无法完整运行，建议先在工具管理页面安装对应工具。</div>
                </div>
              )}
            </div>
          )}
          {importResult?.error && (
            <div className="mt-2 text-xs text-red-400">{importResult.error}</div>
          )}
        </div>
      )}

      <div className="space-y-4">
        <div className="flex gap-2 items-end">
          <div className="flex-1"><Input label="名称" value={name} onChange={(e: any) => setName(e.target.value)} placeholder="例如：我的客服助手" /></div>
          {sourceMode === 'manual' && (
            <Button variant="secondary" size="sm" onClick={handleAiFill} loading={aiLoading}
              disabled={!name.trim() || !description.trim() || aiLoading}>✨ AI 智能填充</Button>
          )}
        </div>
        {sourceMode === 'manual' && (
          <div className="text-xs text-gray-500 -mt-2">根据名称和功能描述自动生成分类、显示名、输入/输出 schema、权限、触发词、SOP 等</div>
        )}
        <Input label="Skill ID（可选，留空则自动生成）" value={skillId} onChange={(e: any) => setSkillId(e.target.value)} placeholder="例如：customer_support（建议小写/下划线）" />
        <div className="flex items-end justify-between gap-3">
          <div className="flex-1">
            <Select
              label="分类"
              value={category}
              onChange={(v) => {
                setCategory(v);
                if (sourceMode === 'manual') applyTemplate(v);
              }}
              options={categoryOptions}
            />
          </div>
          {sourceMode === 'manual' && (
            <Button variant="secondary" onClick={() => applyTemplate(category)} disabled={loading}>
              应用模板
            </Button>
          )}
          {sourceMode === 'manual' && (
            <Button variant="primary" onClick={() => setWizV2Open(true)} disabled={loading}>
              向导 v2（推荐）
            </Button>
          )}
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
        {!triggerText.trim() && sourceMode !== 'manual' && (
          <div className="text-xs text-blue-400 bg-blue-500/5 border border-blue-500/20 rounded p-2 -mt-2 mb-1">
            💡 此技能未声明触发词，需要手动填写才能被自动匹配。建议 3-6 个中文触发词，例如：
            <code className="ml-1 px-1 bg-blue-900/30 rounded text-blue-300">最近30天</code>
            <code className="ml-1 px-1 bg-blue-900/30 rounded text-blue-300">帮我调研</code>
            <code className="ml-1 px-1 bg-blue-900/30 rounded text-blue-300">查一下最近</code>
          </div>
        )}
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
