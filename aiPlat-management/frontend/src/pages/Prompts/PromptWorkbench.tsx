import React, { useEffect, useState } from 'react';
import { Button, Input, Modal, Select, Textarea, toast, Badge } from '../../components/ui';
import { promptAppApi, promptEvalApi, promptOptimizeApi } from '../../services';

const TAGS_LIST = [
  "正式邀请", "人才推荐", "信息发布", "会议记录",
  "课件制作", "试题生成", "学术写作", "文案润色", "诗歌创作",
  "代码注释", "方案撰写",
  "外部客户", "评审机构", "全员", "参会者", "学生", "读者", "开发者",
  "正式礼貌", "正式直接", "客观记录", "教学引导", "创意自由", "技术准确",
];

interface Props {
  template: any;
  models: Array<{value: string; label: string}>;
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
}

const wordDiff = (oldStr: string, newStr: string) => {
  const oldWords = oldStr.split(/(\s+)/);
  const newWords = newStr.split(/(\s+)/);
  const m = oldWords.length, n = newWords.length;
  const dp: number[][] = Array.from({ length: m + 1 }, () => Array(n + 1).fill(0));
  for (let i = 1; i <= m; i++)
    for (let j = 1; j <= n; j++)
      dp[i][j] = oldWords[i - 1] === newWords[j - 1] ? dp[i - 1][j - 1] + 1 : Math.max(dp[i - 1][j], dp[i][j - 1]);
  const result: Array<{ text: string; type: 'same' | 'add' | 'del' }> = [];
  let i = m, j = n;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && oldWords[i - 1] === newWords[j - 1]) {
      result.unshift({ text: oldWords[i - 1], type: 'same' });
      i--; j--;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      result.unshift({ text: newWords[j - 1], type: 'add' });
      j--;
    } else {
      result.unshift({ text: oldWords[i - 1], type: 'del' });
      i--;
    }
  }
  return result;
};

