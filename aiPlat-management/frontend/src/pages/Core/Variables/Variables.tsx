import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Plus, Trash2, Pencil, Globe, Workflow, Check } from 'lucide-react';
import { Button, Modal, Input, toast } from '../../../components/ui';
import { variablesApi } from '../../../services';

interface VariableDef {
  id: string;
  name: string;
  value: string;
  scope: 'global' | 'workflow';
  description: string;
}

const Variables: React.FC = () => {
  const [variables, setVariables] = useState<VariableDef[]>([]);
  const [editing, setEditing] = useState<VariableDef | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

  const fetchVariables = () => {
    variablesApi.list().then((r: any) => setVariables(r?.variables || [])).catch(() => setVariables([]));
  };

  useEffect(() => { fetchVariables(); }, []);

  const handleSave = async () => {
    if (!editing) return;
    if (!editing.name.trim()) { toast.error('变量名不能为空'); return; }
    const cleanName = editing.name.trim().replace(/\s+/g, '_').toUpperCase();
    try {
      if (editing.id) {
        await variablesApi.update(editing.id, { name: cleanName, value: editing.value, scope: editing.scope, description: editing.description });
      } else {
        await variablesApi.create({ name: cleanName, value: editing.value, scope: editing.scope, description: editing.description });
      }
      toast.success('已保存');
      setEditOpen(false); setEditing(null);
      fetchVariables();
    } catch (e: any) { toast.error('保存失败', (e as any)?.detail || e?.message || ''); }
  };

  const handleDelete = async (id: string) => {
    if (deleting) return;
    if (!confirm('确定删除？')) return;
    setDeleting(id);
    try { await variablesApi.delete(id); toast.success('已删除'); fetchVariables(); } catch (e: any) { toast.error('删除失败'); }
    finally { setDeleting(null); }
  };

  const scopeIcon = (scope: string) => scope === 'global' ? <Globe className="w-3.5 h-3.5" /> : <Workflow className="w-3.5 h-3.5" />;
  const scopeLabel = (scope: string) => scope === 'global' ? '全局' : '工作流';

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-100 tracking-tight">变量管理</h1>
          <p className="text-sm text-gray-400 mt-1">定义全局和工作流变量，Agent 和 Workflow 可通过 <code className="text-xs bg-dark-bg px-1 rounded">&#123;&#123;变量名&#125;&#125;</code> 引用</p>
        </div>
        <Button icon={<Plus className="w-4 h-4" />} variant="primary" onClick={() => { setEditing({ id: '', name: '', value: '', scope: 'global', description: '' }); setEditOpen(true); }}>
          新建变量
        </Button>
      </div>

      {variables.length === 0 ? (
        <div className="text-center py-16 text-gray-500 border border-dashed border-dark-border rounded-xl">
          <p className="text-sm mb-1">暂无变量</p>
          <p className="text-xs text-gray-600">创建变量后在 Agent SOP 或 Workflow 中通过 {`{{变量名}}`} 引用</p>
        </div>
      ) : (
        <div className="space-y-2">
          <div className="hidden md:grid grid-cols-[1fr_200px_100px_100px_80px] gap-3 text-[10px] text-gray-500 uppercase tracking-wider px-3 mb-1">
            <span>名称 / 值</span><span>描述</span><span>作用域</span><span>示例引用</span><span />
          </div>
          {variables.map(v => (
            <motion.div key={v.id} layout className="p-3 rounded-lg bg-dark-card border border-dark-border hover:border-primary/20 transition-colors">
              <div className="md:grid md:grid-cols-[1fr_200px_100px_100px_80px] gap-3 items-center">
                <div>
                  <div className="text-sm font-medium text-gray-100 font-mono">{v.name}</div>
                  <div className="text-xs text-gray-400 truncate mt-0.5">{v.value || '(空)'}</div>
                </div>
                <div className="text-xs text-gray-500 hidden md:block truncate">{v.description || '—'}</div>
                <div className="hidden md:flex items-center gap-1 text-xs">
                  {scopeIcon(v.scope)}
                  <span className={v.scope === 'global' ? 'text-blue-300' : 'text-purple-300'}>{scopeLabel(v.scope)}</span>
                </div>
                <code className="hidden md:block text-[10px] bg-dark-bg px-1.5 py-0.5 rounded text-gray-400">{`{{${v.name}}}`}</code>
                <div className="flex items-center gap-1 justify-end">
                  <button onClick={() => { setEditing(v); setEditOpen(true); }} className="p-1 rounded hover:bg-dark-hover"><Pencil className="w-3.5 h-3.5 text-gray-400" /></button>
                  <button onClick={() => handleDelete(v.id)} disabled={!!deleting} className="p-1 rounded hover:bg-red-900/20 disabled:opacity-40"><Trash2 className="w-3.5 h-3.5 text-red-400" /></button>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      )}

      <Modal open={editOpen} onClose={() => { setEditOpen(false); setEditing(null); }} title={editing?.id ? '编辑变量' : '新建变量'} width={500}
        footer={<><Button variant="secondary" onClick={() => { setEditOpen(false); setEditing(null); }}>取消</Button><Button variant="primary" onClick={handleSave}><Check className="w-4 h-4" />{editing?.id ? '保存' : '创建'}</Button></>}>
        {editing && (
          <div className="space-y-4">
            <Input label="变量名" value={editing.name} onChange={e => setEditing({ ...editing, name: e.target.value })} placeholder="例如：API_ENDPOINT, MODEL_NAME" />
            <Input label="默认值" value={editing.value} onChange={e => setEditing({ ...editing, value: e.target.value })} placeholder="变量默认值" />
            <div>
              <div className="text-sm text-gray-400 mb-1">作用域</div>
              <select value={editing.scope} onChange={e => setEditing({ ...editing, scope: e.target.value as 'global' | 'workflow' })}
                className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100">
                <option value="global">全局（所有 Agent/Workflow 可用）</option>
                <option value="workflow">工作流（仅当前 Workflow 内可用）</option>
              </select>
            </div>
            <Input label="描述" value={editing.description} onChange={e => setEditing({ ...editing, description: e.target.value })} placeholder="变量用途说明" />
            <div className="text-xs text-gray-500">
              引用方式: <code className="bg-dark-bg px-1 rounded">{`{{${editing.name || 'VARIABLE'}}}`}</code>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default Variables;
