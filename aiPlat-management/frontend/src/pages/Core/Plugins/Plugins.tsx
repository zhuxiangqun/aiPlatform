import { useEffect, useMemo, useState } from 'react';
import { RefreshCw, Save, ToggleLeft, ToggleRight, History, Eye } from 'lucide-react';
import { Button, Card, CardContent, CardHeader, Modal, Table, toast } from '../../../components/ui';
import { pluginApi } from '../../../services';
import { toastGateError } from '../../../utils/governanceError';

const Plugins: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<any[]>([]);

  const [manifestText, setManifestText] = useState(() => {
    const example = {
      plugin_id: 'p_demo',
      name: 'demo',
      version: '1.0.0',
      description: 'example plugin',
      dependencies: [],
      required_tools: ['calculator'],
      permissions: { tools: ['calculator'], files: { read: ['workspace/**'] } },
      tests: [{ kind: 'pytest', target: 'core/tests/integration/test_plugins_workflow.py' }],
    };
    return JSON.stringify(example, null, 2);
  });
  const [enabled, setEnabled] = useState(true);

  const [modalOpen, setModalOpen] = useState(false);
  const [modalTitle, setModalTitle] = useState('');
  const [modalData, setModalData] = useState<any>(null);

  const [versionsOpen, setVersionsOpen] = useState(false);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [versionsPlugin, setVersionsPlugin] = useState<any>(null);
  const [versions, setVersions] = useState<any[]>([]);

  const load = async () => {
    setLoading(true);
    try {
      const res = await pluginApi.list();
      setItems(Array.isArray(res?.items) ? res.items : []);
    } catch (e: any) {
      setItems([]);
      toastGateError(e, '加载插件失败');
    } finally {
      setLoading(false);
    }
  };

  const upsert = async () => {
    let manifest: any;
    try {
      manifest = JSON.parse(manifestText);
    } catch (e: any) {
      toast.error('manifest 不是合法 JSON', String(e?.message || ''));
      return;
    }
    try {
      const res = await pluginApi.upsert(manifest, enabled);
      toast.success('已保存', res?.plugin?.plugin_id || '');
      await load();
    } catch (e: any) {
      toastGateError(e, '保存失败');
    }
  };

  const toggleEnabled = async (p: any) => {
    try {
      const target = !(Number(p.enabled || 0) === 1);
      await pluginApi.setEnabled(String(p.plugin_id), target);
      toast.success('已更新', target ? 'enabled' : 'disabled');
      await load();
    } catch (e: any) {
      toastGateError(e, '更新失败');
    }
  };

  const showManifest = (p: any) => {
    setModalTitle(`manifest: ${p.plugin_id}`);
    setModalData(p.manifest || {});
    setModalOpen(true);
  };

  const showVersions = async (p: any) => {
    setVersionsPlugin(p);
    setVersionsOpen(true);
    setVersionsLoading(true);
    try {
      const res = await pluginApi.versions(String(p.plugin_id), 50, 0);
      setVersions(Array.isArray(res?.items) ? res.items : []);
    } catch (e: any) {
      setVersions([]);
      toastGateError(e, '加载版本失败');
    } finally {
      setVersionsLoading(false);
    }
  };

  const rollback = async (p: any, version: string) => {
    try {
      await pluginApi.rollback(String(p.plugin_id), version);
      toast.success('已回滚', version);
      await load();
      await showVersions(p);
    } catch (e: any) {
      toastGateError(e, '回滚失败');
    }
  };

  useEffect(() => {
    load();
  }, []);

  const columns = useMemo(
    () => [
      { key: 'plugin_id', title: 'plugin_id', dataIndex: 'plugin_id', width: 180 },
      { key: 'name', title: 'name', dataIndex: 'name', width: 180 },
      { key: 'version', title: 'version', dataIndex: 'version', width: 110 },
      {
        key: 'enabled',
        title: 'enabled',
        width: 90,
        render: (_: any, r: any) => (Number(r.enabled || 0) === 1 ? 'yes' : 'no'),
      },
      {
        key: 'actions',
        title: '操作',
        width: 220,
        render: (_: any, r: any) => (
          <div className="flex items-center gap-2">
            <Button size="sm" variant="secondary" icon={Number(r.enabled || 0) === 1 ? <ToggleRight size={14} /> : <ToggleLeft size={14} />} onClick={() => toggleEnabled(r)}>
              {Number(r.enabled || 0) === 1 ? '禁用' : '启用'}
            </Button>
            <Button size="sm" variant="ghost" icon={<Eye size={14} />} onClick={() => showManifest(r)} />
            <Button size="sm" variant="ghost" icon={<History size={14} />} onClick={() => showVersions(r)} />
          </div>
        ),
      },
    ],
    []
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-200">Plugins</h1>
          <p className="text-sm text-gray-500 mt-1">插件元数据（依赖/权限/测试声明）+ 安装/升级/回滚</p>
        </div>
        <Button variant="secondary" icon={<RefreshCw size={14} />} loading={loading} onClick={load}>
          刷新
        </Button>
      </div>

      <Card>
        <CardHeader>
          <div className="text-sm font-semibold text-gray-200">安装 / 升级（Upsert）</div>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-3 mb-3">
            <label className="flex items-center gap-2 text-sm text-gray-400">
              <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
              enabled
            </label>
            <Button variant="secondary" icon={<Save size={14} />} onClick={upsert}>
              保存
            </Button>
          </div>
          <textarea
            className="w-full h-64 bg-dark-hover border border-dark-border rounded-lg p-3 text-xs text-gray-200"
            value={manifestText}
            onChange={(e) => setManifestText(e.target.value)}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="text-sm font-semibold text-gray-200">已安装插件</div>
        </CardHeader>
        <CardContent>
          <Table rowKey={(r: any) => String(r.plugin_id)} loading={loading} data={items} columns={columns as any} emptyText="暂无插件" />
        </CardContent>
      </Card>

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title={modalTitle} width={900}>
        <pre className="text-xs bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto max-h-[70vh]">{JSON.stringify(modalData || {}, null, 2)}</pre>
      </Modal>

      <Modal
        open={versionsOpen}
        onClose={() => setVersionsOpen(false)}
        title={versionsPlugin ? `版本历史: ${versionsPlugin.plugin_id}` : '版本历史'}
        width={900}
      >
        <Table
          rowKey={(r: any) => String(r.version)}
          loading={versionsLoading}
          data={versions}
          columns={[
            { key: 'version', title: 'version', dataIndex: 'version', width: 140 },
            { key: 'created_at', title: 'created_at', dataIndex: 'created_at', width: 160 },
            {
              key: 'actions',
              title: '操作',
              width: 180,
              render: (_: any, r: any) => (
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => rollback(versionsPlugin, String(r.version))}
                  >
                    回滚到此版本
                  </Button>
                </div>
              ),
            },
          ]}
          emptyText="暂无版本记录"
        />
      </Modal>
    </div>
  );
};

export default Plugins;
