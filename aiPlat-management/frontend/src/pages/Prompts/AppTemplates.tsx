import React, { useEffect, useState } from 'react';
import { Plus, Edit3, Trash2, RefreshCw } from 'lucide-react';
import { Button, Card, CardContent, CardHeader, Input, Modal, Table, Textarea, toast, Badge } from '../../components/ui';
import { promptAppApi } from '../../services';
import PromptWorkbench from './PromptWorkbench';

const AppTemplates: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [seeding, setSeeding] = useState(false);
  const [items, setItems] = useState<any[]>([]);
  const [instances, setInstances] = useState<any[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [tab, setTab] = useState<'templates' | 'instances'>('templates');
  const [catFilter, setCatFilter] = useState('');
  const [search, setSearch] = useState('');
  const [newCat, setNewCat] = useState('');
  const [models, setModels] = useState<{value: string, label: string}[]>([]);

  // Instance editing (simple inline edit)
  const [instEditOpen, setInstEditOpen] = useState(false);
  const [instEditForm, setInstEditForm] = useState<any>({});
  const [instSaving, setInstSaving] = useState(false);

  const [workbenchOpen, setWorkbenchOpen] = useState(false);
  const [workbenchTpl, setWorkbenchTpl] = useState<any>(null);

  const fetchModels = async () => {
    try {
      const r = await fetch('/api/core/models');
      const data = await r.json();
      const list = (data.models || []).filter((m: any) => m.enabled !== false);
      setModels(list.map((m: any) => ({ value: m.name, label: `${m.name} (${m.provider || ''})` })));
    } catch { }
  };

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [tpl, cats, inst] = await Promise.all([
        promptAppApi.list({ category: catFilter }),
        promptAppApi.categories(),
        promptAppApi.listInstances(),
      ]);
      setItems((tpl as any).items || []);
      setCategories((cats as any) || []);
      setInstances((inst as any).items || []);
    } catch { } finally { setLoading(false); }
  };

  useEffect(() => { fetchAll(); fetchModels(); }, [catFilter]);
  const handleUseTemplate = async (sourceId: string) => {
    try {
      await promptAppApi.createInstance({ source_template_id: sourceId, name: '' });
      toast.success('已创建实例');
      fetchAll();
    } catch (e: any) { toast.error('创建失败', e?.message); }
  };

  const handleEditInstance = async (instId: string, inst: any) => {
    const safeVars = typeof inst.variables === 'string' ? JSON.parse(inst.variables || '[]') : (inst.variables || []);
    setInstEditForm({ ...inst, template_id: instId, isInstance: true, variables: safeVars,
      scenario_tags: typeof inst.scenario_tags === 'string' ? JSON.parse(inst.scenario_tags || '[]') : (inst.scenario_tags || []) });
    setInstEditOpen(true);
  };

  const handleSaveInstance = async () => {
    setInstSaving(true);
    try {
      await promptAppApi.updateInstance(instEditForm.template_id, instEditForm);
      toast.success('已保存');
      setInstEditOpen(false);
      fetchAll();
    } catch (e: any) { toast.error('保存失败', e?.message); }
    finally { setInstSaving(false); }
  };

  const handleDeleteInstance = async (id: string) => {
    if (!confirm('确认删除？')) return;
    await promptAppApi.deleteInstance(id);
    toast.success('已删除');
    fetchAll();
  };

  const filtered = items.filter(i => !search || i.name?.toLowerCase().includes(search.toLowerCase()));

  const openWorkbench = (tpl: any) => {
    setWorkbenchTpl(tpl);
    setWorkbenchOpen(true);
  };

  const tplColumns = [
    { title: '名称', dataIndex: 'name', render: (v: string, r: any) => (
      <span className="cursor-pointer text-primary hover:underline" onClick={() => openWorkbench(r)}>{v}</span>
    )},
    { title: '行业', dataIndex: 'category', render: (v: string) => <Badge>{v || '-'}</Badge> },
    { title: '标签', dataIndex: 'tags', render: (v: string) => {
      try { return JSON.parse(v || '[]').slice(0, 3).map((t: string) => <Badge key={t} className="mr-1">{t}</Badge>); } catch { return '-'; }
    }},
    { title: '操作', dataIndex: 'id', render: (id: string, r: any) => (
      <div className="flex gap-1">
        <Button size="sm" variant="primary" onClick={() => handleUseTemplate(id)}>使用</Button>
        <Button size="sm" variant="secondary" onClick={() => openWorkbench(r)}>🤖 工作台</Button>
        <Button size="sm" variant="ghost" onClick={() => handleDelete(id)}><Trash2 className="w-3 h-3" /></Button>
      </div>
    )},
  ];

  const instColumns = [
    { title: '名称', dataIndex: 'name' },
    { title: '来源', dataIndex: 'source_template_id', render: (v: string) => <span className="text-xs text-gray-500">{v}</span> },
    { title: '状态', dataIndex: 'status', render: (v: string) => v === 'published' ? '✅' : '📝' },
    { title: '操作', dataIndex: 'id', render: (id: string, r: any) => (
      <div className="flex gap-1">
        <Button size="sm" variant="ghost" onClick={() => handleEditInstance(id, r)}><Edit3 className="w-3 h-3" /></Button>
        <Button size="sm" variant="ghost" onClick={() => handleDeleteInstance(id)}><Trash2 className="w-3 h-3" /></Button>
      </div>
    )},
  ];

  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-gray-200">应用模板</h1>
        <div className="flex gap-2">
          <Button variant="secondary" icon={<Plus size={16} />} onClick={() => openWorkbench({ name: '', category: '', tags: [], system_prompt: '', user_prompt: '', assistant_prompt: '', variables: [], scenario_tags: [], id: '', template_id: '' })}>新建模板</Button>
          <Button variant="secondary" onClick={async () => { setSeeding(true); try { await promptAppApi.seed(); toast.success('已导入预置模板'); } catch (e: any) { toast.error('导入失败', e?.message); } finally { await fetchAll(); setSeeding(false); } }} loading={seeding}>↓ 导入预置</Button>
          <Button variant="secondary" icon={<RefreshCw size={16} />} onClick={fetchAll} loading={loading}>刷新</Button>
        </div>
      </div>

      {/* Tab switcher */}
      <div className="flex gap-0.5 bg-dark-bg rounded-lg p-0.5 border border-dark-border">
        <button onClick={() => setTab('templates')} className={`px-3 py-1.5 rounded text-xs ${tab === 'templates' ? 'bg-primary/20 text-primary' : 'text-gray-400'}`}>缺省模板库</button>
        <button onClick={() => setTab('instances')} className={`px-3 py-1.5 rounded text-xs ${tab === 'instances' ? 'bg-primary/20 text-primary' : 'text-gray-400'}`}>我的模板</button>
      </div>

      {tab === 'templates' ? (
        <>
          <div className="flex gap-0.5 bg-dark-bg rounded-lg p-0.5 border border-dark-border flex-wrap">
            <button onClick={() => setCatFilter('')} className={`px-3 py-1.5 rounded text-xs ${!catFilter ? 'bg-primary/20 text-primary' : 'text-gray-400'}`}>全部</button>
            {categories.map(c => (
              <button key={c} onClick={() => setCatFilter(c)} className={`px-3 py-1.5 rounded text-xs ${catFilter === c ? 'bg-primary/20 text-primary' : 'text-gray-400'}`}>{c}</button>
            ))}
            <div className="flex items-center gap-1 ml-2">
              <Input value={newCat} onChange={e => setNewCat(e.target.value)} placeholder="新分类..." className="w-20 text-[10px] py-0.5" />
              <Button size="sm" variant="ghost" onClick={async () => { if (newCat) { await promptAppApi.createCategory({ name: newCat }); setNewCat(''); fetchAll(); } }}>+</Button>
            </div>
          </div>
          <Card>
            <CardHeader><Input value={search} onChange={e => setSearch(e.target.value)} placeholder="搜索模板..." className="w-64" /></CardHeader>
            <CardContent><Table columns={tplColumns} data={filtered} rowKey="id" loading={loading} /></CardContent>
          </Card>
        </>
      ) : (
        <Card>
          <CardContent>
            {instances.length === 0 ? (
              <div className="text-center py-8 text-gray-500 text-sm">暂无实例。请从缺省模板库中点击"使用"创建。</div>
            ) : (
              <Table columns={instColumns} data={instances} rowKey="id" loading={loading} />
            )}
          </CardContent>
        </Card>
      )}

      <PromptWorkbench template={workbenchTpl} models={models} open={workbenchOpen} onClose={() => { setWorkbenchOpen(false); fetchAll(); }} onSaved={fetchAll} />

      {/* Instance Edit Modal (simple) */}
      <Modal open={instEditOpen} onClose={() => setInstEditOpen(false)} title="编辑实例" width={800}>
        <div className="space-y-3">
          <div><label className="text-xs text-gray-400">名称</label><Input value={instEditForm.name || ''} onChange={e => setInstEditForm({ ...instEditForm, name: e.target.value })} /></div>
          <div><label className="text-xs text-gray-400">角色定义</label><Textarea value={instEditForm.system_prompt || ''} onChange={e => setInstEditForm({ ...instEditForm, system_prompt: e.target.value })} rows={2} /></div>
          <div><label className="text-xs text-gray-400">任务指令</label><Textarea value={instEditForm.user_prompt || ''} onChange={e => setInstEditForm({ ...instEditForm, user_prompt: e.target.value })} rows={4} /></div>
          <div className="flex justify-end gap-2">
            <Button onClick={handleSaveInstance} loading={instSaving}>保存</Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default AppTemplates;
