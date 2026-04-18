import React, { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { Plus, RotateCcw, Trash2, Globe, Zap } from 'lucide-react';
import { Table, Button, Modal, Switch, toast, Input } from '../../../components/ui';
import PageHeader from '../../../components/common/PageHeader';
import { gatewayApi, gatewayAdminApi } from '../../../services';
import type { GatewayRoute, GatewayPairing, GatewayToken } from '../../../services';

const methodColors: Record<string, { bg: string; text: string }> = {
  GET: { bg: 'bg-green-50', text: 'text-green-300' },
  POST: { bg: 'bg-blue-50', text: 'text-blue-300' },
  PUT: { bg: 'bg-orange-50', text: 'text-orange-300' },
  DELETE: { bg: 'bg-red-50', text: 'text-red-300' },
  PATCH: { bg: 'bg-purple-50', text: 'text-purple-300' },
};

const Gateway: React.FC = () => {
  const [routes, setRoutes] = useState<GatewayRoute[]>([]);
  const [loading, setLoading] = useState(false);
  const [deleteModal, setDeleteModal] = useState<{ open: boolean; route: GatewayRoute | null }>({ open: false, route: null });

  const [pairings, setPairings] = useState<GatewayPairing[]>([]);
  const [pairingsLoading, setPairingsLoading] = useState(false);
  const [pairingModal, setPairingModal] = useState<{ open: boolean }>({ open: false });
  const [pairingForm, setPairingForm] = useState<{ channel: string; channel_user_id: string; user_id: string; session_id: string }>({
    channel: 'slack',
    channel_user_id: '',
    user_id: '',
    session_id: 'default',
  });

  const [tokens, setTokens] = useState<GatewayToken[]>([]);
  const [tokensLoading, setTokensLoading] = useState(false);
  const [tokenModal, setTokenModal] = useState<{ open: boolean }>({ open: false });
  const [tokenForm, setTokenForm] = useState<{ name: string; token: string; enabled: boolean }>({ name: 'default', token: '', enabled: true });

  const fetchRoutes = useCallback(async () => {
    setLoading(true);
    try {
      const res = await gatewayApi.list();
      setRoutes(res.routes || []);
    } catch {
      toast.error('获取路由列表失败');
      setRoutes([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchPairings = useCallback(async () => {
    setPairingsLoading(true);
    try {
      const res = await gatewayAdminApi.listPairings({ limit: 200, offset: 0 });
      setPairings(res.items || []);
    } catch (e: any) {
      toast.error('获取 Pairings 失败', String(e?.message || ''));
      setPairings([]);
    } finally {
      setPairingsLoading(false);
    }
  }, []);

  const fetchTokens = useCallback(async () => {
    setTokensLoading(true);
    try {
      const res = await gatewayAdminApi.listTokens({ limit: 200, offset: 0 });
      setTokens(res.items || []);
    } catch (e: any) {
      toast.error('获取 Tokens 失败', String(e?.message || ''));
      setTokens([]);
    } finally {
      setTokensLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRoutes();
    fetchPairings();
    fetchTokens();
  }, [fetchRoutes, fetchPairings, fetchTokens]);

  const handleToggle = async (route: GatewayRoute) => {
    try {
      await gatewayApi.update(route.id, { enabled: !route.enabled });
      toast.success(`路由 "${route.name}" 已${route.enabled ? '禁用' : '启用'}`);
      fetchRoutes();
    } catch {
      toast.error('操作失败');
    }
  };

  const handleDelete = async () => {
    if (!deleteModal.route) return;
    try {
      await gatewayApi.delete(deleteModal.route.id);
      toast.success('路由已删除');
      setDeleteModal({ open: false, route: null });
      fetchRoutes();
    } catch {
      toast.error('删除失败');
    }
  };

  const submitPairing = async () => {
    try {
      if (!pairingForm.channel_user_id.trim()) return toast.error('请输入 channel_user_id');
      if (!pairingForm.user_id.trim()) return toast.error('请输入 user_id');
      await gatewayAdminApi.upsertPairing({
        channel: pairingForm.channel.trim() || 'default',
        channel_user_id: pairingForm.channel_user_id.trim(),
        user_id: pairingForm.user_id.trim(),
        session_id: pairingForm.session_id.trim() || 'default',
      });
      toast.success('Pairing 已保存');
      setPairingModal({ open: false });
      setPairingForm({ channel: 'slack', channel_user_id: '', user_id: '', session_id: 'default' });
      fetchPairings();
    } catch (e: any) {
      toast.error('保存 Pairing 失败', String(e?.message || ''));
    }
  };

  const deletePairing = async (p: GatewayPairing) => {
    try {
      await gatewayAdminApi.deletePairing({ channel: p.channel, channel_user_id: p.channel_user_id });
      toast.success('Pairing 已删除');
      fetchPairings();
    } catch (e: any) {
      toast.error('删除 Pairing 失败', String(e?.message || ''));
    }
  };

  const submitToken = async () => {
    try {
      if (!tokenForm.name.trim()) return toast.error('请输入 name');
      if (!tokenForm.token.trim()) return toast.error('请输入 token');
      await gatewayAdminApi.createToken({ name: tokenForm.name.trim(), token: tokenForm.token.trim(), enabled: tokenForm.enabled });
      toast.success('Token 已创建（请妥善保存 token 明文）');
      setTokenModal({ open: false });
      setTokenForm({ name: 'default', token: '', enabled: true });
      fetchTokens();
    } catch (e: any) {
      toast.error('创建 Token 失败', String(e?.message || ''));
    }
  };

  const deleteToken = async (t: GatewayToken) => {
    try {
      await gatewayAdminApi.deleteToken(t.id);
      toast.success('Token 已删除');
      fetchTokens();
    } catch (e: any) {
      toast.error('删除 Token 失败', String(e?.message || ''));
    }
  };

  const columns = [
    {
      key: 'name',
      title: '路由名称',
      render: (_: unknown, record: GatewayRoute) => (
        <span className="font-medium text-gray-100">{record.name}</span>
      ),
    },
    {
      key: 'path',
      title: '路径',
      render: (_: unknown, record: GatewayRoute) => (
        <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded text-gray-300">{record.path}</code>
      ),
    },
    {
      key: 'backend',
      title: '后端服务',
      render: (_: unknown, record: GatewayRoute) => (
        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium bg-dark-hover text-gray-300">
          <Globe size={12} />
          {record.backend}
        </span>
      ),
    },
    {
      key: 'methods',
      title: '方法',
      render: (_: unknown, record: GatewayRoute) => (
        <div className="flex flex-wrap gap-1">
          {record.methods.map((m: string) => {
            const colors = methodColors[m] || { bg: 'bg-dark-hover', text: 'text-gray-300' };
            return (
              <span key={m} className={`px-2 py-0.5 rounded text-xs font-medium ${colors.bg} ${colors.text}`}>
                {m}
              </span>
            );
          })}
        </div>
      ),
    },
    {
      key: 'rate_limit',
      title: '限流',
      render: (_: unknown, record: GatewayRoute) => `${record.rate_limit}/min`,
    },
    {
      key: 'enabled',
      title: '状态',
      render: (_: unknown, record: GatewayRoute) => (
        <Switch
          checked={record.enabled}
          onChange={() => handleToggle(record)}
        />
      ),
    },
    {
      key: 'actions',
      title: '操作',
      align: 'center' as const,
      render: (_: unknown, record: GatewayRoute) => (
        <div className="flex items-center justify-center gap-1">
          <button
            className="p-1.5 rounded-lg text-gray-400 hover:bg-dark-hover transition-colors"
            title="测试"
          >
            <Zap size={16} />
          </button>
          <button
            className="p-1.5 rounded-lg text-error hover:bg-error-light transition-colors"
            title="删除"
            onClick={() => setDeleteModal({ open: true, route: record })}
          >
            <Trash2 size={16} />
          </button>
        </div>
      ),
    },
  ];

  const enabledCount = routes.filter(r => r.enabled).length;

  return (
    <div className="space-y-6">
      <PageHeader
        title="API网关"
        description="管理API路由、限流、熔断与负载均衡策略"
        extra={
          <div className="flex items-center gap-3">
            <Button
              icon={<RotateCcw className="w-4 h-4" />}
              onClick={fetchRoutes}
              loading={loading}
            >
              刷新
            </Button>
            <Button
              variant="primary"
              icon={<Plus className="w-4 h-4" />}
            >
              创建路由
            </Button>
          </div>
        }
      />

      <div className="grid grid-cols-4 gap-4">
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-400 mb-1">总路由数</div>
          <div className="text-2xl font-semibold text-gray-100">{routes.length}</div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-400 mb-1">已启用</div>
          <div className="text-2xl font-semibold text-success">{enabledCount}</div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-400 mb-1">总限流</div>
          <div className="text-2xl font-semibold text-gray-100">{routes.reduce((s, r) => s + r.rate_limit, 0)}<span className="text-sm text-gray-400 ml-1">/min</span></div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="bg-dark-card rounded-xl border border-dark-border p-4"
        >
          <div className="text-sm text-gray-400 mb-1">平均超时</div>
          <div className="text-2xl font-semibold text-gray-100">
            {routes.length > 0 ? Math.round(routes.reduce((s, r) => s + r.timeout, 0) / routes.length) : 0}
            <span className="text-sm text-gray-400 ml-1">s</span>
          </div>
        </motion.div>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="bg-dark-card rounded-xl border border-dark-border overflow-hidden"
      >
        <Table
          columns={columns}
          data={routes}
          rowKey="id"
          loading={loading}
          emptyText="暂无路由数据"
        />
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="bg-dark-card rounded-xl border border-dark-border overflow-hidden">
          <div className="p-4 flex items-center justify-between">
            <div>
              <div className="text-sm text-gray-200 font-medium">Gateway Pairings</div>
              <div className="text-xs text-gray-500 mt-1">channel + channel_user_id → user_id/session_id</div>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="secondary" onClick={fetchPairings} loading={pairingsLoading}>
                刷新
              </Button>
              <Button variant="primary" onClick={() => setPairingModal({ open: true })}>
                新增
              </Button>
            </div>
          </div>
          <Table
            columns={[
              { key: 'channel', title: 'channel', width: 90, render: (_: unknown, r: any) => <span className="text-gray-300">{r.channel}</span> },
              { key: 'channel_user_id', title: 'channel_user_id', width: 140, render: (_: unknown, r: any) => <code className="text-xs text-gray-300">{r.channel_user_id}</code> },
              { key: 'user_id', title: 'user_id', width: 120, render: (_: unknown, r: any) => <code className="text-xs text-gray-300">{r.user_id}</code> },
              { key: 'session_id', title: 'session_id', width: 120, render: (_: unknown, r: any) => <code className="text-xs text-gray-400">{r.session_id || '-'}</code> },
              {
                key: 'actions',
                title: '操作',
                width: 90,
                align: 'center' as const,
                render: (_: unknown, r: GatewayPairing) => (
                  <button className="p-1.5 rounded-lg text-error hover:bg-error-light transition-colors" title="删除" onClick={() => deletePairing(r)}>
                    <Trash2 size={16} />
                  </button>
                ),
              },
            ]}
            data={pairings}
            rowKey="id"
            loading={pairingsLoading}
            emptyText="暂无 Pairings"
          />
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="bg-dark-card rounded-xl border border-dark-border overflow-hidden">
          <div className="p-4 flex items-center justify-between">
            <div>
              <div className="text-sm text-gray-200 font-medium">Gateway Tokens</div>
              <div className="text-xs text-gray-500 mt-1">/gateway/execute 可选鉴权 token</div>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="secondary" onClick={fetchTokens} loading={tokensLoading}>
                刷新
              </Button>
              <Button variant="primary" onClick={() => setTokenModal({ open: true })}>
                新增
              </Button>
            </div>
          </div>
          <Table
            columns={[
              { key: 'id', title: 'id', width: 140, render: (_: unknown, r: any) => <code className="text-xs text-gray-400">{r.id}</code> },
              { key: 'name', title: 'name', width: 120, render: (_: unknown, r: any) => <span className="text-gray-300">{r.name}</span> },
              { key: 'enabled', title: 'enabled', width: 80, render: (_: unknown, r: any) => <span className="text-gray-400">{String(Boolean(r.enabled))}</span> },
              {
                key: 'actions',
                title: '操作',
                width: 90,
                align: 'center' as const,
                render: (_: unknown, r: GatewayToken) => (
                  <button className="p-1.5 rounded-lg text-error hover:bg-error-light transition-colors" title="删除" onClick={() => deleteToken(r)}>
                    <Trash2 size={16} />
                  </button>
                ),
              },
            ]}
            data={tokens}
            rowKey="id"
            loading={tokensLoading}
            emptyText="暂无 Tokens"
          />
        </motion.div>
      </div>

      <Modal
        open={deleteModal.open}
        onClose={() => setDeleteModal({ open: false, route: null })}
        title="确认删除"
        footer={
          <>
            <Button onClick={() => setDeleteModal({ open: false, route: null })}>
              取消
            </Button>
            <Button variant="danger" onClick={handleDelete}>
              确认删除
            </Button>
          </>
        }
      >
        <p className="text-gray-600">
          确定要删除路由 "{deleteModal.route?.name}" 吗？此操作不可撤销。
        </p>
      </Modal>

      <Modal
        open={pairingModal.open}
        onClose={() => setPairingModal({ open: false })}
        title="新增 Pairing"
        width={640}
        footer={
          <>
            <Button variant="secondary" onClick={() => setPairingModal({ open: false })}>
              取消
            </Button>
            <Button variant="primary" onClick={submitPairing}>
              保存
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <Input label="channel" value={pairingForm.channel} onChange={(e: any) => setPairingForm({ ...pairingForm, channel: e.target.value })} />
          <Input
            label="channel_user_id"
            value={pairingForm.channel_user_id}
            onChange={(e: any) => setPairingForm({ ...pairingForm, channel_user_id: e.target.value })}
          />
          <Input label="user_id" value={pairingForm.user_id} onChange={(e: any) => setPairingForm({ ...pairingForm, user_id: e.target.value })} />
          <Input
            label="session_id"
            value={pairingForm.session_id}
            onChange={(e: any) => setPairingForm({ ...pairingForm, session_id: e.target.value })}
          />
        </div>
      </Modal>

      <Modal
        open={tokenModal.open}
        onClose={() => setTokenModal({ open: false })}
        title="新增 Token"
        width={640}
        footer={
          <>
            <Button variant="secondary" onClick={() => setTokenModal({ open: false })}>
              取消
            </Button>
            <Button variant="primary" onClick={submitToken}>
              创建
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <Input label="name" value={tokenForm.name} onChange={(e: any) => setTokenForm({ ...tokenForm, name: e.target.value })} />
          <Input label="token（明文）" value={tokenForm.token} onChange={(e: any) => setTokenForm({ ...tokenForm, token: e.target.value })} />
          <div className="text-xs text-gray-500">提示：token 明文仅由你输入并自行保存；服务端不会返回明文。</div>
        </div>
      </Modal>
    </div>
  );
};

export default Gateway;