const PromptWorkbench: React.FC<Props> = ({ template, models, open, onClose, onSaved }) => {
  // Tabs
  const [tab, setTab] = useState<'edit' | 'eval' | 'compare'>('edit');

  // Edit state
  const [editForm, setEditForm] = useState<any>({});
  const [saving, setSaving] = useState(false);
  const [previewModel, setPreviewModel] = useState('deepseek-chat');

  // Eval state
  const [evalCases, setEvalCases] = useState<any[]>([]);
  const [evalRuns, setEvalRuns] = useState<any[]>([]);
  const [evalLoading, setEvalLoading] = useState(false);
  const [evalModel, setEvalModel] = useState('deepseek-chat');
  const [newCase, setNewCase] = useState({ name: '', variables: '{}', expected_keys: '' });
  const [expandedRunId, setExpandedRunId] = useState<string | null>(null);
  const [runDetail, setRunDetail] = useState<any>(null);
  const [runDetailLoading, setRunDetailLoading] = useState(false);

  // Optimize state
  const [optimizeModel, setOptimizeModel] = useState('deepseek-chat');
  const [optimizeLoading, setOptimizeLoading] = useState(false);
  const [optimizeMessages, setOptimizeMessages] = useState<Array<{role: string; content: string; versionIndex?: number}>>([]);
  const [optimizeVersions, setOptimizeVersions] = useState<any[]>([]);
  const [optimizeActiveVersion, setOptimizeActiveVersion] = useState(0);
  const [optimizeRefineInput, setOptimizeRefineInput] = useState('');
  const [chatExpanded, setChatExpanded] = useState(false);
  const [templatePreviewExpanded, setTemplatePreviewExpanded] = useState(false);

  // Test comparison state
  const [testVars, setTestVars] = useState<Array<{name: string; value: string}>>([]);
  const [testResults, setTestResults] = useState<{original: string; optimized: string} | null>(null);
  const [testLoading, setTestLoading] = useState(false);
  const [runOutput, setRunOutput] = useState('');

  // Init from template
  useEffect(() => {
    if (!template) return;
    const safeTags = typeof template.tags === 'string'
      ? (() => { try { return JSON.parse(template.tags || '[]'); } catch { return []; } })()
      : (template.tags || []);
    const safeVars = typeof template.variables === 'string'
      ? (() => { try { return JSON.parse(template.variables || '[]'); } catch { return []; } })()
      : (template.variables || []);
    const safeScenarios = typeof template.scenario_tags === 'string'
      ? (() => { try { return JSON.parse(template.scenario_tags || '[]'); } catch { return []; } })()
      : (template.scenario_tags || []);
    setEditForm({
      ...template,
      template_id: template.id,
      tags: safeTags,
      variables: safeVars,
      scenario_tags: safeScenarios,
    });
    // Init test vars from template variables
    const vars = (safeVars || []).map((v: any) => ({ name: typeof v === 'string' ? v : v.name || '', value: '' }));
    setTestVars(vars);
    // Init newCase variables
    const tplText = template.user_prompt || template.system_prompt || '';
    const dv = [...new Set(tplText.match(/\$\{(\w+)\}/g)?.map((m: string) => m.slice(2, -1)) || [])];
    const vo: Record<string, string> = {};
    dv.forEach((v: any) => { vo[v as string] = ''; });
    setNewCase({ name: '', variables: dv.length > 0 ? JSON.stringify(vo) : '{}', expected_keys: '' });
    // Reset optimize state
    setOptimizeMessages([]);
    setOptimizeVersions([]);
    setOptimizeActiveVersion(0);
    setTestResults(null);
    setRunOutput('');
    setChatExpanded(false);
    setTemplatePreviewExpanded(false);
    // Load eval data
    loadEvalData();
  }, [template]);

  const loadEvalData = async () => {
    if (!template?.id) return;
    setEvalLoading(true);
    try {
      const [tc, rn] = await Promise.all([
        promptEvalApi.listTestCases(template.id),
        promptEvalApi.listRuns(template.id),
      ]);
      setEvalCases((tc as any).items || []);
      setEvalRuns(rn as any || []);
    } catch (e: any) { console.error('加载评估数据失败:', e); }
    finally { setEvalLoading(false); }
  };

  // Auto-refresh eval runs
  useEffect(() => {
    if (!open || !evalRuns.some(r => r.status === 'running')) return;
    const timer = setInterval(() => loadEvalData(), 3000);
    return () => clearInterval(timer);
  }, [open, evalRuns]);

  // ───────── Edit functions ─────────

  const handleSave = async () => {
    setSaving(true);
    try {
      const parseArr = (val: any) => {
        if (Array.isArray(val)) return val;
        if (typeof val === 'string') { try { return JSON.parse(val || '[]'); } catch { return []; } }
        return [];
      };
      const body = {
        name: editForm.name,
        category: editForm.category,
        tags: parseArr(editForm.tags),
        system_prompt: editForm.system_prompt,
        user_prompt: editForm.user_prompt,
        assistant_prompt: editForm.assistant_prompt,
        variables: Array.isArray(editForm.variables) ? editForm.variables : [],
        examples: editForm.examples || '',
        constraints: editForm.constraints || '',
        scenario_tags: parseArr(editForm.scenario_tags),
        status: editForm.status || 'draft',
      };
      const isEdit = !!editForm.template_id;
      if (isEdit) {
        await promptAppApi.update(editForm.template_id, body);
      } else {
        await promptAppApi.create({ ...body, template_id: editForm.template_id || editForm.name.toLowerCase().replace(/\s+/g, '-') });
      }
      toast.success('已保存');
      onSaved();
    } catch (e: any) { toast.error('保存失败', e?.message); }
    finally { setSaving(false); }
  };

  const handleRun = async () => {
    if (!template?.id) return;
    const varsObj: Record<string, string> = {};
    testVars.forEach(tv => { if (tv.value) varsObj[tv.name] = tv.value; });
    setTestLoading(true);
    setRunOutput('');
    try {
      const r = await promptAppApi.run({ template_id: template.id, variables: varsObj, model: previewModel });
      setRunOutput((r as any).output || '');
      toast.success('运行成功');
    } catch (e: any) { toast.error('运行失败', e?.message); }
    finally { setTestLoading(false); }
  };

  // ───────── Eval functions ─────────

  const handleAddCase = async () => {
    if (!template?.id) return;
    try {
      await promptEvalApi.createTestCase({
        template_id: template.id,
        name: newCase.name,
        variables: JSON.parse(newCase.variables),
        expected_keys: newCase.expected_keys,
      });
      toast.success('用例已添加');
      const dv = [...new Set((editForm.user_prompt || '').match(/\$\{(\w+)\}/g)?.map((m: string) => m.slice(2, -1)) || [])];
      const vo: Record<string, string> = {};
    dv.forEach((v: any) => { (vo as any)[v] = ''; });
      setNewCase({ name: '', variables: dv.length > 0 ? JSON.stringify(vo) : '{}', expected_keys: '' });
      loadEvalData();
    } catch (e: any) { toast.error('添加失败', e?.message); }
  };

  const handleRunEval = async () => {
    if (!template?.id || !evalCases.length) return;
    try {
      const r = await promptEvalApi.createRun({
        template_id: template.id,
        version_a: '1.0.0', version_b: '1.0.1',
        model: evalModel,
        case_ids: evalCases.map(c => c.id),
      });
      toast.success(`评估已启动: ${(r as any).run_id}`);
      loadEvalData();
    } catch (e: any) { toast.error('评估失败', e?.message); }
  };

  const handleViewRun = async (runId: string) => {
    if (expandedRunId === runId) { setExpandedRunId(null); setRunDetail(null); return; }
    setExpandedRunId(runId);
    setRunDetailLoading(true);
    try {
      const d = await promptEvalApi.getRun(runId);
      setRunDetail(d as any);
    } catch { }
    finally { setRunDetailLoading(false); }
  };

  // ───────── Optimize functions ─────────

  const handleStartOptimize = async () => {
    const up = editForm.user_prompt || editForm.system_prompt || '';
    if (!up) { (toast as any).warn('模板无内容可优化'); return; }
    setOptimizeLoading(true);
    try {
      const r = await promptOptimizeApi.run({ prompt: up, model: optimizeModel });
      const v = { ...(r as any), original: up, instruction: '' };
      setOptimizeVersions([v]);
      setOptimizeActiveVersion(0);
      setOptimizeMessages([{ role: 'assistant', content: 'optimized', versionIndex: 0 }]);
      setTab('compare');
    } catch (e: any) { toast.error('优化失败', e?.message); }
    finally { setOptimizeLoading(false); }
  };

  // Optimize for a specific eval case
  const handleOptimizeForCase = async (caseData: any) => {
    const up = editForm.user_prompt || '';
    if (!up) return;
    // Build optimization prompt targeting this case's low score
    const caseVars = (() => { try { return JSON.parse(caseData.variables || '{}'); } catch { return {}; } })();
    const expectedKeys = caseData.expected_keys || '';
    const optimizationHint = `针对以下测试用例优化 Prompt：
    用例: ${caseData.name}
    输入变量: ${JSON.stringify(caseVars)}
    期望输出包含: ${expectedKeys}
    
    原始 Prompt: ${up}
    
    请优化 Prompt 使其在以上用例中表现更好。保留所有 \${变量} 占位符。`;

    setOptimizeLoading(true);
    try {
      const r = await promptOptimizeApi.run({ prompt: optimizationHint, model: optimizeModel });
      const v = { ...(r as any), original: up, instruction: `针对用例「${caseData.name}」优化` };
      setOptimizeVersions([v]);
      setOptimizeActiveVersion(0);
      setOptimizeMessages([{ role: 'assistant', content: 'optimized', versionIndex: 0 }]);
      setTab('compare');
    } catch (e: any) { toast.error('优化失败', e?.message); }
    finally { setOptimizeLoading(false); }
  };

  const handleRefineOptimize = async (instruction: string) => {
    const cur = optimizeVersions[optimizeActiveVersion];
    const basePrompt = cur?.optimized || editForm.user_prompt || '';
    if (!instruction.trim()) return;
    setOptimizeRefineInput('');
    setOptimizeMessages(prev => [...prev, { role: 'user', content: instruction }]);
    setOptimizeLoading(true);
    try {
      const refinePrompt = `优化指令：${instruction}\n\n当前 Prompt：\n${basePrompt}\n\n请根据上述优化指令改进 Prompt。`;
      const r = await promptOptimizeApi.run({ prompt: refinePrompt, model: optimizeModel });
      const v = { ...(r as any), original: basePrompt, instruction };
      setOptimizeVersions(prev => [...prev, v]);
      const newIdx = optimizeVersions.length;
      setOptimizeActiveVersion(newIdx);
      setOptimizeMessages(prev => [...prev, { role: 'assistant', content: 'optimized', versionIndex: newIdx }]);
    } catch (e: any) { toast.error('优化失败', e?.message); }
    finally { setOptimizeLoading(false); }
  };

  const handleRunTestComparison = async () => {
    const v = optimizeVersions[optimizeActiveVersion];
    if (!v || !template) return;
    const sp = editForm.system_prompt || '';
    const varsObj: Record<string, string> = {};
    testVars.forEach(tv => { if (tv.value) varsObj[tv.name] = tv.value; });
    setTestLoading(true);
    try {
      const [origR, optR] = await Promise.all([
        fetch('/api/core/prompts/app/preview-text', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ system_prompt: sp, user_prompt: v.original, variables: varsObj, model: optimizeModel }),
        }).then(r => r.json()),
        fetch('/api/core/prompts/app/preview-text', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ system_prompt: sp, user_prompt: v.optimized, variables: varsObj, model: optimizeModel }),
        }).then(r => r.json()),
      ]);
      setTestResults({ original: origR.output || '', optimized: optR.output || '' });
    } catch (e: any) { toast.error('测试失败', e?.message); }
    finally { setTestLoading(false); }
  };

  const handleApplyVersion = async () => {
    const v = optimizeVersions[optimizeActiveVersion];
    if (!v?.optimized || !template) return;
    setEditForm((prev: any) => ({ ...prev, user_prompt: v.optimized }));
    // Auto-switch to variables from optimized
    if (v.suggested_vars?.length > 0) {
      const existing = Array.isArray(editForm.variables) ? editForm.variables : [];
      const newVars = v.suggested_vars
        .filter((sv: string) => !existing.some((e: any) => (e.name || e) === sv))
        .map((sv: string) => ({ name: sv, type: 'text', description: '' }));
      setEditForm((prev: any) => ({ ...prev, user_prompt: v.optimized, variables: [...existing, ...newVars] }));
    }
    toast.success('已应用至编辑区，请确认后保存');
    setTab('edit');
  };

  const currentOptimized = optimizeVersions[optimizeActiveVersion];
  const optimizeDiffs = currentOptimized?.original && currentOptimized?.optimized
    ? wordDiff(currentOptimized.original, currentOptimized.optimized) : [];

  if (!template) return null;

  return (
    <Modal open={open} onClose={onClose} title={template?.name || 'Prompt 工作台'} width={1400}>
      <div style={{ minHeight: 'calc(100vh - 200px)' }} className="flex flex-col gap-3">
        {/* Top bar */}
        <div className="flex items-center gap-3 shrink-0">
          <div className="flex-1 flex items-center gap-2 min-w-0">
            <span className="text-sm text-gray-200 font-medium truncate">{editForm.name || template.name}</span>
            <Badge>{editForm.category || template.category || '-'}</Badge>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-40">
              <Select value={tab === 'compare' ? optimizeModel : evalModel} onChange={tab === 'compare' ? setOptimizeModel : setEvalModel} options={
                models.length > 0 ? models : [{ value: 'deepseek-chat', label: 'deepseek-chat' }]
              } className="w-full" />
            </div>
            <div className="flex gap-0.5 bg-dark-bg rounded-lg p-0.5 border border-dark-border">
              {[
                { key: 'edit', label: '编辑' },
                { key: 'eval', label: '评估' },
                { key: 'compare', label: '对比' },
              ].map(t => (
                <button key={t.key} onClick={() => setTab(t.key as any)}
                  className={`px-3 py-1 rounded text-xs transition-colors ${tab === t.key ? 'bg-primary/20 text-primary' : 'text-gray-400 hover:text-gray-200'}`}>
                  {t.label}
                </button>
              ))}
            </div>
            <Button size="sm" onClick={handleSave} loading={saving}>保存</Button>
          </div>
        </div>

        {/* Tab content */}
        <div className="flex-1 min-h-0 overflow-hidden">
          {/* ============ EDIT TAB ============ */}
          {tab === 'edit' && (
            <div className="flex gap-4 h-full">
              {/* Left: Edit form */}
              <div className="flex-1 overflow-y-auto space-y-3 pr-2">
                <div className="grid grid-cols-3 gap-3">
                  <Input label="名称" value={editForm.name || ''} onChange={e => setEditForm({ ...editForm, name: e.target.value })} />
                  <Input label="行业分类" value={editForm.category || ''} onChange={e => setEditForm({ ...editForm, category: e.target.value })} />
                  <Input label="标签(逗号分隔)" value={Array.isArray(editForm.tags) ? editForm.tags.join(',') : ''} onChange={e => setEditForm({ ...editForm, tags: e.target.value.split(',') })} />
                </div>
                <div><label className="text-xs text-gray-400">角色定义</label><Textarea value={editForm.system_prompt || ''} onChange={e => setEditForm({ ...editForm, system_prompt: e.target.value })} rows={2} /></div>
                <div><label className="text-xs text-gray-400">任务指令</label><Textarea value={editForm.user_prompt || ''} onChange={e => setEditForm({ ...editForm, user_prompt: e.target.value })} rows={5} /></div>

                {/* Variable detection */}
                {editForm.user_prompt && (() => {
                  const detected = [...new Set((editForm.user_prompt || '').match(/\$\{(\w+)\}/g)?.map((m: string) => m.slice(2, -1)) || [])];
                  if (!detected.length) return null;
                  const vars = Array.isArray(editForm.variables) ? editForm.variables : [];
                  return (
                    <div>
                      <label className="text-xs text-gray-400">输入变量 <span className="text-gray-600">(自动检测)</span></label>
                      <div className="flex flex-col gap-2 mt-1">
                        {(detected as string[]).map((v: string) => {
                          const existing = vars.find((x: any) => (x.name || x) === v) || {};
                          return (
                            <div key={v} className="bg-dark-bg rounded px-3 py-1.5 text-xs flex items-center gap-2">
                              <code className="text-blue-400 shrink-0">{'${' + v + '}'}</code>
                              <select value={existing.type || 'text'} onChange={e => {
                                const next = vars.filter((x: any) => (x.name || x) !== v);
                                next.push({ name: v, type: e.target.value, description: existing.description || '' });
                                setEditForm({ ...editForm, variables: next });
                              }} className="text-xs bg-dark-bg border-0 text-gray-400 w-16 outline-none">
                                <option value="text">文本</option>
                                <option value="number">数字</option>
                                <option value="date">日期</option>
                                <option value="select">选项</option>
                              </select>
                              <input value={existing.description || ''} onChange={e => {
                                const next = vars.filter((x: any) => (x.name || x) !== v);
                                next.push({ name: v, type: existing.type || 'text', description: e.target.value });
                                setEditForm({ ...editForm, variables: next });
                              }} placeholder="变量说明..." className="flex-1 text-xs bg-dark-bg border-0 text-gray-400 placeholder-gray-600 outline-none min-w-0" />
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  );
                })()}

                <div><label className="text-xs text-gray-400">输出格式</label><Textarea value={editForm.assistant_prompt || ''} onChange={e => setEditForm({ ...editForm, assistant_prompt: e.target.value })} rows={2} /></div>
                <div><label className="text-xs text-gray-400">示例 <span className="text-gray-600">(输入→输出参考)</span></label><Textarea value={editForm.examples || ''} onChange={e => setEditForm({ ...editForm, examples: e.target.value })} rows={3} placeholder={(() => {
                  const d = [...new Set((editForm.user_prompt || '').match(/\$\{(\w+)\}/g)?.map((m: string) => m.slice(2, -1)) || [])];
                  const sv: Record<string, string> = {};
                  d.slice(0, 3).forEach((v: any) => { (sv as any)[v] = v + '示例'; });
                  return d.length > 0 ? `输入：${JSON.stringify(sv)}\n输出：（在此填写期望的输出效果或参考示例）` : '输入：{"变量1":"示例值"}\n输出：（在此填写期望的输出效果）';
                })()} /></div>
                <div><label className="text-xs text-gray-400">约束 <span className="text-gray-600">(不能做什么)</span></label><Textarea value={editForm.constraints || ''} onChange={e => setEditForm({ ...editForm, constraints: e.target.value })} rows={2} placeholder="· 日期使用yyyy年mm月dd日格式\n· 不使用昵称" /></div>
                <div>
                  <label className="text-xs text-gray-400">场景标签 <span className="text-gray-600">(多选)</span></label>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {TAGS_LIST.map((tag: string) => {
                      const selected = (editForm.scenario_tags || []).includes(tag);
                      return (
                        <button key={tag} type="button" onClick={() => {
                          const cur = editForm.scenario_tags || [];
                          const next = selected ? cur.filter((t: string) => t !== tag) : [...cur, tag];
                          setEditForm({ ...editForm, scenario_tags: next });
                        }} className={`px-2 py-0.5 rounded text-[10px] border transition-colors ${selected ? 'bg-primary/20 text-primary border-primary/30' : 'text-gray-500 border-dark-border hover:text-gray-300'}`}>{tag}</button>
                      );
                    })}
                  </div>
                </div>
                <div className="flex gap-2 pt-2">
                  <Button size="sm" onClick={handleSave} loading={saving}>{editForm.id ? '保存' : '创建'}</Button>
                </div>
              </div>
              {/* Right: Preview panel */}
              <div className="w-80 flex-shrink-0 flex flex-col gap-3 border-l border-dark-border pl-4 overflow-y-auto">
                <div className="text-xs text-gray-400 uppercase tracking-wider font-medium">快速预览</div>
                <div className="space-y-2">
                  <div><label className="text-[10px] text-gray-500 block mb-0.5">模型</label><Select value={previewModel} onChange={setPreviewModel} options={
                    models.length > 0 ? models : [{ value: 'deepseek-chat', label: 'deepseek-chat' }]
                  } className="w-full" /></div>
                  <div>
                    <label className="text-[10px] text-gray-500 block mb-0.5">测试变量</label>
                    <div className="space-y-1">
                      {testVars.map((tv, i) => (
                        <div key={i} className="flex items-center gap-1">
                          <code className="text-[10px] text-blue-400 w-16 shrink-0">{'${' + tv.name + '}'}</code>
                          <input value={tv.value} onChange={e => { const n = [...testVars]; n[i] = { ...n[i], value: e.target.value }; setTestVars(n); }}
                            className="flex-1 bg-dark-bg border border-dark-border rounded px-2 py-1 text-[10px] text-gray-200 placeholder-gray-600 outline-none" placeholder="值..." />
                        </div>
                      ))}
                      {testVars.length === 0 && <div className="text-[10px] text-gray-600">模板无变量</div>}
                    </div>
                  </div>
                  <div className="flex gap-1.5">
                    <Button size="sm" onClick={handleRun} loading={testLoading} className="flex-1">▶ 运行</Button>
                    <Button size="sm" onClick={handleStartOptimize} loading={optimizeLoading} className="flex-1">🤖 优化</Button>
                  </div>
                  {runOutput && (
                    <div>
                      <label className="text-[10px] text-gray-500 block mb-0.5">运行结果</label>
                      <pre className="text-xs text-gray-300 whitespace-pre-wrap bg-dark-bg border border-dark-border rounded-lg p-2 max-h-48 overflow-y-auto">{runOutput}</pre>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* ============ EVAL TAB ============ */}
          {tab === 'eval' && (
            <div className="flex flex-col gap-3 h-full overflow-y-auto">
              {/* Template preview (collapsible) */}
              <div className="border border-dark-border rounded-lg shrink-0">
                <button onClick={() => setTemplatePreviewExpanded(!templatePreviewExpanded)}
                  className="flex items-center justify-between w-full px-3 py-2 text-xs text-gray-400 hover:text-gray-200 bg-dark-bg rounded-t-lg">
                  <span className="flex items-center gap-2">
                    📋 模板预览
                    <span className="text-[10px] text-gray-600">{editForm.system_prompt ? '含角色定义' : ''}</span>
                  </span>
                  <span className="text-[10px]">{templatePreviewExpanded ? '收起 ▲' : '展开 ▼'}</span>
                </button>
                {templatePreviewExpanded && (
                  <div className="p-3 space-y-2 border-t border-dark-border text-xs">
                    {editForm.system_prompt && (
                      <div>
                        <div className="text-[10px] text-gray-500 mb-0.5">角色定义</div>
                        <pre className="text-xs text-gray-400 whitespace-pre-wrap">{editForm.system_prompt}</pre>
                      </div>
                    )}
                    <div>
                      <div className="text-[10px] text-gray-500 mb-0.5">任务指令</div>
                      <pre className="text-xs text-gray-300 whitespace-pre-wrap">{editForm.user_prompt || ''}</pre>
                    </div>
                    {editForm.examples && (
                      <div>
                        <div className="text-[10px] text-gray-500 mb-0.5">示例</div>
                        <pre className="text-xs text-gray-400 whitespace-pre-wrap">{editForm.examples}</pre>
                      </div>
                    )}
                    {editForm.constraints && (
                      <div>
                        <div className="text-[10px] text-gray-500 mb-0.5">约束</div>
                        <pre className="text-xs text-gray-400 whitespace-pre-wrap">{editForm.constraints}</pre>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Config bar */}
              <div className="flex items-center gap-3 bg-dark-bg rounded-lg p-2.5 shrink-0">
                <div className="flex-1 flex items-center gap-3 text-[10px] text-gray-500">
                  <span>用例 <span className="text-gray-200">{evalCases.length}</span></span>
                  {evalRuns.length > 0 && (() => {
                    const done = evalRuns.filter((r: any) => r.status === 'done');
                    const avgScore = done.length > 0 ? (done.reduce((s: number, r: any) => s + (r.avg_score_a || 0), 0) / done.length).toFixed(1) : '-';
                    return <span>均分 <span className="text-gray-200">{avgScore}</span></span>;
                  })()}
                </div>
                <Button size="sm" onClick={loadEvalData}>🔄</Button>
                <Button size="sm" onClick={handleRunEval} disabled={!evalCases.length}>▶ 运行评估</Button>
              </div>

              {/* Add case */}
              <div className="flex gap-2 shrink-0">
                <input value={newCase.name} onChange={e => setNewCase({ ...newCase, name: e.target.value })}
                  className="flex-[2] bg-dark-bg border border-dark-border rounded px-3 py-2 text-xs text-gray-200 placeholder-gray-600 outline-none"
                  placeholder="用例名称" />
                <input value={newCase.variables} onChange={e => setNewCase({ ...newCase, variables: e.target.value })}
                  className="flex-[2] bg-dark-bg border border-dark-border rounded px-3 py-2 text-xs text-gray-200 placeholder-gray-600 outline-none"
                  placeholder='{"var":"value"}' />
                <input value={newCase.expected_keys} onChange={e => setNewCase({ ...newCase, expected_keys: e.target.value })}
                  className="flex-1 bg-dark-bg border border-dark-border rounded px-3 py-2 text-xs text-gray-200 placeholder-gray-600 outline-none"
                  placeholder="关键词1,关键词2" />
                <Button size="sm" onClick={handleAddCase} disabled={!newCase.name}>+ 添加</Button>
              </div>

              {/* Cases grid */}
              {evalLoading ? (
                <div className="text-center py-12 text-gray-500 text-sm">加载中...</div>
              ) : evalCases.length === 0 ? (
                <div className="text-center py-12 text-gray-500 text-sm border border-dashed border-dark-border rounded-lg">
                  暂无测试用例<br/><span className="text-[10px]">添加测试用例后可运行评估，低分用例支持一键 AI 优化</span>
                </div>
              ) : (
                <div className="grid grid-cols-3 gap-2">
                  {evalCases.map((c: any, i: number) => {
                    let vars: Record<string, string> = {};
                    try { vars = JSON.parse(c.variables || '{}'); } catch { }
                    // Check latest run result for this case
                    const latestDone = evalRuns.filter((r: any) => r.status === 'done').reverse()[0];
                    let caseResult: any = null;
                    if (latestDone && expandedRunId === latestDone.id && runDetail?.results_json) {
                      let results: any[] = [];
                      try { results = typeof runDetail.results_json === 'string' ? JSON.parse(runDetail.results_json) : runDetail.results_json; } catch { }
                      caseResult = results.find((res: any) => res.case_id === c.id);
                    }
                    return (
                      <div key={c.id} className="bg-dark-bg border border-dark-border rounded-lg p-2.5 relative group">
                        <button onClick={async () => { await promptEvalApi.deleteTestCase(c.id); loadEvalData(); }}
                          className="absolute top-1.5 right-1.5 text-gray-600 hover:text-red-400 text-[10px] opacity-0 group-hover:opacity-100 transition-opacity">✕</button>
                        <div className="text-xs text-gray-200 font-medium mb-1.5 truncate pr-4">#{i + 1} {c.name}</div>
                        <div className="space-y-0.5 mb-1.5">
                          {Object.entries(vars).map(([k, v]) => (
                            <div key={k} className="flex items-center gap-1 text-[10px]">
                              <code className="text-blue-400 shrink-0">{'${' + k + '}'}</code>
                              <span className="text-gray-500">→</span>
                              <span className="text-gray-300 truncate">{String(v)}</span>
                            </div>
                          ))}
                        </div>
                        {c.expected_keys && (
                          <div className="flex flex-wrap items-center gap-1 mb-1.5">
                            <span className="text-[9px] text-gray-600">期望:</span>
                            {c.expected_keys.split(',').filter(Boolean).map((k: string) => (
                              <span key={k} className="text-[9px] bg-gray-800 text-gray-400 px-1.5 py-0.5 rounded">{k.trim()}</span>
                            ))}
                          </div>
                        )}
                        {caseResult && (
                          <div className="flex items-center gap-2 pt-1.5 border-t border-dark-border">
                            <span className={`text-xs font-medium ${caseResult.score >= 8 ? 'text-green-400' : caseResult.score >= 6 ? 'text-yellow-400' : 'text-red-400'}`}>
                              {caseResult.score}/10
                            </span>
                            {caseResult.score < 8 && (
                              <button onClick={() => handleOptimizeForCase(c)}
                                className="text-[10px] text-blue-400 hover:underline">✨ 优化</button>
                            )}
                          </div>
                        )}
                        {!caseResult && (
                          <div className="text-[10px] text-gray-600 pt-1.5 border-t border-dark-border">未评估</div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Run results */}
              {evalRuns.length > 0 && (
                <div className="shrink-0">
                  <div className="text-xs text-gray-400 uppercase tracking-wider font-medium mb-2">评估历史</div>
                  <div className="space-y-1.5">
                    {evalRuns.map((r: any) => (
                      <div key={r.id} className="border border-dark-border rounded-lg overflow-hidden">
                        <button onClick={() => handleViewRun(r.id)}
                          className="flex items-center gap-3 w-full px-3 py-2 hover:bg-dark-bg/50 text-left">
                          <span className="text-[10px] text-gray-500 font-mono w-20 shrink-0">{r.id?.substring(0, 12)}</span>
                          <span className="text-[10px] text-gray-400 w-28 shrink-0">{new Date((r.created_at || 0) * 1000).toLocaleString().replace(/ 202\d/, '')}</span>
                          <span className="text-[10px] text-gray-500 w-24 shrink-0 truncate">{r.model}</span>
                          <span className="flex-1 text-right">
                            {r.status === 'done'
                              ? <span className="text-xs text-green-400">{r.avg_score_a || '-'}/10</span>
                              : <span className="text-[10px] text-yellow-400">⏳ 运行中</span>}
                          </span>
                          <span className="text-[10px] text-gray-600">{expandedRunId === r.id ? '▲' : '▼'}</span>
                        </button>
                        {expandedRunId === r.id && (
                          <div className="border-t border-dark-border p-3 space-y-3 bg-gray-900/30">
                            {runDetailLoading ? (
                              <div className="text-center py-4 text-gray-500 text-xs">加载中...</div>
                            ) : runDetail?.results_json ? (
                              (() => {
                                let results: any[] = [];
                                try { results = typeof runDetail.results_json === 'string' ? JSON.parse(runDetail.results_json) : runDetail.results_json; } catch { }
                                return results.map((res: any, ri: number) => {
                                  const tc = evalCases.find(c => c.id === res.case_id);
                                   const expectedKeys = (tc?.expected_keys || '').split(',').filter(Boolean).map((k: any) => k.trim().toLowerCase());
                                  return (
                                    <div key={ri} className="bg-dark-bg border border-dark-border rounded-lg p-3">
                                      <div className="flex items-start gap-4">
                                        <div className="flex-1 min-w-0">
                                          <div className="flex items-center gap-2 mb-1">
                                            <span className="text-xs text-gray-200 font-medium">{tc?.name || res.case_id}</span>
                                            {res.score < 8 && (
                                              <button onClick={() => handleOptimizeForCase(tc || res)}
                                                className="text-[10px] text-blue-400 hover:underline">✨ 针对此例优化</button>
                                            )}
                                          </div>
                                          {res.error ? (
                                            <div className="text-xs text-red-400">{res.error}</div>
                                          ) : (
                                            <pre className="text-xs text-gray-300 whitespace-pre-wrap leading-relaxed">{res.output}</pre>
                                          )}
                                        </div>
                                        <div className="w-32 shrink-0 space-y-1">
                                          <div className={`text-xs font-medium ${res.score >= 8 ? 'text-green-400' : res.score >= 6 ? 'text-yellow-400' : 'text-red-400'}`}>
                                            评分: {res.score}/10
                                          </div>
                                          {expectedKeys.length > 0 && (
                                            <div className="space-y-0.5">
                                              {expectedKeys.map((k: string) => {
                                                const hit = (res.output || '').toLowerCase().includes(k);
                                                return (
                                                  <div key={k} className={`text-[10px] flex items-center gap-1 ${hit ? 'text-green-400' : 'text-red-400'}`}>
                                                    <span>{hit ? '✓' : '✗'}</span><span>{k}</span>
                                                  </div>
                                                );
                                              })}
                                            </div>
                                          )}
                                        </div>
                                      </div>
                                    </div>
                                  );
                                });
                              })()
                            ) : (
                              <div className="text-center py-4 text-gray-500 text-xs">无法加载结果</div>
                            )}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ============ COMPARE TAB ============ */}
          {tab === 'compare' && (
            <div className="flex flex-col gap-3 h-full overflow-y-auto">
              {optimizeMessages.length === 0 ? (
                <div className="text-center py-12 text-gray-500 text-sm">
                  请在「编辑」标签中点击「AI 优化」，或在「评估」标签中对低分用例点击「✨ 优化」
                </div>
              ) : (
                <>
                  {/* Toolbar */}
                  <div className="flex items-center gap-3 bg-dark-bg rounded-lg p-2.5 shrink-0">
                    <div className="flex items-center gap-2 flex-1">
                      {optimizeVersions.length > 1 && (
                        <div className="flex gap-1">
                          {optimizeVersions.map((_v, i) => (
                            <button key={i} onClick={() => setOptimizeActiveVersion(i)}
                              className={`px-2 py-0.5 rounded text-[10px] ${i === optimizeActiveVersion ? 'bg-primary/20 text-primary' : 'text-gray-500 hover:text-gray-300'}`}>V{i + 1}</button>
                          ))}
                        </div>
                      )}
                      {currentOptimized?.score_after != null && (
                        <span className="text-xs text-green-400">{currentOptimized.score_before ?? '?'}→{currentOptimized.score_after}/10</span>
                      )}
                    </div>
                    <Button size="sm" onClick={handleApplyVersion} className="bg-green-600 hover:bg-green-700">应用至编辑区</Button>
                  </div>

                  {/* Dual-panel comparison */}
                  <div className="grid grid-cols-2 gap-4 min-h-0 overflow-y-auto">
                    <div className="flex flex-col min-h-0">
                      <div className="flex items-center gap-2 mb-1.5">
                        <span className="text-xs text-gray-400 uppercase tracking-wider font-medium">原提示词</span>
                        {currentOptimized?.score_before != null && <Badge className="text-[10px] bg-yellow-500/20 text-yellow-400">{currentOptimized.score_before}/10</Badge>}
                      </div>
                      <div className="flex-1 overflow-y-auto bg-dark-bg border border-dark-border rounded-lg p-3 text-xs leading-relaxed whitespace-pre-wrap">
                        {editForm.system_prompt && (
                          <div className="mb-3">
                            <div className="text-[10px] text-gray-500 mb-0.5">角色定义</div>
                            <span className="text-gray-500">{editForm.system_prompt}</span>
                          </div>
                        )}
                        <div>
                          <div className="text-[10px] text-gray-500 mb-0.5">任务指令</div>
                          {optimizeDiffs.map((d, di) => (
                            <span key={di} className={d.type === 'add' ? 'hidden' : d.type === 'del' ? 'bg-red-500/20 text-red-300 line-through rounded-sm px-0.5' : 'text-gray-300'}>{d.text}</span>
                          ))}
                        </div>
                      </div>
                    </div>
                    <div className="flex flex-col min-h-0">
                      <div className="flex items-center gap-2 mb-1.5">
                        <span className="text-xs text-green-400 uppercase tracking-wider font-medium">优化后提示词</span>
                        {currentOptimized?.score_after != null && <Badge className="text-[10px] bg-green-500/20 text-green-400">{currentOptimized.score_after}/10</Badge>}
                      </div>
                      <div className="flex-1 overflow-y-auto bg-dark-bg border border-dark-border rounded-lg p-3 text-xs leading-relaxed whitespace-pre-wrap">
                        {editForm.system_prompt && (
                          <div className="mb-3">
                            <div className="text-[10px] text-gray-500 mb-0.5">角色定义</div>
                            <span className="text-gray-500">{editForm.system_prompt}</span>
                          </div>
                        )}
                        <div>
                          <div className="text-[10px] text-gray-500 mb-0.5">任务指令</div>
                          {optimizeDiffs.map((d, di) => (
                            <span key={di} className={d.type === 'del' ? 'hidden' : d.type === 'add' ? 'bg-green-500/20 text-green-300 rounded-sm px-0.5' : 'text-gray-300'}>{d.text}</span>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Test comparison */}
                  {testVars.length > 0 && (
                    <div className="border border-dark-border rounded-lg shrink-0">
                      <div className="flex items-center px-3 py-2 bg-dark-bg rounded-t-lg justify-between">
                        <span className="text-xs text-gray-400 uppercase tracking-wider font-medium">测试对比</span>
                        <Button size="sm" onClick={handleRunTestComparison} loading={testLoading}
                          disabled={!testVars.some(tv => tv.value)}>▶ 运行测试对比</Button>
                      </div>
                      <div className="p-3 space-y-2">
                        <div className="flex items-center gap-2 flex-wrap">
                          {testVars.map((tv, i) => (
                            <div key={i} className="flex items-center gap-1 bg-gray-900 rounded px-2 py-1">
                              <code className="text-[10px] text-blue-400">{'${' + tv.name + '}'}</code>
                              <input value={tv.value} onChange={e => { const n = [...testVars]; n[i] = { ...n[i], value: e.target.value }; setTestVars(n); }}
                                className="w-20 bg-transparent text-[10px] text-gray-200 placeholder-gray-600 outline-none" placeholder="值..." />
                            </div>
                          ))}
                        </div>
                        {testResults && (
                          <div className="grid grid-cols-2 gap-2">
                            <div>
                              <div className="text-[10px] text-gray-500 mb-1">原版输出</div>
                              <pre className="text-xs text-gray-300 whitespace-pre-wrap bg-dark-bg rounded-lg p-2 max-h-32 overflow-y-auto border border-dark-border">{testResults.original}</pre>
                            </div>
                            <div>
                              <div className="text-[10px] text-green-400 mb-1">优化版输出</div>
                              <pre className="text-xs text-green-300 whitespace-pre-wrap bg-dark-bg rounded-lg p-2 max-h-32 overflow-y-auto border border-green-500/20">{testResults.optimized}</pre>
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Changes & suggested vars */}
                  {(currentOptimized?.changes?.length > 0 || currentOptimized?.suggested_vars?.length > 0) && (
                    <div className="flex gap-4 text-[11px] shrink-0 bg-dark-bg rounded-lg p-3">
                      {currentOptimized.changes?.length > 0 && (
                        <div className="flex-1">
                          <div className="text-[10px] text-gray-500 mb-1 uppercase tracking-wider">改动详情</div>
                          <div className="flex flex-wrap gap-x-4 gap-y-0.5">
                            {currentOptimized.changes.map((c: string, ci: number) => (
                              <span key={ci} className="text-gray-400 flex items-center gap-1"><span className="text-green-400 text-[10px]">✓</span>{c}</span>
                            ))}
                          </div>
                        </div>
                      )}
                      {currentOptimized?.suggested_vars?.length > 0 && (
                        <div className="w-56">
                          <div className="text-[10px] text-gray-500 mb-1 uppercase tracking-wider">建议新增变量</div>
                          <div className="flex flex-wrap gap-1">
                            {currentOptimized.suggested_vars.map((sv: string) => (
                              <code key={sv} className="text-[10px] text-blue-400 bg-gray-900 px-1 py-0.5 rounded">{'${' + sv + '}'}</code>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Collapsible chat */}
                  <div className="border border-dark-border rounded-lg shrink-0">
                    <button onClick={() => setChatExpanded(!chatExpanded)}
                      className="flex items-center justify-between w-full px-3 py-2 text-xs text-gray-400 hover:text-gray-200 bg-dark-bg rounded-t-lg">
                      <span>对话微调 {optimizeMessages.filter(m => m.role === 'user').length > 0 ? `(${optimizeMessages.filter(m => m.role === 'user').length})` : ''}</span>
                      <span className="text-[10px]">{chatExpanded ? '收起 ▲' : '展开 ▼'}</span>
                    </button>
                    {chatExpanded && (
                      <div className="p-3 space-y-2 border-t border-dark-border">
                        <div className="max-h-40 overflow-y-auto space-y-2">
                          {optimizeMessages.map((msg, i) => (
                            msg.role === 'user' ? (
                              <div key={i} className="flex justify-end">
                                <div className="bg-primary/10 border border-primary/20 rounded px-2 py-1 text-xs text-gray-200 max-w-[80%]">{msg.content}</div>
                              </div>
                            ) : (
                              <div key={i} className="flex items-center gap-2 text-[11px]">
                                <span className="text-[10px] text-gray-600">AI #{((msg.versionIndex ?? 0) + 1)}</span>
                                <span className="text-gray-400">{(() => { const vi = msg.versionIndex ?? 0; const vv = optimizeVersions[vi]; return vv?.analysis || (vv?.score_after != null ? `评分 ${vv.score_before ?? '?'}→${vv.score_after}/10` : ''); })()}</span>
                                <button onClick={() => { const vi = msg.versionIndex ?? 0; setOptimizeActiveVersion(vi); }} className="text-blue-400 hover:underline text-[10px]">查看</button>
                              </div>
                            )
                          ))}
                        </div>
                        <div className="flex gap-1.5">
                          {['更简洁', '更正式', '更详细', '更专业'].map(q => (
                            <button key={q} onClick={() => handleRefineOptimize(q)} className="text-[10px] px-2 py-0.5 rounded border border-dark-border text-gray-400 hover:text-gray-200">{q}</button>
                          ))}
                        </div>
                        <div className="flex gap-2">
                          <input value={optimizeRefineInput} onChange={e => setOptimizeRefineInput(e.target.value)}
                            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleRefineOptimize(optimizeRefineInput); } }}
                            placeholder="输入优化指令..." className="flex-1 bg-dark-bg border border-dark-border rounded px-3 py-1.5 text-xs text-gray-200 placeholder-gray-600 outline-none" />
                          <Button size="sm" onClick={() => handleRefineOptimize(optimizeRefineInput)} disabled={!optimizeRefineInput.trim()}>→</Button>
                        </div>
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
};

export default PromptWorkbench;
