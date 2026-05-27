import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Card, CardContent, Button, Input, Select, toast } from '../../components/ui';

interface ApprovalItem {
  id: string;
  name: string;
  type: string;
  status: string;
  description: string;
  skills: string[];
  tools: string[];
  agent_type: string;
  deps_ok?: boolean;
  dep_warnings?: string[];
  meta?: Record<string, any>;
}

const PAGE_SIZE = 20;

const statusOptions = [
  { value: '', label: '全部状态' },
  { value: 'ready', label: '待审核' },
  { value: 'published', label: '已发布' },
  { value: 'listed', label: '已上架' },
  { value: 'deprecated', label: '已废弃' },
];

const typeOptions = [
  { value: '', label: '全部类型' },
  { value: 'agent', label: 'Agent' },
  { value: 'skill', label: 'Skill' },
  { value: 'mcp', label: 'MCP' },
  { value: 'workflow', label: 'Workflow' },
];

const statusLabels: Record<string, string> = { draft: '草稿', ready: '待审核', published: '已发布', listed: '已上架', deprecated: '已废弃' };
const statusColors: Record<string, string> = { draft: '#888', ready: '#f59e0b', published: '#3b82f6', listed: '#10b981', deprecated: '#6b7280' };

const ApprovalCenter: React.FC = () => {
  const [items, setItems] = useState<ApprovalItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [expandedId, setExpandedId] = useState('');

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/approval/list');
      const data = await res.json();
      setItems(data.items || []);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchList(); }, [fetchList]);

  // Filtered items
  const filtered = useMemo(() => {
    let list = items.filter(item => {
      if (statusFilter && item.status !== statusFilter) return false;
      if (typeFilter && item.type !== typeFilter) return false;
      if (search) {
        const q = search.toLowerCase();
        if (!(item.name || '').toLowerCase().includes(q) &&
            !(item.description || '').toLowerCase().includes(q) &&
            !(item.type || '').toLowerCase().includes(q)) return false;
      }
      return true;
    });
    // Sort: lifecycle states first, runtime states last
    const order: Record<string, number> = { ready: 0, published: 1, listed: 2, deprecated: 3 };
    list.sort((a, b) => {
      const oa = order[a.status] ?? 99;
      const ob = order[b.status] ?? 99;
      if (oa !== ob) return oa - ob;
      return (a.name || '').localeCompare(b.name || '');
    });
    return list;
  }, [items, statusFilter, typeFilter, search]);

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const paged = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  useEffect(() => { setPage(1); }, [statusFilter, typeFilter, search]);

  const handleAction = async (id: string, action: string, itemType: string) => {
    setActionLoading(id + action);
    try {
      const res = await fetch(`/api/approval/${action}?id=${encodeURIComponent(id)}&type=${encodeURIComponent(itemType)}`, { method: 'POST' });
      const data = await res.json();
      if (data.ok) {
        const msgs: Record<string, string> = { approve: '功能审核通过', publish: '已上架', reject: '已退回', deprecate: '已废弃', unlist: '已下架' };
        toast.success(msgs[action] || '操作完成');
        fetchList();
      } else {
        toast.error(data.detail || '操作失败');
      }
    } catch { toast.error('操作失败'); }
    finally { setActionLoading(null); }
  };

  const renderChecklist = (item: ApprovalItem) => {
    const m = item.meta || {};
    const s = item.status;
    const ok = (v: any) => (v ? '☑' : '☐');
    return (
      <div style={{ padding: '12px 16px', background: '#0a0a14', borderTop: '1px solid #1a1a2e' }}>
        {s === 'ready' && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <div>
              <div style={{ fontSize: 12, color: '#888', marginBottom: 6 }}>📋 功能审核清单（ready → published）</div>
              {item.type === 'agent' && (
                <>
                  <div style={{ fontSize: 12, marginBottom: 4 }}>{ok(item.name?.length > 1)} 名称规范</div>
                  <div style={{ fontSize: 12, marginBottom: 4 }}>{ok(item.description?.length > 10)} 描述完整</div>
                  <div style={{ fontSize: 12, marginBottom: 4 }}>{ok(item.skills?.length > 0)} Skills 绑定 ({item.skills?.length || 0}个)</div>
                  <div style={{ fontSize: 12, marginBottom: 4 }}>{ok(item.tools?.length > 0)} Tools 绑定 ({item.tools?.length || 0}个)</div>
                  <div style={{ fontSize: 12, marginBottom: 4 }}>{ok(m.model)} 模型配置: {m.model || '未配置'}</div>
                  {item.deps_ok === false && <div style={{ fontSize: 12, marginBottom: 4, color: '#f59e0b' }}>⚠ 依赖未全部上架</div>}
                  {m.lint && (
                    <div style={{ fontSize: 12, lineHeight: 1.6, padding: '8px 10px', background: m.lint.risk_level === 'high' ? 'rgba(239,68,68,0.1)' : 'rgba(245,158,11,0.1)', borderRadius: 6, marginTop: 6 }}>
                      <div style={{ marginBottom: 2 }}>
                        🔍 配置校验: <span style={{ color: m.lint.error_count > 0 ? '#ef4444' : '#f59e0b' }}>E{m.lint.error_count || '?'}</span>
                        {' / '}
                        <span style={{ color: '#f59e0b' }}>W{m.lint.warning_count || '?'}</span>
                      </div>
                      {m.lint.blocked && <div style={{ fontSize: 11, color: '#ef4444' }}>⚠ 存在阻塞错误，无法通过审批</div>}
                    </div>
                  )}
                  {m.governance?.status === 'pending' && (
                    <div style={{ fontSize: 12, marginTop: 4, color: '#f59e0b' }}>📋 治理状态: 待审批</div>
                  )}
                </>
              )}
              {item.type === 'skill' && (
                <>
                  <div style={{ fontSize: 12, marginBottom: 4 }}>{ok(item.name?.length > 1)} 名称规范</div>
                  <div style={{ fontSize: 12, marginBottom: 4 }}>{ok(item.description?.length > 10)} 描述完整</div>
                  <div style={{ fontSize: 12, marginBottom: 4 }}>{ok(m.category)} 分类: {m.category || '未设置'}</div>
                  <div style={{ fontSize: 12, marginBottom: 4 }}>{ok(m.version)} 版本: {m.version || '未设置'}</div>
                  {m.effects?.length === 0 && <div style={{ fontSize: 12, marginBottom: 4, color: '#f59e0b' }}>⚠ 效果声明未提供</div>}
                  {m.lint && (
                    <div style={{ fontSize: 12, lineHeight: 1.6, padding: '8px 10px', background: m.lint.risk_level === 'high' ? 'rgba(239,68,68,0.1)' : 'rgba(245,158,11,0.1)', borderRadius: 6, marginTop: 6 }}>
                      <div style={{ marginBottom: 2 }}>
                        🔍 Lint: <span style={{ color: m.lint.error_count > 0 ? '#ef4444' : '#f59e0b' }}>E{m.lint.error_count || m.lint.summary?.error_count || '?'}</span>
                        {' / '}
                        <span style={{ color: '#f59e0b' }}>W{m.lint.warning_count || m.lint.summary?.warning_count || '?'}</span>
                        {typeof m.lint.risk_level === 'string' && (
                          <span style={{ marginLeft: 4, color: m.lint.risk_level === 'high' ? '#ef4444' : m.lint.risk_level === 'medium' ? '#f59e0b' : '#22c55e' }}>({m.lint.risk_level})</span>
                        )}
                      </div>
                      {m.lint.blocked && <div style={{ fontSize: 11, color: '#ef4444' }}>⚠ 存在阻塞错误，无法通过审批</div>}
                    </div>
                  )}
                  {m.governance?.status === 'pending' && (
                    <div style={{ fontSize: 12, marginTop: 4, color: '#f59e0b' }}>📋 治理状态: 待审批</div>
                  )}
                </>
              )}
              {item.type === 'mcp' && (
                <>
                  <div style={{ fontSize: 12, marginBottom: 4 }}>{ok(item.name?.length > 1)} 名称规范</div>
                  <div style={{ fontSize: 12, marginBottom: 4 }}>{ok(item.description?.length > 10)} 描述完整</div>
                  <div style={{ fontSize: 12, marginBottom: 4 }}>{ok(m.transport)} Transport: {m.transport || '未配置'}</div>
                  <div style={{ fontSize: 12, marginBottom: 4 }}>{ok(m.tool_count > 0)} 工具数: {m.tool_count || 0}</div>
                  {m.lint && (
                    <div style={{ fontSize: 12, lineHeight: 1.6, padding: '8px 10px', background: m.lint.risk_level === 'high' ? 'rgba(239,68,68,0.1)' : 'rgba(245,158,11,0.1)', borderRadius: 6, marginTop: 6 }}>
                      <div style={{ marginBottom: 2 }}>
                        🔍 配置校验: <span style={{ color: m.lint.error_count > 0 ? '#ef4444' : '#f59e0b' }}>E{m.lint.error_count || '?'}</span>
                        {' / '}<span style={{ color: '#f59e0b' }}>W{m.lint.warning_count || '?'}</span>
                      </div>
                      {m.lint.blocked && <div style={{ fontSize: 11, color: '#ef4444' }}>⚠ 存在阻塞错误，无法通过审批</div>}
                    </div>
                  )}
                  {m.governance?.status === 'pending' && (
                    <div style={{ fontSize: 12, marginTop: 4, color: '#f59e0b' }}>📋 治理状态: 待审批</div>
                  )}
                </>
              )}
              {item.type === 'workflow' && (
                <>
                  <div style={{ fontSize: 12, marginBottom: 4 }}>{ok(item.name?.length > 1)} 名称规范</div>
                  <div style={{ fontSize: 12, marginBottom: 4 }}>{ok(item.description?.length > 10)} 描述完整</div>
                  <div style={{ fontSize: 12, marginBottom: 4 }}>{ok((m.node_count || 0) >= 2)} 节点数: {m.node_count || 0}</div>
                  <div style={{ fontSize: 12, marginBottom: 4 }}>{ok(m.bound_app)} 绑定 App: {m.bound_app || '未绑定'}</div>
                  {m.lint && (
                    <div style={{ fontSize: 12, lineHeight: 1.6, padding: '8px 10px', background: m.lint.risk_level === 'high' ? 'rgba(239,68,68,0.1)' : 'rgba(245,158,11,0.1)', borderRadius: 6, marginTop: 6 }}>
                      <div style={{ marginBottom: 2 }}>
                        🔍 配置校验: <span style={{ color: m.lint.error_count > 0 ? '#ef4444' : '#f59e0b' }}>E{m.lint.error_count || '?'}</span>
                        {' / '}<span style={{ color: '#f59e0b' }}>W{m.lint.warning_count || '?'}</span>
                      </div>
                      {m.lint.blocked && <div style={{ fontSize: 11, color: '#ef4444' }}>⚠ 存在阻塞错误，无法通过审批</div>}
                    </div>
                  )}
                  {m.governance?.status === 'pending' && (
                    <div style={{ fontSize: 12, marginTop: 4, color: '#f59e0b' }}>📋 治理状态: 待审批</div>
                  )}
                </>
              )}
              {(item.dep_warnings?.length ?? 0) > 0 && (
                <div style={{ marginTop: 4, padding: '4px 8px', background: '#2d1f00', borderRadius: 4, fontSize: 11, color: '#f59e0b' }}>
                  ⚠ {(item.dep_warnings || []).join(', ')}
                </div>
              )}
            </div>
            <div>
              <div style={{ fontSize: 12, color: '#888', marginBottom: 6 }}>基本信息</div>
              <div style={{ fontSize: 12, color: '#aaa', marginBottom: 2 }}>类型: {item.agent_type || item.type}</div>
              {item.description && <div style={{ fontSize: 11, color: '#666', marginBottom: 4 }}>{item.description.slice(0, 200)}</div>}
              {item.skills?.length > 0 && (
                <div style={{ marginBottom: 4 }}>
                  <div style={{ fontSize: 11, color: '#888' }}>Skills:</div>
                  {item.skills.map((sk, i) => <span key={i} style={{ fontSize: 10, color: '#60a5fa', marginRight: 6 }}>{sk}</span>)}
                </div>
              )}
              {item.tools?.length > 0 && (
                <div>
                  <div style={{ fontSize: 11, color: '#888' }}>Tools:</div>
                  {item.tools.map((t, i) => <span key={i} style={{ fontSize: 10, color: '#fbbf24', marginRight: 6 }}>{t}</span>)}
                </div>
              )}
            </div>
          </div>
        )}

        {s === 'published' && (
          <div style={{ fontSize: 12 }}>
            <div style={{ color: '#888', marginBottom: 6 }}>📦 上架审核清单（published → listed）</div>
            <div style={{ color: '#aaa', marginBottom: 4 }}>已通过功能审核。确认以下内容后可执行上架：</div>
            <div style={{ marginBottom: 4 }}>{ok(item.description?.length > 20)} 文案清晰可对外发布</div>
            <div style={{ marginBottom: 4 }}>{ok(item.deps_ok !== false)} 所有依赖均已上架</div>
            <div style={{ color: '#666', marginTop: 4 }}>描述: {item.description?.slice(0, 200) || '无'}</div>
          </div>
        )}

        {s === 'listed' && (
          <div style={{ fontSize: 12, color: '#10b981' }}>
            ✅ 已上架 — 出现在商城及导出列表中，可下架退回已发布状态
          </div>
        )}

        {s === 'deprecated' && (
          <div style={{ fontSize: 12, color: '#6b7280' }}>
            🗑 已废弃 — 不再使用，只读
          </div>
        )}
      </div>
    );
  };

  const renderButtons = (item: ApprovalItem) => {
    const s = item.status;
    const loadingFor = (a: string) => actionLoading === (item.id + a);

    // Fallback: runtime states treated like ready
    if (s === 'ready' || s === 'initializing' || s === 'running') {
      return (
        <div style={{ display: 'flex', gap: 6 }}>
          <Button variant="primary" size="sm" onClick={() => handleAction(item.id, 'approve', item.type)} loading={loadingFor('approve')}>✅ 通过</Button>
          <Button variant="secondary" size="sm" onClick={() => handleAction(item.id, 'reject', item.type)} loading={loadingFor('reject')}>↩ 退回</Button>
        </div>
      );
    }
    if (s === 'published') {
      return (
        <div style={{ display: 'flex', gap: 6 }}>
          <Button variant="primary" size="sm" onClick={() => handleAction(item.id, 'publish', item.type)} loading={loadingFor('publish')}>📦 上架</Button>
          <Button variant="secondary" size="sm" onClick={() => handleAction(item.id, 'reject', item.type)} loading={loadingFor('reject')}>↩ 退回</Button>
          <Button variant="danger" size="sm" onClick={() => handleAction(item.id, 'deprecate', item.type)} loading={loadingFor('deprecate')}>🗑 废弃</Button>
        </div>
      );
    }
    if (s === 'listed') {
      return (
        <Button variant="danger" size="sm" onClick={() => handleAction(item.id, 'unlist', item.type)} loading={loadingFor('unlist')}>⬇ 下架</Button>
      );
    }
    return null;
  };

  const typeCounts = useMemo(() => {
    const c: Record<string, number> = { agent: 0, skill: 0, mcp: 0, workflow: 0 };
    items.forEach(i => { c[i.type] = (c[i.type] || 0) + 1; });
    return c;
  }, [items]);

  const statusCounts = useMemo(() => {
    const c: Record<string, number> = {};
    items.forEach(i => { c[i.status] = (c[i.status] || 0) + 1; });
    return c;
  }, [items]);

  return (
    <div style={{ padding: 20, maxWidth: 1100 }}>
      <h2 style={{ margin: 0 }}>审批中心</h2>
      <p style={{ color: '#888', margin: '4px 0 16px' }}>
        总计 {items.length} 项 | Agent {typeCounts.agent} | Skill {typeCounts.skill} | MCP {typeCounts.mcp} | Workflow {typeCounts.workflow}
        &nbsp;| 待审核 {statusCounts.ready || 0} | 已发布 {statusCounts.published || 0} | 已上架 {statusCounts.listed || 0} | 已废弃 {statusCounts.deprecated || 0}
      </p>

      {/* Filters */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 16, alignItems: 'center' }}>
        <div style={{ width: 140 }}>
          <Select value={typeFilter} onChange={setTypeFilter} options={typeOptions} />
        </div>
        <div style={{ width: 150 }}>
          <Select value={statusFilter} onChange={setStatusFilter} options={statusOptions} />
        </div>
        <div style={{ flex: 1 }}>
          <Input value={search} onChange={e => setSearch(e.target.value)} placeholder="搜索名称或描述..." />
        </div>
        <Button variant="secondary" size="sm" onClick={fetchList} loading={loading}>🔄 刷新</Button>
      </div>

      <Card>
        <CardContent>
          {loading ? (
            <div style={{ color: '#666', padding: 40, textAlign: 'center' }}>加载中...</div>
          ) : paged.length === 0 ? (
            <div style={{ color: '#666', padding: 40, textAlign: 'center' }}>
              {filtered.length === 0 ? '暂无数据' : '无匹配结果'}
            </div>
          ) : (
            <>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #333', color: '#888', fontSize: 13, textAlign: 'left' }}>
                    <th style={{ padding: '8px 10px', width: 40 }}>#</th>
                    <th style={{ padding: '8px 10px' }}>名称</th>
                    <th style={{ padding: '8px 10px', width: 90 }}>类型</th>
                    <th style={{ padding: '8px 10px', width: 100 }}>状态</th>
                    <th style={{ padding: '8px 10px', width: 280 }}>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {paged.map((item, i) => (
                    <React.Fragment key={item.id}>
                      <tr
                        onClick={() => setExpandedId(expandedId === item.id ? '' : item.id)}
                        style={{
                          borderBottom: '1px solid #1a1a2e', color: '#ccc', fontSize: 13,
                          cursor: 'pointer',
                          background: expandedId === item.id ? '#111122' : 'transparent',
                        }}>
                        <td style={{ padding: '8px 10px', color: '#555' }}>{(page - 1) * PAGE_SIZE + i + 1}</td>
                        <td style={{ padding: '8px 10px' }}>
                          <div style={{ fontWeight: 500 }}>
                            {item.name}
                            {item.deps_ok === false && item.status !== 'deprecated' && (
                              <span style={{ color: '#f59e0b', fontSize: 11, marginLeft: 6 }} title={(item.dep_warnings || []).join(', ')}>
                                ⚠ 依赖未上架
                              </span>
                            )}
                          </div>
                          {item.description && (
                            <div style={{ color: '#666', fontSize: 11, marginTop: 2 }}>{item.description.slice(0, 100)}</div>
                          )}
                        </td>
                        <td style={{ padding: '8px 10px', fontSize: 12 }}>
                          <span style={{ padding: '2px 6px', borderRadius: 4, fontSize: 11,
                            background: item.type === 'agent' ? '#1e3a5f' : item.type === 'skill' ? '#3d2e1e' : item.type === 'mcp' ? '#2e1e3d' : '#1e3d2e',
                            color: item.type === 'agent' ? '#60a5fa' : item.type === 'skill' ? '#fbbf24' : item.type === 'mcp' ? '#c084fc' : '#34d399',
                          }}>{item.type}</span>
                        </td>
                        <td style={{ padding: '8px 10px' }}>
                          <span style={{ padding: '2px 8px', borderRadius: 4, fontSize: 11,
                            color: statusColors[item.status] || '#888',
                            background: (statusColors[item.status] || '#888') + '18',
                            border: '1px solid ' + (statusColors[item.status] || '#888') + '40',
                          }}>{statusLabels[item.status] || item.status}</span>
                        </td>
                        <td style={{ padding: '8px 10px' }}>
                          {renderButtons(item)}
                        </td>
                      </tr>
                      {expandedId === item.id && (
                        <tr>
                          <td colSpan={5} style={{ padding: 0 }}>
                            {renderChecklist(item)}
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  ))}
                </tbody>
              </table>

              {/* Pagination */}
              {totalPages > 1 && (
                <div style={{ display: 'flex', justifyContent: 'center', gap: 8, marginTop: 12 }}>
                  <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>← 上一页</Button>
                  <span style={{ color: '#888', fontSize: 13, padding: '4px 12px' }}>{page} / {totalPages}</span>
                  <Button variant="secondary" size="sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>下一页 →</Button>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default ApprovalCenter;
