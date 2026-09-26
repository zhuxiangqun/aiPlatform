import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Plus, Trash2, Pencil, Key, Check, Eye, EyeOff } from 'lucide-react';
import { Button, Modal, Input, toast } from '../../../components/ui';
import { credentialsApi } from '../../../services';

interface CredentialDef {
  id: string;
  name: string;
  key: string;
  provider: string;
  tool_name: string;
}

const emptyForm = (): CredentialDef => ({
  id: '',
  name: '',
  key: '',
  provider: '',
  tool_name: '',
});

const Credentials: React.FC = () => {
  const [items, setItems] = useState<CredentialDef[]>([]);
  const [editing, setEditing] = useState<CredentialDef | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [showKey, setShowKey] = useState(false);

  const fetchItems = () => {
    credentialsApi
      .list()
      .then((r: any) => setItems(r?.credentials || []))
      .catch(() => setItems([]));
  };

  useEffect(() => {
    fetchItems();
  }, []);

  const handleSave = async () => {
    if (!editing) return;
    if (!editing.name.trim()) {
      toast.error('名称不能为空');
      return;
    }
    if (!editing.id && !editing.key.trim()) {
      toast.error('密钥不能为空');
      return;
    }
    try {
      const payload = {
        name: editing.name.trim(),
        key: editing.key,
        provider: editing.provider.trim() || undefined,
        tool_name: editing.tool_name.trim() || undefined,
      };
      if (editing.id) {
        await credentialsApi.update(editing.id, payload);
      } else {
        await credentialsApi.create(payload as { name: string; key: string; provider?: string; tool_name?: string });
      }
      toast.success('已保存');
      setEditOpen(false);
      setEditing(null);
      setShowKey(false);
      fetchItems();
    } catch (e: any) {
      toast.error('保存失败', e?.detail || e?.message || '');
    }
  };

  const handleDelete = async (id: string) => {
    if (deleting) return;
    if (!confirm('确定删除该凭证？')) return;
    setDeleting(id);
    try {
      await credentialsApi.delete(id);
      toast.success('已删除');
      fetchItems();
    } catch {
      toast.error('删除失败');
    } finally {
      setDeleting(null);
    }
  };

  const openEdit = async (row: CredentialDef) => {
    setShowKey(false);
    try {
      const full: any = await credentialsApi.get(row.id, true);
      setEditing({
        id: row.id,
        name: String(full?.name || row.name || ''),
        key: String(full?.key || ''),
        provider: String(full?.provider || row.provider || ''),
        tool_name: String(full?.tool_name || row.tool_name || ''),
      });
    } catch {
      setEditing({ ...row, key: '' });
    }
    setEditOpen(true);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-100 tracking-tight">凭证管理</h1>
          <p className="text-sm text-gray-400 mt-1">
            API Key / Token 集中保管，绑定到工具后 Agent 可调用外部服务
          </p>
        </div>
        <Button
          icon={<Plus className="w-4 h-4" />}
          variant="primary"
          onClick={() => {
            setEditing(emptyForm());
            setShowKey(true);
            setEditOpen(true);
          }}
        >
          新建凭证
        </Button>
      </div>

      {items.length === 0 ? (
        <div className="text-center py-16 text-gray-500 border border-dashed border-dark-border rounded-xl">
          <Key className="w-8 h-8 mx-auto mb-2 opacity-40" />
          <p className="text-sm mb-1">暂无凭证</p>
          <p className="text-xs text-gray-600">创建后可在工具配置中引用 provider / tool_name</p>
        </div>
      ) : (
        <div className="space-y-2">
          <div className="hidden md:grid grid-cols-[1fr_160px_160px_1fr_80px] gap-3 text-[10px] text-gray-500 uppercase tracking-wider px-3 mb-1">
            <span>名称</span>
            <span>Provider</span>
            <span>Tool</span>
            <span>密钥</span>
            <span />
          </div>
          {items.map((c) => (
            <motion.div
              key={c.id}
              layout
              className="p-3 rounded-lg bg-dark-card border border-dark-border hover:border-primary/20 transition-colors"
            >
              <div className="md:grid md:grid-cols-[1fr_160px_160px_1fr_80px] gap-3 items-center">
                <div className="text-sm font-medium text-gray-100">{c.name}</div>
                <div className="text-xs text-gray-400 truncate">{c.provider || '—'}</div>
                <div className="text-xs text-gray-400 truncate">{c.tool_name || '—'}</div>
                <code className="text-xs text-gray-500 font-mono truncate">{c.key || '••••••••'}</code>
                <div className="flex items-center gap-1 justify-end">
                  <button
                    onClick={() => openEdit(c)}
                    className="p-1 rounded hover:bg-dark-hover"
                    title="编辑"
                  >
                    <Pencil className="w-3.5 h-3.5 text-gray-400" />
                  </button>
                  <button
                    onClick={() => handleDelete(c.id)}
                    disabled={!!deleting}
                    className="p-1 rounded hover:bg-red-900/20 disabled:opacity-40"
                    title="删除"
                  >
                    <Trash2 className="w-3.5 h-3.5 text-red-400" />
                  </button>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      )}

      <Modal
        open={editOpen}
        onClose={() => {
          setEditOpen(false);
          setEditing(null);
          setShowKey(false);
        }}
        title={editing?.id ? '编辑凭证' : '新建凭证'}
        width={520}
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => {
                setEditOpen(false);
                setEditing(null);
                setShowKey(false);
              }}
            >
              取消
            </Button>
            <Button variant="primary" onClick={handleSave}>
              <Check className="w-4 h-4" />
              {editing?.id ? '保存' : '创建'}
            </Button>
          </>
        }
      >
        {editing && (
          <div className="space-y-4">
            <Input
              label="名称"
              value={editing.name}
              onChange={(e) => setEditing({ ...editing, name: e.target.value })}
              placeholder="例如：OpenAI 生产 Key"
            />
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm text-gray-400">密钥 / Token</span>
                <button
                  type="button"
                  className="text-xs text-gray-500 hover:text-gray-300 flex items-center gap-1"
                  onClick={() => setShowKey((v) => !v)}
                >
                  {showKey ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                  {showKey ? '隐藏' : '显示'}
                </button>
              </div>
              <Input
                type={showKey ? 'text' : 'password'}
                value={editing.key}
                onChange={(e) => setEditing({ ...editing, key: e.target.value })}
                placeholder={editing.id ? '留空则不修改' : 'sk-...'}
              />
            </div>
            <Input
              label="Provider（可选）"
              value={editing.provider}
              onChange={(e) => setEditing({ ...editing, provider: e.target.value })}
              placeholder="例如：openai / anthropic"
            />
            <Input
              label="绑定工具名（可选）"
              value={editing.tool_name}
              onChange={(e) => setEditing({ ...editing, tool_name: e.target.value })}
              placeholder="例如：web_search"
            />
          </div>
        )}
      </Modal>
    </div>
  );
};

export default Credentials;
