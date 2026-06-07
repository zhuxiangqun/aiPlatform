/**
 * BrowserTestPanel — 全功能浏览器自动化测试控制面板
 *
 * 功能：
 *   - 测试参数配置（URL、账号、路由、选项）
 *   - 启动/停止测试
 *   - 实时轮询进度展示
 *   - 通过/失败/跳过数量统计
 *   - 页面级操作明细表
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  Input,
  Select,
  Textarea,
  toast,
  Table,
  Tag,
} from '../../../components/ui';
import { browserTestApi } from '../../../services';
import type { TestStatus, TestReport } from '../../../services/browserTestApi';

const ROUTE_PRESETS: Record<string, string[]> = {
  '全部（默认85条）': [],
  '快速冒烟（5条）': ['/overview', '/core/agents', '/workspace/agents', '/diagnostics', '/alerts'],
  '核心能力层': [
    '/core/agents', '/core/skills', '/core/tools', '/core/mcp',
    '/core/workflows', '/core/resources', '/core/variables', '/core/credentials',
    '/core/memory', '/core/prompts', '/core/jobs',
  ],
  '应用库': [
    '/workspace/agents', '/workspace/skills', '/workspace/marketplace',
    '/workspace/packages', '/workspace/mcp',
  ],
  '诊断层': ['/diagnostics', '/diagnostics/runs', '/diagnostics/traces', '/diagnostics/audit'],
};

const BrowserTestPanel: React.FC = () => {
  // ── config state ──
  const [baseUrl, setBaseUrl] = useState('http://localhost:5173');
  const [accountsJson, setAccountsJson] = useState('');
  const [routePreset, setRoutePreset] = useState('快速冒烟（5条）');
  const [customRoutes, setCustomRoutes] = useState('');
  const [maxDepth, setMaxDepth] = useState(2);
  const [includePatterns, setIncludePatterns] = useState('');
  const [allowWrites, setAllowWrites] = useState(false);
  const [actionTimeout, setActionTimeout] = useState(15000);

  // ── run state ──
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<TestStatus | null>(null);
  const [report, setReport] = useState<TestReport | null>(null);
  const [expandedPages, setExpandedPages] = useState<Set<string>>(new Set());
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── polling ──
  const startPolling = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const s = await browserTestApi.status();
        setStatus(s);
        if (!s.running) {
          if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
          try {
            const r = await browserTestApi.report(true);
            setReport(r);
            setStatus(s);
          } catch {}
        }
      } catch {}
    }, 2000);
  }, []);

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  // ── actions ──
  const startTest = async () => {
    setLoading(true);
    setReport(null);
    setStatus(null);
    try {
      let accounts: any[] = [];
      if (accountsJson.trim()) {
        try { accounts = JSON.parse(accountsJson); } catch {
          toast.error('accounts JSON 格式错误');
          setLoading(false);
          return;
        }
      }

      let routes: string[] = ROUTE_PRESETS[routePreset] || [];
      if (customRoutes.trim()) {
        routes = customRoutes.split(/[\n,]+/).map(s => s.trim()).filter(Boolean);
      }

      const r = await browserTestApi.start({
        base_url: baseUrl,
        routes,
        accounts,
        max_recursion_depth: maxDepth,
        include_patterns: includePatterns.trim() ? includePatterns.split(/[\n,]+/).map(s => s.trim()).filter(Boolean) : undefined,
        allow_writes: allowWrites,
        action_timeout_ms: actionTimeout,
        login_url: '',
      });
      if (r.ok) {
        toast.success('浏览器测试已启动');
        startPolling();
      } else {
        toast.error('启动失败');
      }
    } catch (e: any) {
      toast.error(`错误: ${e?.message || e}`);
    } finally {
      setLoading(false);
    }
  };

  const stopTest = async () => {
    try {
      await browserTestApi.stop();
      toast.success('测试已停止');
    } catch (e: any) {
      toast.error(`停止失败: ${e?.message || e}`);
    }
  };

  const togglePage = (url: string) => {
    setExpandedPages(prev => {
      const next = new Set(prev);
      if (next.has(url)) next.delete(url); else next.add(url);
      return next;
    });
  };

  // ── computed ──
  const summary = status?.summary;
  const passRate = summary && summary.total_actions > 0
    ? Math.round((summary.passed / summary.total_actions) * 100) : 0;
  const isRunning = status?.running || false;
  const badgeVariant = (r: string): 'success' | 'error' | 'warning' | 'default' | 'info' =>
    r === 'passed' ? 'success' : r === 'failed' ? 'error' : r === 'skipped' ? 'warning' : 'default';

  return (
    <div style={{ padding: 20, maxWidth: 1100 }}>
      <h2 style={{ margin: 0 }}>浏览器自动化测试</h2>
      <p style={{ color: '#888', margin: '4px 0 16px' }}>
        自动遍历所有页面，对每个交互元素执行操作，输出测试报告
      </p>

      {/* ── Config Card ── */}
      <div style={{ marginBottom: 16 }}>
        <Card>
        <CardHeader title="测试配置" />
        <CardContent>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <label>Base URL</label>
              <Input value={baseUrl} onChange={e => setBaseUrl(e.target.value)} placeholder="http://localhost:5173" />
            </div>
            <div>
              <label>路由预设</label>
              <Select value={routePreset} onChange={setRoutePreset}
                options={Object.keys(ROUTE_PRESETS).map(k => ({ value: k, label: k }))} />
            </div>
            <div>
              <label>自定义路由（每行一个，逗号分隔）</label>
              <Textarea value={customRoutes} onChange={e => setCustomRoutes(e.target.value)}
                placeholder="留空则用预设路由" rows={2} />
            </div>
            <div>
              <label>测试账号 (JSON数组)</label>
              <Textarea value={accountsJson} onChange={e => setAccountsJson(e.target.value)}
                placeholder='[{"username":"admin","password":"admin"}]' rows={2} />
            </div>
            <div>
              <label>最大递归深度</label>
              <Input type="number" value={maxDepth} onChange={e => setMaxDepth(Number(e.target.value))} min={1} max={5} />
            </div>
            <div>
              <label>URL 白名单（正则，逗号分隔。如 #/careers）</label>
              <Input value={includePatterns} onChange={e => setIncludePatterns(e.target.value)}
                placeholder="不填则不过滤" />
            </div>
            <div>
              <label>操作超时(ms)</label>
              <Input type="number" value={actionTimeout} onChange={e => setActionTimeout(Number(e.target.value))} min={1000} />
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <input type="checkbox" checked={allowWrites} onChange={e => setAllowWrites(e.target.checked)} />
              <label>允许写操作（含创建/提交）</label>
            </div>
          </div>
          <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
            <Button onClick={startTest} disabled={loading || isRunning} variant="primary">
              {loading ? '启动中...' : isRunning ? '运行中...' : '▶ 启动测试'}
            </Button>
            <Button onClick={stopTest} disabled={!isRunning} variant="danger">
              ⏹ 停止
            </Button>
          </div>
          </CardContent>
        </Card>
        </div>

      {/* ── Status Bar ── */}
      {status && (
        <div style={{ marginBottom: 16 }}>
          <Card>
          <CardContent>
            <div style={{ display: 'flex', gap: 24, alignItems: 'center', flexWrap: 'wrap' }}>
              <div><Badge variant={isRunning ? 'info' : report ? 'success' : 'default'}>{isRunning ? '运行中' : report ? '已完成' : status.status}</Badge></div>
              {summary && (
                <>
                  <div>页面: <strong>{summary.total_pages}</strong></div>
                  <div>操作: <strong>{summary.total_actions}</strong></div>
                  <div style={{ color: 'green' }}>通过: <strong>{summary.passed}</strong></div>
                  <div style={{ color: 'red' }}>失败: <strong>{summary.failed}</strong></div>
                  <div style={{ color: 'orange' }}>跳过: <strong>{summary.skipped}</strong></div>
                  <div>耗时: <strong>{(summary.duration_ms / 1000).toFixed(1)}s</strong></div>
                  {passRate > 0 && (
                    <div>通过率: <strong style={{ color: passRate >= 90 ? 'green' : 'red' }}>{passRate}%</strong></div>
                  )}
                </>
              )}
            </div>
            {/* Progress bar */}
            {isRunning && summary && summary.total_actions > 0 && (
              <div style={{ marginTop: 8, background: '#eee', borderRadius: 4, height: 8, overflow: 'hidden' }}>
                <div style={{
                  width: `${Math.round(((summary.passed + summary.failed) / Math.max(summary.total_actions, 1)) * 100)}%`,
                  height: '100%', background: '#1890ff', transition: 'width 0.3s',
                }} />
              </div>
            )}
          </CardContent>
        </Card>
        </div>
      )}

      {/* ── Report Detail ── */}
      {report?.pages && (
        <Card>
          <CardHeader title={`测试报告 — ${report.pages.length} 页`} />
          <CardContent>
            {report.errors.length > 0 && (
              <div style={{ background: '#fff2f0', border: '1px solid #ffccc7', padding: 8, marginBottom: 12, borderRadius: 4 }}>
                <strong>错误:</strong> {report.errors.join(' | ')}
              </div>
            )}
            {report.pages.map(p => (
              <div key={p.url} style={{ marginBottom: 8, border: '1px solid #f0f0f0', borderRadius: 6, overflow: 'hidden' }}>
                <div onClick={() => togglePage(p.url)}
                  style={{ padding: '10px 14px', cursor: 'pointer', background: '#fafafa', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <Tag color={p.loaded ? 'green' : 'red'}>{p.loaded ? 'LOADED' : 'FAIL'}</Tag>
                    <span style={{ marginLeft: 8, fontFamily: 'monospace', fontSize: 13 }}>{p.url}</span>
                    {p.modals_detected > 0 && <span style={{ marginLeft: 8, color: '#888', fontSize: 12 }}>弹窗×{p.modals_detected}</span>}
                  </div>
                  <div style={{ fontSize: 12, color: '#888' }}>
                    {p.elements_found} 元素 · {p.actions.length} 操作
                  </div>
                </div>
                {expandedPages.has(p.url) && (
                  <div style={{ padding: '0 14px 10px' }}>
                    <details className="bg-dark-card border border-dark-border rounded-lg px-3 py-2 text-xs text-gray-500 cursor-pointer group mb-2">
                      <summary className="text-gray-400 hover:text-gray-200 select-none">📖 表头说明</summary>
                      <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1.5">
                        <div><span className="text-gray-300">#</span><span className="ml-2 text-gray-600">步骤序号</span></div>
                        <div><span className="text-gray-300">操作</span><span className="ml-2 text-gray-600">浏览器操作类型（click/type/navigate等）</span></div>
                        <div><span className="text-gray-300">元素角色</span><span className="ml-2 text-gray-600">目标元素的 ARIA role</span></div>
                        <div><span className="text-gray-300">元素文本</span><span className="ml-2 text-gray-600">目标元素的文本内容（截断40字）</span></div>
                        <div><span className="text-gray-300">结果</span><span className="ml-2 text-gray-600">通过/失败/跳过</span></div>
                        <div><span className="text-gray-300">耗时</span><span className="ml-2 text-gray-600">步骤执行时间（毫秒）</span></div>
                        <div><span className="text-gray-300">错误</span><span className="ml-2 text-gray-600">失败时的错误信息（截断60字）</span></div>
                      </div>
                    </details>
                    <Table
                      columns={[
                        { title: '#', dataIndex: 'step_id', key: 'step_id', width: 50 },
                        { title: '操作', dataIndex: 'action', key: 'action', width: 130,
                          render: (v: string) => <Tag>{v}</Tag> },
                        { title: '元素角色', dataIndex: 'element_role', key: 'role', width: 120 },
                        { title: '元素文本', dataIndex: 'element_text', key: 'text', width: 150,
                          render: (v: string) => <span style={{ fontSize: 12, color: '#666' }}>{v?.slice(0, 40)}</span> },
                        { title: '结果', dataIndex: 'result', key: 'result', width: 80,
                          render: (v: string) => <Badge variant={badgeVariant(v)}>{v}</Badge> },
                        { title: '耗时', dataIndex: 'duration_ms', key: 'dur', width: 80,
                          render: (v: number) => v ? `${v}ms` : '-' },
                        { title: '错误', dataIndex: 'error', key: 'err', width: 200,
                          render: (v: string) => v ? <span style={{ color: 'red', fontSize: 12 }}>{v.slice(0, 60)}</span> : '-' },
                      ]}
                      data={p.actions.map(a => ({ ...a, key: `${p.url}-${a.step_id}` }))}
                      rowKey="key"
                    />
                  </div>
                )}
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default BrowserTestPanel;
