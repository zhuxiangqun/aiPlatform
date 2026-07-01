import React, { useEffect, useState } from 'react';
import { Plus, Trash2, Play, Square, RefreshCw } from 'lucide-react';
import { Button, Modal, toast, Input, Select } from '../../../components/ui';
import { finetuneApi } from '../../../services';

const FineTunePage: React.FC = () => {
  const [tab, setTab] = useState<'datasets' | 'jobs' | 'training' | 'distill' | 'scratch' | 'models'>('datasets');
  const [datasets, setDatasets] = useState<any[]>([]);
  const [jobs, setJobs] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [providers, setProviders] = useState<any[]>([]);

  // ── Dataset state ──
  const [dsModalOpen, setDsModalOpen] = useState(false);
  const [dsName, setDsName] = useState('');
  const [dsDesc, setDsDesc] = useState('');
  const [importModalOpen, setImportModalOpen] = useState(false);
  const [importDsId, setImportDsId] = useState('');
  const [importContent, setImportContent] = useState('');
  const [previewModalOpen, setPreviewModalOpen] = useState(false);
  const [previewData, setPreviewData] = useState<any>(null);

  // ── Job state ──  
  const [jobModalOpen, setJobModalOpen] = useState(false);
  const [jobBaseModel, setJobBaseModel] = useState('');
  const [jobDatasetId, setJobDatasetId] = useState('');
  const [jobTemplate, setJobTemplate] = useState('general');
  const [jobCustomName, setJobCustomName] = useState('');
  const [jobProvider, setJobProvider] = useState('deepseek');
  const [loraRank, setLoraRank] = useState('16');
  const [loraAlpha, setLoraAlpha] = useState('32');

  // ── Training state ──
  const [trainBaseModel, setTrainBaseModel] = useState('');
  const [trainDatasetId, setTrainDatasetId] = useState('');
  const [trainIterations, setTrainIterations] = useState('1');
  const [trainEpisodes, setTrainEpisodes] = useState('8');
  const [trainResult, setTrainResult] = useState<any>(null);
  const [trainRunning, setTrainRunning] = useState(false);

  // ── Distill state ──
  const [distillTeacher, setDistillTeacher] = useState('');
  const [distillStudent, setDistillStudent] = useState('');
  const [distillDatasetId, setDistillDatasetId] = useState('');
  const [distillTemp, setDistillTemp] = useState('2.0');
  const [distillAlpha, setDistillAlpha] = useState('0.5');
  const [distillMode, setDistillMode] = useState('lora');
  const [distillJobs, setDistillJobs] = useState<any[]>([]);
  const [distillRunning, setDistillRunning] = useState(false);

  // ── Scratch state ──
  const [scratchArch, setScratchArch] = useState('gpt2');
  const [scratchDataset, setScratchDataset] = useState('');
  const [scratchOutputName, setScratchOutputName] = useState('');
  const [scratchEpochs, setScratchEpochs] = useState('3');
  const [scratchBatchSize, setScratchBatchSize] = useState('4');
  const [scratchLR, setScratchLR] = useState('5e-5');
  const [scratchJobs, setScratchJobs] = useState<any[]>([]);
  const [scratchRunning, setScratchRunning] = useState(false);
  const [models, setModels] = useState<any[]>([]);
  const [baseModelOptions, setBaseModelOptions] = useState<{value:string,label:string}[]>([
    {value:'deepseek-chat',label:'deepseek-chat'},
    {value:'deepseek-v4-pro',label:'deepseek-v4-pro'}
  ]);

  const fetchDatasets = async () => {
    try {
      const res = await finetuneApi.listDatasets({ limit: 50 });
      setDatasets(res.datasets || []);
    } catch { }
  };

  const fetchJobs = async () => {
    try {
      const res = await finetuneApi.listJobs({ limit: 50 });
      setJobs(res.jobs || []);
    } catch { }
  };

  const fetchProviders = async () => {
    try {
      const res = await finetuneApi.listProviders();
      setProviders(res.providers || []);
    } catch { }
  };

  useEffect(() => { fetchDatasets(); fetchJobs(); fetchProviders(); }, []);

  const statusBadge = (status: string) => {
    const map: Record<string, string> = {
      ready: 'bg-green-900/40 text-green-300', error: 'bg-red-900/40 text-red-300',
      completed: 'bg-green-900/40 text-green-300', failed: 'bg-red-900/40 text-red-300',
      queued: 'bg-blue-900/40 text-blue-300', training: 'bg-yellow-900/40 text-yellow-300',
      uploading: 'bg-purple-900/40 text-purple-300', validating: 'bg-blue-900/40 text-blue-300',
      cancelled: 'bg-gray-900/40 text-gray-400', validating_model: 'bg-purple-900/40 text-purple-300',
    };
    return `text-xs px-2 py-0.5 rounded ${map[status] || 'bg-gray-900/40 text-gray-400'}`;
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-100">模型微调</h1>
          <p className="text-sm text-gray-500 mt-1">管理训练数据集和微调作业</p>
        </div>
      </div>

      {/* ── Tabs ── */}
      <div className="flex gap-2 border-b border-dark-border pb-2">
        {(['datasets', 'jobs', 'training', 'distill', 'scratch', 'models'] as const).map(t => (
          <button key={t} onClick={() => { setTab(t); if (t === 'models') fetch('/api/core/finetune/providers').then(r=>r.json()).then(d => setModels(d.providers || [])); }}
            className={`px-4 py-2 text-sm rounded-t-lg transition-colors ${
              tab === t ? 'bg-dark-card text-gray-100 border border-dark-border border-b-dark-card' : 'text-gray-500 hover:text-gray-300'
            }`}>
            {t === 'datasets' ? '📊 数据集' : t === 'jobs' ? '⚙️ 微调作业' : t === 'training' ? '🧠 RL训练' : t === 'distill' ? '🔮 蒸馏' : t === 'scratch' ? '🏗️ 从零训练' : '📋 模型注册表'}
          </button>
        ))}
      </div>

      {/* ── Datasets Tab ── */}
      {tab === 'datasets' && (
        <div className="space-y-4">
          <div className="flex gap-2">
            <Button icon={<Plus className="w-4 h-4" />} onClick={() => { setDsName(''); setDsDesc(''); setDsModalOpen(true); }}>创建数据集</Button>
            <Button variant="secondary" icon={<RefreshCw className="w-4 h-4" />} onClick={fetchDatasets}>刷新</Button>
          </div>
          <div className="bg-dark-card border border-dark-border rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-dark-border text-gray-400">
                  <th className="text-left p-3">名称</th>
                  <th className="text-left p-3">样本数</th>
                  <th className="text-left p-3">状态</th>
                  <th className="text-left p-3">创建时间</th>
                  <th className="text-right p-3">操作</th>
                </tr>
              </thead>
              <tbody>
                {datasets.map(ds => (
                  <tr key={ds.id} className="border-b border-dark-border/30 hover:bg-dark-bg/50">
                    <td className="p-3 text-gray-200">{ds.name}</td>
                    <td className="p-3 text-gray-400">{ds.sample_count}</td>
                    <td className="p-3"><span className={statusBadge(ds.status)}>{ds.status}</span></td>
                    <td className="p-3 text-gray-500 text-xs">{ds.created_at ? new Date(ds.created_at * 1000).toLocaleDateString() : '-'}</td>
                    <td className="p-3 text-right flex gap-1 justify-end">
                      <Button variant="secondary" size="sm" onClick={() => { setImportDsId(ds.id); setImportContent(''); setImportModalOpen(true); }}>导入</Button>
                      <Button variant="secondary" size="sm" onClick={async () => { try { const r = await finetuneApi.previewDataset(ds.id); setPreviewData(r); setPreviewModalOpen(true); } catch (e: any) { toast.error('预览失败', e?.message); } }}>预览</Button>
                      <Button variant="secondary" size="sm" onClick={async () => { if (confirm('确定删除？')) { await finetuneApi.deleteDataset(ds.id); fetchDatasets(); } }}>
                        <Trash2 className="w-3 h-3" />
                      </Button>
                    </td>
                  </tr>
                ))}
                {datasets.length === 0 && <tr><td colSpan={5} className="p-6 text-center text-gray-500">暂无数据集</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Jobs Tab ── */}
      {tab === 'jobs' && (
        <div className="space-y-4">
          <div className="flex gap-2">
            <Button icon={<Play className="w-4 h-4" />} onClick={() => { setJobBaseModel(''); setJobDatasetId(''); setJobCustomName(''); setJobTemplate('general'); setJobModalOpen(true); }}>提交微调</Button>
            <Button variant="secondary" icon={<RefreshCw className="w-4 h-4" />} onClick={fetchJobs}>刷新</Button>
          </div>

          {/* Provider info */}
          {providers.length > 0 && (
            <div className="flex gap-3 flex-wrap">
              {providers.map(p => (
                <div key={p.name} className={`p-3 rounded-lg border text-xs ${p.available ? 'border-green-500/30 bg-green-900/10' : 'border-red-500/30 bg-red-900/10'}`}>
                  <div className="text-gray-200 font-medium">{p.display_name}</div>
                  <div className="text-gray-500 mt-1">配额: {p.quota_used}/{p.quota_total}</div>
                  <div className="text-gray-600">{p.estimated_cost_per_job}</div>
                </div>
              ))}
            </div>
          )}

          <div className="bg-dark-card border border-dark-border rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-dark-border text-gray-400">
                  <th className="text-left p-3">模型名</th>
                  <th className="text-left p-3">数据集</th>
                  <th className="text-left p-3">状态</th>
                  <th className="text-left p-3">模板</th>
                  <th className="text-right p-3">操作</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map(j => (
                   <tr key={j.id} className="border-b border-dark-border/30 hover:bg-dark-bg/50">
                    <td className="p-3">
                      <div className="text-gray-200 text-xs">{j.result_model || j.base_model}</div>
                      <div className="text-gray-500 text-[10px]">{j.base_model} → {j.provider}</div>
                      {j.progress && j.progress.status === 'training' && (
                        <div className="mt-1">
                          <div className="w-full bg-dark-border/40 rounded h-1.5">
                            <div className="bg-primary h-1.5 rounded transition-all"
                              style={{width: `${j.progress.total_iters > 0 ? (j.progress.current_iter / j.progress.total_iters) * 100 : 0}%`}} />
                          </div>
                          <div className="flex gap-3 text-[9px] text-gray-500 mt-0.5">
                            <span>🔁 {j.progress.current_iter}/{j.progress.total_iters}</span>
                            {j.progress.loss && <span>📉 {j.progress.loss.toFixed(2)}</span>}
                            {j.progress.tokens_per_sec > 0 && <span>⚡ {j.progress.tokens_per_sec} tok/s</span>}
                            {j.progress.estimated_remaining_sec > 0 && <span>⏱ 剩余 {Math.round(j.progress.estimated_remaining_sec / 60)}min</span>}
                          </div>
                        </div>
                      )}
                    </td>
                    <td className="p-3 text-gray-400 text-xs">{j.dataset_name}</td>
                    <td className="p-3"><span className={statusBadge(j.status)}>{j.status}</span></td>
                    <td className="p-3 text-gray-500 text-xs">{j.template}</td>
                    <td className="p-3 text-right">
                      {['queued','training','validating','uploading'].includes(j.status) && (
                        <Button variant="secondary" size="sm" onClick={async () => { await finetuneApi.cancelJob(j.id); fetchJobs(); toast.success('已取消'); }}>
                          <Square className="w-3 h-3" />
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
                {jobs.length === 0 && <tr><td colSpan={5} className="p-6 text-center text-gray-500">暂无微调作业</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Create Dataset Modal ── */}
      <Modal open={dsModalOpen} onClose={() => setDsModalOpen(false)} title="创建数据集">
        <div className="space-y-4">
          <Input label="名称" value={dsName} onChange={(e: any) => setDsName(e.target.value)} />
          <Input label="描述" value={dsDesc} onChange={(e: any) => setDsDesc(e.target.value)} />
          <Button variant="primary" onClick={async () => {
            if (!dsName.trim()) return toast.error('请输入名称');
            await finetuneApi.createDataset({ name: dsName, description: dsDesc });
            setDsModalOpen(false); fetchDatasets(); toast.success('创建成功');
          }}>创建</Button>
        </div>
      </Modal>

      {/* ── Import Dataset Modal ── */}
      <Modal open={importModalOpen} onClose={() => setImportModalOpen(false)} title="导入 JSONL 数据">
        <div className="space-y-4">
          <div className="text-xs text-gray-400">每行一个 JSON 对象，格式：{`{"messages":[{"role":"user","content":"..."},{"role":"assistant","content":"..."}]}`}</div>
          <textarea value={importContent} onChange={(e) => setImportContent(e.target.value)}
            rows={15} className="w-full bg-dark-bg border border-dark-border rounded-lg p-3 text-xs text-gray-200 font-mono"
            placeholder={`{"messages": [{"role": "user", "content": "你好"}, {"role": "assistant", "content": "你好！有什么可以帮你的？"}]}`} />
          <Button variant="primary" loading={loading} onClick={async () => {
            if (!importContent.trim()) return toast.error('请输入 JSONL 内容');
            setLoading(true);
            try {
              await finetuneApi.importDataset(importDsId, importContent, 'data.jsonl');
              setImportModalOpen(false); fetchDatasets(); toast.success('导入成功');
            } catch (e: any) { toast.error('导入失败', e?.message); }
            finally { setLoading(false); }
          }}>导入</Button>
        </div>
      </Modal>

      {/* ── Preview Modal ── */}
      <Modal open={previewModalOpen} onClose={() => setPreviewModalOpen(false)} title="数据集预览">
        <div className="space-y-2 max-h-96 overflow-auto">
          {previewData?.samples?.map((s: any, i: number) => (
            <div key={i} className="bg-dark-bg border border-dark-border rounded-lg p-2 text-xs">
              <div className="text-gray-500 mb-1">样本 #{previewData.total_count - (previewData.samples.length - i) + 1}</div>
              {(s.messages || []).map((m: any, j: number) => (
                <div key={j} className="mb-1">
                  <span className={`font-mono ${m.role === 'user' ? 'text-blue-400' : 'text-green-400'}`}>{m.role}:</span>
                  <span className="text-gray-300 ml-1">{String(m.content).slice(0, 200)}</span>
                </div>
              ))}
            </div>
          ))}
        </div>
      </Modal>

      {/* ── Submit Job Modal ── */}
      <Modal open={jobModalOpen} onClose={() => setJobModalOpen(false)} title="提交微调作业">
        <div className="space-y-4">
          <Select label="微调提供者" value={jobProvider} onChange={(v: string) => {
            setJobProvider(v);
            setJobBaseModel('');
            if (v === 'local') {
              // Get Ollama models from provider info
              const lp = providers.find((p:any) => p.name === 'local');
              if (lp?.supported_base_models?.length) {
                setBaseModelOptions(lp.supported_base_models.map((m:string) => ({value:m, label:m})));
              } else {
                setBaseModelOptions([{value:'qwen2.5-coder:7b',label:'qwen2.5-coder:7b (默认)'}]);
              }
            } else {
              setBaseModelOptions([{value:'deepseek-chat',label:'deepseek-chat'},{value:'deepseek-v4-pro',label:'deepseek-v4-pro'}]);
            }
          }}
            options={[
              {value:'deepseek',label:'DeepSeek (云端 API)'},
              {value:'local',label:'本地 LoRA (MLX) ' + (providers.find((p:any) => p.name==='local')?.available ? '✅' : '⚠️')},
            ]} />
          <Select label="基模型" value={jobBaseModel} onChange={setJobBaseModel}
            options={baseModelOptions} />
          <Select label="数据集" value={jobDatasetId} onChange={setJobDatasetId}
            options={datasets.filter(d => d.sample_count >= 10).map(d => ({value:d.id, label:`${d.name} (${d.sample_count}条)`}))} />
          <Select label="微调模板" value={jobTemplate} onChange={setJobTemplate}
            options={[
              {value:'general',label:'通用增强 (epochs=3)'},
              {value:'code',label:'代码能力 (epochs=4)'},
              {value:'customer_service',label:'客服场景 (epochs=2)'},
              {value:'custom',label:'自定义'},
            ]} />
          <Input label="自定义模型名（可选）" value={jobCustomName}
            onChange={(e: any) => setJobCustomName(e.target.value)}
            placeholder="留空则自动生成: base:ft-dataset:timestamp" />
          {jobProvider === 'local' && (
            <details className="text-xs text-gray-500">
              <summary className="cursor-pointer hover:text-gray-300">LoRA 高级参数</summary>
              <div className="mt-2 space-y-2 pl-2 border-l border-dark-border/50">
                <Input label="LoRA Rank (默认 16)" value={loraRank}
                  onChange={(e: any) => setLoraRank(e.target.value)} />
                <Input label="LoRA Alpha (默认 32)" value={loraAlpha}
                  onChange={(e: any) => setLoraAlpha(e.target.value)} />
              </div>
            </details>
          )}
          <Button variant="primary" onClick={async () => {
            if (!jobBaseModel || !jobDatasetId) return toast.error('请选择基模型和数据集');
            try {
              const body: any = { base_model: jobBaseModel, dataset_id: jobDatasetId, provider: jobProvider, template: jobTemplate, custom_name: jobCustomName };
              if (jobProvider === 'local') {
                body.lora_rank = parseInt(loraRank) || 16;
                body.lora_alpha = parseInt(loraAlpha) || 32;
              }
              await finetuneApi.createJob(body);
              setJobModalOpen(false); fetchJobs(); toast.success('微调作业已提交');
            } catch (e: any) { toast.error('提交失败', e?.message); }
          }}>提交</Button>
        </div>
      </Modal>

      {/* ── RL Training Tab ── */}
      {tab === 'training' && (
        <div className="space-y-4 mt-4">
          <div className="bg-dark-card rounded-lg p-6 border border-dark-border">
            <h3 className="text-lg font-semibold text-gray-100 mb-4">RL 强化学习训练</h3>
            <div className="grid grid-cols-2 gap-4 mb-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">基座模型</label>
                <input value={trainBaseModel} onChange={e => setTrainBaseModel(e.target.value)}
                  placeholder="qwen2.5-coder:7b"
                  className="w-full bg-dark-bg border border-dark-border rounded px-3 py-2 text-gray-200 text-sm" />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">数据集 ID</label>
                <select value={trainDatasetId} onChange={e => setTrainDatasetId(e.target.value)}
                  className="w-full bg-dark-bg border border-dark-border rounded px-3 py-2 text-gray-200 text-sm">
                  <option value="">选择数据集</option>
                  {datasets.map((d: any) => <option key={d.id} value={d.id}>{d.name || d.id}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">迭代次数</label>
                <input value={trainIterations} onChange={e => setTrainIterations(e.target.value)}
                  className="w-full bg-dark-bg border border-dark-border rounded px-3 py-2 text-gray-200 text-sm" />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">每迭代样本数</label>
                <input value={trainEpisodes} onChange={e => setTrainEpisodes(e.target.value)}
                  className="w-full bg-dark-bg border border-dark-border rounded px-3 py-2 text-gray-200 text-sm" />
              </div>
            </div>
            <Button icon={<Play className="w-4 h-4" />} loading={trainRunning} onClick={async () => {
              setTrainRunning(true); setTrainResult(null);
              try {
                const res = await fetch('/api/core/finetune/train', {
                  method: 'POST', headers: {'Content-Type': 'application/json'},
                  body: JSON.stringify({
                    base_model: trainBaseModel, dataset_id: trainDatasetId,
                    num_iterations: parseInt(trainIterations) || 1,
                    episodes_per_iter: parseInt(trainEpisodes) || 8,
                  }),
                });
                setTrainResult(await res.json());
                toast.success('RL 训练已启动');
              } catch (e: any) { toast.error('训练失败', e?.message); }
              setTrainRunning(false);
            }}>开始 RL 训练</Button>
            {trainResult && (
              <div className="mt-4 p-4 bg-dark-bg rounded border border-dark-border">
                <div className="text-sm text-gray-300">状态: <span className="text-green-400">{trainResult.status}</span></div>
                <div className="text-sm text-gray-300">迭代: {trainResult.iterations} · 样本: {trainResult.episodes}</div>
                <div className="text-sm text-gray-300">平均奖励: {trainResult.avg_reward?.toFixed(2)}</div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Distillation Tab ── */}
      {tab === 'distill' && (
        <div className="space-y-4 mt-4">
          <div className="bg-dark-card rounded-lg p-6 border border-dark-border">
            <h3 className="text-lg font-semibold text-gray-100 mb-4">知识蒸馏 (Teacher→Student)</h3>
            <div className="grid grid-cols-2 gap-4 mb-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">教师模型 (Teacher)</label>
                <input value={distillTeacher} onChange={e => setDistillTeacher(e.target.value)}
                  placeholder="qwen2.5-coder:32b"
                  className="w-full bg-dark-bg border border-dark-border rounded px-3 py-2 text-gray-200 text-sm" />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">学生模型 (Student)</label>
                <input value={distillStudent} onChange={e => setDistillStudent(e.target.value)}
                  placeholder="qwen2.5-coder:7b"
                  className="w-full bg-dark-bg border border-dark-border rounded px-3 py-2 text-gray-200 text-sm" />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">数据集 ID</label>
                <select value={distillDatasetId} onChange={e => setDistillDatasetId(e.target.value)}
                  className="w-full bg-dark-bg border border-dark-border rounded px-3 py-2 text-gray-200 text-sm">
                  <option value="">选择数据集</option>
                  {datasets.map((d: any) => <option key={d.id} value={d.id}>{d.name || d.id}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">模式</label>
                <select value={distillMode} onChange={e => setDistillMode(e.target.value)}
                  className="w-full bg-dark-bg border border-dark-border rounded px-3 py-2 text-gray-200 text-sm">
                  <option value="lora">LoRA (轻量, ~5MB)</option>
                  <option value="full">Full (全参数)</option>
                </select>
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">温度 (Temperature)</label>
                <input value={distillTemp} onChange={e => setDistillTemp(e.target.value)}
                  className="w-full bg-dark-bg border border-dark-border rounded px-3 py-2 text-gray-200 text-sm" />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">硬目标权重 (Alpha)</label>
                <input value={distillAlpha} onChange={e => setDistillAlpha(e.target.value)}
                  className="w-full bg-dark-bg border border-dark-border rounded px-3 py-2 text-gray-200 text-sm" />
              </div>
            </div>
            <Button icon={<Play className="w-4 h-4" />} loading={distillRunning} onClick={async () => {
              setDistillRunning(true);
              try {
                const res = await fetch('/api/core/finetune/distill', {
                  method: 'POST', headers: {'Content-Type': 'application/json'},
                  body: JSON.stringify({
                    teacher_model: distillTeacher, student_model: distillStudent,
                    dataset_id: distillDatasetId, temperature: parseFloat(distillTemp) || 2,
                    alpha: parseFloat(distillAlpha) || 0.5, mode: distillMode,
                  }),
                });
                const data = await res.json();
                setDistillJobs([data, ...distillJobs]);
                toast.success(`蒸馏作业已提交: ${data.job_id}`);
              } catch (e: any) { toast.error('蒸馏失败', e?.message); }
              setDistillRunning(false);
            }}>开始蒸馏</Button>
            {/* Distill jobs list */}
            {distillJobs.length > 0 && (
              <div className="mt-4">
                <h4 className="text-sm text-gray-400 mb-2">蒸馏作业</h4>
                {distillJobs.map((j: any, i: number) => (
                  <div key={i} className="flex justify-between items-center p-3 bg-dark-bg rounded border border-dark-border mb-2">
                    <div className="text-sm text-gray-300">
                      <span className="font-mono text-xs text-blue-400">{j.job_id?.slice(0, 12)}</span>
                      <span className={`ml-2 px-2 py-0.5 rounded text-xs ${
                        j.status === 'completed' ? 'bg-green-900 text-green-400' :
                        j.status === 'running' ? 'bg-blue-900 text-blue-400' : 'bg-gray-700 text-gray-400'
                      }`}>{j.status}</span>
                    </div>
                    <span className="text-xs text-gray-500">{j.teacher}→{j.student}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── From-Scratch Training Tab ── */}
      {tab === 'scratch' && (
        <div className="space-y-4 mt-4">
          <div className="bg-dark-card rounded-lg p-6 border border-dark-border">
            <h3 className="text-lg font-semibold text-gray-100 mb-2">从零训练模型</h3>
            <p className="text-sm text-gray-500 mb-4">随机初始化权重 → 在自定义数据集上训练 → 产出独立模型。适用于小型专用模型。</p>
            <div className="grid grid-cols-2 gap-4 mb-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">模型架构</label>
                <select value={scratchArch} onChange={e => setScratchArch(e.target.value)}
                  className="w-full bg-dark-bg border border-dark-border rounded px-3 py-2 text-gray-200 text-sm">
                  <option value="gpt2">GPT-2 (124M, ~4GB RAM)</option>
                  <option value="pythia-160m">Pythia (160M, ~6GB RAM)</option>
                  <option value="gpt2-medium">GPT-2 Medium (355M, ~12GB RAM)</option>
                </select>
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">数据集</label>
                <select value={scratchDataset} onChange={e => setScratchDataset(e.target.value)}
                  className="w-full bg-dark-bg border border-dark-border rounded px-3 py-2 text-gray-200 text-sm">
                  <option value="">选择数据集</option>
                  {datasets.map((d: any) => <option key={d.id} value={d.id}>{d.name || d.id}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">输出模型名</label>
                <input value={scratchOutputName} onChange={e => setScratchOutputName(e.target.value)}
                  placeholder="my-custom-model"
                  className="w-full bg-dark-bg border border-dark-border rounded px-3 py-2 text-gray-200 text-sm" />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Epochs</label>
                <input value={scratchEpochs} onChange={e => setScratchEpochs(e.target.value)}
                  className="w-full bg-dark-bg border border-dark-border rounded px-3 py-2 text-gray-200 text-sm" />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Batch Size</label>
                <input value={scratchBatchSize} onChange={e => setScratchBatchSize(e.target.value)}
                  className="w-full bg-dark-bg border border-dark-border rounded px-3 py-2 text-gray-200 text-sm" />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">学习率</label>
                <input value={scratchLR} onChange={e => setScratchLR(e.target.value)}
                  className="w-full bg-dark-bg border border-dark-border rounded px-3 py-2 text-gray-200 text-sm" />
              </div>
            </div>
            <div className="bg-amber-900/20 border border-amber-800/40 rounded-lg p-3 mb-4">
              <p className="text-xs text-amber-400">
                ⚠️ 从零训练需要大量数据（建议 1,000+ 条）和计算资源。适用于训练小型专用模型，不适合训练通用 LLM。
              </p>
            </div>
            <Button icon={<Play className="w-4 h-4" />} loading={scratchRunning} onClick={async () => {
              setScratchRunning(true);
              try {
                const res = await fetch('/api/core/finetune/scratch', {
                  method: 'POST', headers: {'Content-Type': 'application/json'},
                  body: JSON.stringify({
                    model_architecture: scratchArch, dataset_id: scratchDataset,
                    output_model_name: scratchOutputName, epochs: parseInt(scratchEpochs) || 3,
                    batch_size: parseInt(scratchBatchSize) || 4,
                    learning_rate: parseFloat(scratchLR) || 5e-5,
                  }),
                });
                const data = await res.json();
                setScratchJobs([data, ...scratchJobs]);
                toast.success(`训练已启动: ${data.job_id}`);
              } catch (e: any) { toast.error('训练失败', e?.message); }
              setScratchRunning(false);
            }}>开始训练</Button>
            {scratchJobs.length > 0 && (
              <div className="mt-4">
                <h4 className="text-sm text-gray-400 mb-2">训练作业</h4>
                {scratchJobs.map((j: any, i: number) => (
                  <div key={i} className="flex justify-between items-center p-3 bg-dark-bg rounded border border-dark-border mb-2">
                    <span className="font-mono text-xs text-blue-400">{j.job_id?.slice(0, 12)}</span>
                    <span className={`px-2 py-0.5 rounded text-xs ${
                      j.status === 'completed' ? 'bg-green-900 text-green-400' :
                      j.status === 'running' ? 'bg-blue-900 text-blue-400' : 'bg-gray-700 text-gray-400'
                    }`}>{j.status}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Models Tab ── */}
      {tab === 'models' && (
        <div className="space-y-4 mt-4">
          <div className="bg-dark-card rounded-lg p-6 border border-dark-border">
            <h3 className="text-lg font-semibold text-gray-100 mb-4">已注册模型</h3>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-500 border-b border-dark-border">
                  <th className="text-left py-2">名称</th>
                  <th className="text-left py-2">Provider</th>
                  <th className="text-left py-2">用途</th>
                  <th className="text-left py-2">分数</th>
                  <th className="text-left py-2">状态</th>
                </tr>
              </thead>
              <tbody>
                {models.length === 0 ? (
                  <tr><td colSpan={5} className="py-4 text-gray-500 text-center">暂无已注册模型</td></tr>
                ) : (
                  models.map((m: any, i: number) => (
                    <tr key={i} className="border-b border-dark-border/50">
                      <td className="py-2 text-gray-200">{m.display_name || m.name || '—'}</td>
                      <td className="py-2 text-gray-400">{m.provider_name || '—'}</td>
                      <td className="py-2 text-gray-400">{m.purpose || 'chat'}</td>
                      <td className="py-2 text-gray-400">{m.capability_score?.toFixed(2) || '—'}</td>
                      <td className="py-2">
                        <span className={`px-2 py-0.5 rounded text-xs ${m.available !== false ? 'bg-green-900 text-green-400' : 'bg-red-900 text-red-400'}`}>
                          {m.available !== false ? '可用' : '不可用'}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

export default FineTunePage;
