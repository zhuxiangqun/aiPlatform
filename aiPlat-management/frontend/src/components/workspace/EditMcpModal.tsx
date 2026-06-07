import React, { useEffect, useMemo, useState } from 'react';
import { RotateCw, CheckSquare, Square } from 'lucide-react';
import { workspaceMcpApi } from '../../services';
import type { McpServer } from '../../services';
import { Alert, Button, Input, Modal, Select, Switch, Textarea, toast } from '../ui';

interface EditMcpModalProps {
  open: boolean;
  server: McpServer | null;
  onClose: () => void;
  onSuccess: () => void;
  autoDiscover?: boolean;
}

const TRANSPORTS = [
  { value: 'sse', label: 'sse' },
  { value: 'http', label: 'http' },
  { value: 'stdio', label: 'stdio' },
];

const MCP_TEMPLATES = [
  { value: 'sse_internal', label: 'SSE（内部服务）' },
  { value: 'http_internal', label: 'HTTP（内部服务）' },
  { value: 'stdio_launcher_dev', label: 'STDIO + Launcher（dev/staging）' },
  { value: 'stdio_launcher_prod', label: 'STDIO + Launcher（prod 受控）' },
  { value: 'local_tools', label: '📦 本地工作台工具' },
];

const LOCAL_TOOLS_HELP = `### 📦 本地工作台工具
**自动扫描 ~/.aiplat/tools/ 下的 Python 工具文件，以 MCP 协议暴露给 Agent。**

#### 工具管理
- 点击"发现工具（tools/list）"查看当前可用工具
- 在 allowed_tools 中只保留需要暴露的工具
- 在 ~/.aiplat/tools/ 下新增 .py 后，重新启用即可同步

#### 命令配置
- command: python3（使用系统 Python 解释器）
- args: ["-m", "core.apps.mcp.local_tools_server"]
- 子进程自动继承服务器的 PYTHONPATH 环境变量`;

const MCP_HELP = `### 如何配置 MCP Server
**transport 选择：**
- **sse/http（推荐）**：填写 url；建议配置鉴权 auth；通过 allowed_tools 控制最小权限。
- **stdio（高风险）**：启动本机进程。prod 必须通过放行策略（allowlist/command prefixes/可选统一 launcher）。

**allowed_tools：**
- 建议先 enabled=false
- 点击“发现工具（tools/list）”获取工具列表
- 只保留必要工具，避免全量放行

**常见排查：**
- tools/list 失败：url/command 不正确或鉴权失败
- tools/call 失败：allowed_tools 未放行、token 过期、server 未启用
- stdio prod：先点“prod 放行检查”确认策略通过`;

const EditMcpModal: React.FC<EditMcpModalProps> = ({ open, server, onClose, onSuccess, autoDiscover }) => {
  const [loading, setLoading] = useState(false);
  const [fetching, setFetching] = useState(false);

  const [enabled, setEnabled] = useState(false);
  const [transport, setTransport] = useState('sse');
  const [url, setUrl] = useState('');
  const [command, setCommand] = useState('');
  const [argsText, setArgsText] = useState('[]');
  const [allowedToolsText, setAllowedToolsText] = useState('');
  const [authText, setAuthText] = useState('');
  const [metadataText, setMetadataText] = useState('');
  const [launcherPath, setLauncherPath] = useState('/opt/aiplat/mcp/bin/launch');
  const [template, setTemplate] = useState('sse_internal');
  const [policyModal, setPolicyModal] = useState<{ open: boolean; title: string; content: string }>({ open: false, title: '', content: '' });
  const [discoveredTools, setDiscoveredTools] = useState<{ name: string; description: string; selected: boolean }[]>([]);
  const [discoveringTools, setDiscoveringTools] = useState(false);
  const [showTools, setShowTools] = useState(false);

  // Seed form from prop immediately on open, then enrich from API
  useEffect(() => {
    if (!open || !server?.name) return;
    // Start with prop data so the form shows correct values instantly (no flash of defaults)
    setEnabled(Boolean(server.enabled));
    setTransport(String(server.transport || 'sse'));
    setUrl(String(server.url || ''));
    setCommand(String(server.command || ''));
    setArgsText(JSON.stringify(server.args || [], null, 2));
    setAllowedToolsText((server.allowed_tools || []).join('\n'));
    setMetadataText(server.metadata ? JSON.stringify(server.metadata, null, 2) : '');
    setDiscoveredTools([]);
    setShowTools(false);

    // Then enrich from full API (may have richer metadata/filesystem info)
    setFetching(true);
    workspaceMcpApi.getServer(server.name).then((detail: any) => {
      const d = detail as McpServer;
      setEnabled(Boolean(d.enabled));
      setTransport(String(d.transport || 'sse'));
      setUrl(String(d.url || ''));
      setCommand(String(d.command || ''));
      setArgsText(JSON.stringify(d.args || [], null, 2));
      setAllowedToolsText((d.allowed_tools || []).join('\n'));
      setAuthText(d.auth ? JSON.stringify(d.auth, null, 2) : '');
      setMetadataText(d.metadata ? JSON.stringify(d.metadata, null, 2) : '');
    }).catch(() => {
      // fallback already applied above
    }).finally(() => setFetching(false));
  }, [open, server?.name]);

  // Auto-discover tools when opened via "新增" flow
  const autoDiscovered = React.useRef(false);
  useEffect(() => {
    if (autoDiscover && !fetching && open && server?.name && !autoDiscovered.current) {
      autoDiscovered.current = true;
      handleDiscover();
    }
    if (!open) {
      autoDiscovered.current = false;
    }
  }, [autoDiscover, fetching, open, server?.name]);

  const isInternal = server?.source === 'internal';

  const hint = useMemo(() => {
    if (isInternal) return 'STDIO 模式 — 自动连接 ~/.aiplat/tools/ 下的 Python 工具。';
    if (transport === 'stdio') return 'stdio 模式通常使用 command + args（例如：node / python / 本地可执行文件）。';
    return 'sse/http 模式通常使用 url（例如：http://localhost:0/mcp）。';
  }, [transport, isInternal]);

  const riskHint = useMemo(() => {
    if (isInternal) return '低风险（L1）：本地工作台工具，仅暴露 ~/.aiplat/tools/ 下已勾选的文件。';
    if (transport === 'stdio') {
      return '高风险（L3）：等同于在 core 所在机器上启动本机进程执行。prod 建议使用"服务器白名单 + 命令前缀白名单 + metadata.prod_allowed=true"，并可进一步开启"统一 launcher"强约束。';
    }
    return '中风险（L2）：远程服务型 MCP。建议配置鉴权（auth）并用 allowed_tools 做最小白名单。';
  }, [transport, isInternal]);

  const applyLauncherTemplate = () => {
    const serverName = (server?.name || 'server_name').trim() || 'server_name';
    setTransport('stdio');
    setCommand(launcherPath);
    setArgsText(JSON.stringify([serverName, '--config', `/etc/aiplat/mcp/${serverName}.yaml`], null, 2));
  };

  const applyMcpTemplate = () => {
    const serverName = (server?.name || 'server_name').trim() || 'server_name';
    const baseMeta = (() => {
      try {
        return metadataText.trim() ? JSON.parse(metadataText) : {};
      } catch {
        return {};
      }
    })();

    if (template === 'sse_internal') {
      setTransport('sse');
      setUrl('http://localhost:0/mcp');
      setCommand('');
      setArgsText('[]');
      setAuthText('{\n  "type": "bearer",\n  "token": ""\n}');
      setAllowedToolsText('');
      setMetadataText(JSON.stringify({ ...baseMeta, description: baseMeta.description || '内部 SSE MCP Server' }, null, 2));
      return;
    }
    if (template === 'http_internal') {
      setTransport('http');
      setUrl('http://localhost:0/mcp');
      setCommand('');
      setArgsText('[]');
      setAuthText('{\n  "type": "bearer",\n  "token": ""\n}');
      setAllowedToolsText('');
      setMetadataText(JSON.stringify({ ...baseMeta, description: baseMeta.description || '内部 HTTP MCP Server' }, null, 2));
      return;
    }
    if (template === 'stdio_launcher_dev') {
      setTransport('stdio');
      setUrl('');
      setCommand(launcherPath);
      setArgsText(JSON.stringify([serverName, '--config', `/etc/aiplat/mcp/${serverName}.yaml`], null, 2));
      setAuthText('');
      setAllowedToolsText('');
      setMetadataText(JSON.stringify({ ...baseMeta, description: baseMeta.description || 'STDIO MCP（dev/staging，launcher）', prod_allowed: false }, null, 2));
      return;
    }
    if (template === 'stdio_launcher_prod') {
      setTransport('stdio');
      setUrl('');
      setCommand(launcherPath);
      setArgsText(JSON.stringify([serverName, '--config', `/etc/aiplat/mcp/${serverName}.yaml`], null, 2));
      setAuthText('');
      setAllowedToolsText('');
      setMetadataText(JSON.stringify({ ...baseMeta, description: baseMeta.description || 'STDIO MCP（prod 受控，launcher）', prod_allowed: true }, null, 2));
      return;
    }
    if (template === 'local_tools') {
      setTransport('stdio');
      setUrl('');
      setCommand('python3');
      setArgsText(JSON.stringify(['-m', 'core.apps.mcp.local_tools_server'], null, 2));
      setAuthText('');
      setAllowedToolsText('');
      setMetadataText(JSON.stringify({ ...baseMeta, description: baseMeta.description || '本地工作台工具（~/.aiplat/tools/）', prod_allowed: false }, null, 2));
      return;
    }
  };

  const markProdAllowed = () => {
    try {
      const cur = metadataText.trim() ? JSON.parse(metadataText) : {};
      const next = { ...(cur || {}), prod_allowed: true };
      setMetadataText(JSON.stringify(next, null, 2));
    } catch {
      toast.error('metadata JSON 格式错误，无法自动设置 prod_allowed');
    }
  };

  const handlePolicyCheck = async () => {
    if (!server?.name) return;
    try {
      const res = await workspaceMcpApi.policyCheck(server.name);
      const ok = Boolean((res as any).ok);
      const env = String((res as any).env || '');
      const transport = String((res as any).transport || '');
      if (ok) {
        toast.success(`策略检查通过（env=${env}, transport=${transport}）`);
        setPolicyModal({ open: true, title: '策略检查：通过', content: JSON.stringify(res, null, 2) });
      } else {
        toast.error(`策略检查未通过：${String((res as any).reason || '')}`);
        setPolicyModal({ open: true, title: '策略检查：未通过', content: JSON.stringify(res, null, 2) });
      }
    } catch (e: any) {
      toast.error('策略检查失败', String(e?.message || ''));
    }
  };

  const handleDiscover = async () => {
    if (!server?.name) return;
    setDiscoveringTools(true);
    try {
      let tools: { name: string; description: string }[] = [];

      if (isInternal) {
        // Local tools: scan ~/.aiplat/tools/ directly
        const res = await fetch('/api/core/workspace/tools/discover', { method: 'POST' });
        const data = await res.json();
        tools = (data.tools || []).map((t: any) => ({ name: t.name, description: t.description || '' }));
      } else {
        // External MCP: connect and call tools/list
        const res = await workspaceMcpApi.discoverTools(server.name, { timeout_seconds: 25 });
        tools = ((res as any).tools || []).map((t: any) => ({ name: t.name, description: t.description || '' }));
      }

      if (!tools.length) {
        toast.error('未发现工具');
        setDiscoveredTools([]);
        setShowTools(false);
        return;
      }
      setDiscoveredTools(tools.map(t => ({ ...t, selected: true })));
      setShowTools(true);
    } catch (e: any) {
      toast.error('发现工具失败', String(e?.message || ''));
    } finally {
      setDiscoveringTools(false);
    }
  };

  const toggleToolSelect = (idx: number) => {
    setDiscoveredTools(prev => prev.map((t, i) => i === idx ? { ...t, selected: !t.selected } : t));
  };

  const selectAll = () => {
    setDiscoveredTools(prev => prev.map(t => ({ ...t, selected: true })));
  };

  const deselectAll = () => {
    setDiscoveredTools(prev => prev.map(t => ({ ...t, selected: false })));
  };

  const confirmToolSelection = () => {
    const selected = discoveredTools.filter(t => t.selected).map(t => t.name);
    setAllowedToolsText(selected.join('\n'));
    toast.success(`已选择 ${selected.length} 个工具`);
  };

  const handleSubmit = async () => {
    if (!server?.name) return;
    setLoading(true);
    try {
      let args: string[] = [];
      if (argsText.trim()) {
        try {
          const v = JSON.parse(argsText);
          if (Array.isArray(v)) args = v.map((x) => String(x));
          else throw new Error('args 必须是数组');
        } catch {
          toast.error('args JSON 格式错误（应为数组）');
          setLoading(false);
          return;
        }
      }

      let auth: Record<string, unknown> | undefined;
      if (authText.trim()) {
        try {
          auth = JSON.parse(authText);
        } catch {
          toast.error('auth JSON 格式错误（应为对象）');
          setLoading(false);
          return;
        }
      }

      let metadata: Record<string, unknown> | undefined;
      if (metadataText.trim()) {
        try {
          metadata = JSON.parse(metadataText);
        } catch {
          toast.error('metadata JSON 格式错误（应为对象）');
          setLoading(false);
          return;
        }
      }

      const allowed_tools = allowedToolsText
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean);

      await workspaceMcpApi.updateServer(server.name, {
        enabled,
        transport,
        url: url.trim() || undefined,
        command: command.trim() || undefined,
        args,
        allowed_tools,
        source: isInternal ? 'internal' : 'external',
        ...(auth ? { auth } : {}),
        ...(metadata ? { metadata } : {}),
      } as any);
      toast.success('已更新 MCP Server');
      onSuccess();
      onClose();
    } catch (e: any) {
      toast.error('更新失败', String(e?.message || ''));
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
    <Modal
      open={open}
      onClose={onClose}
      title={`编辑应用库 MCP：${server?.name || ''}`}
      width={1080}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={loading}>
            取消
          </Button>
          <Button variant="primary" onClick={handleSubmit} loading={loading} disabled={fetching}>
            保存
          </Button>
        </>
      }
    >
      {fetching ? (
        <div className="text-sm text-gray-500">加载中...</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-4">
          <Input label="名称（只读）" value={server?.name || ''} onChange={() => {}} disabled />

          <Alert type={isInternal ? 'success' : transport === 'stdio' ? 'warning' : 'info'} title="风险提示">
            {riskHint}
          </Alert>

          <details className="bg-dark-card border border-dark-border rounded-lg px-3 py-2 text-xs text-gray-500 cursor-pointer group">
            <summary className="text-gray-400 hover:text-gray-200 select-none">📖 表头说明</summary>
            <div className="mt-2 grid grid-cols-1 gap-x-6 gap-y-1.5">
              <div><span className="text-gray-300">名称</span><span className="ml-2 text-gray-600">只读，不可修改。修改名称需要删除重建。</span></div>
              <div><span className="text-gray-300">Transport</span><span className="ml-2 text-gray-600">传输方式。sse/http 用于远程服务，stdio 用于本机进程。</span></div>
              <div><span className="text-gray-300">enabled</span><span className="ml-2 text-gray-600">开关。启用后 aiPlat 才会连接此 MCP Server 并注册其工具。</span></div>
              <div><span className="text-gray-300">url / command + args</span><span className="ml-2 text-gray-600">远程服务填 url，本机进程填 command（可执行文件路径）+ args（参数数组）。</span></div>
              <div><span className="text-gray-300">allowed_tools</span><span className="ml-2 text-gray-600">该 MCP Server 暴露给 Agent 的工具白名单。点"发现工具"获取列表，只保留需要的。</span></div>
              <div><span className="text-gray-300">auth</span><span className="ml-2 text-gray-600">鉴权配置（JSON）。SSE/HTTP 推荐配置 bearer token。</span></div>
              <div><span className="text-gray-300">metadata</span><span className="ml-2 text-gray-600">扩展元数据（JSON）。包含 description、prod_allowed 等字段。</span></div>
            </div>
          </details>

          {!isInternal && (
            <div className="flex items-end justify-between gap-3">
              <div className="flex-1">
                <Select label="模板" value={template} onChange={(v) => setTemplate(v)} options={MCP_TEMPLATES} />
              </div>
              <Button variant="secondary" onClick={applyMcpTemplate} disabled={loading}>
                应用模板
              </Button>
            </div>
          )}

          {!isInternal && transport === 'stdio' && (
            <div className="flex items-center justify-end">
              <Button variant="secondary" onClick={handlePolicyCheck} disabled={loading}>
                prod 放行检查
              </Button>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Select label="Transport" value={transport} onChange={(v) => setTransport(v)} options={TRANSPORTS} />
            <div className="flex items-center justify-between gap-3 pt-6">
              <div className="text-sm text-gray-300">enabled</div>
              <Switch checked={enabled} onChange={() => setEnabled(!enabled)} />
            </div>
          </div>

          {!isInternal && <Input label="url（sse/http）" value={url} onChange={(e: any) => setUrl(e.target.value)} placeholder="http://localhost:0/mcp" />}
          {!isInternal && transport === 'stdio' && (
            <div className="flex items-end justify-between gap-3">
              <Input
                label="prod launcher（可选）"
                value={launcherPath}
                onChange={(e: any) => setLauncherPath(e.target.value)}
                placeholder="/opt/aiplat/mcp/bin/launch"
              />
              <div className="flex gap-2 pb-1">
                <Button variant="secondary" onClick={applyLauncherTemplate} disabled={loading}>
                  应用 launcher 模板
                </Button>
                <Button variant="secondary" onClick={markProdAllowed} disabled={loading}>
                  metadata.prod_allowed=true
                </Button>
              </div>
            </div>
          )}
          <Input label="command（stdio）" value={command} onChange={(e: any) => setCommand(e.target.value)} placeholder="例如：node /usr/local/bin/mcp-server.js" />
          <Textarea label="args（JSON 数组）" rows={3} value={argsText} onChange={(e: any) => setArgsText(e.target.value)} />

          <div className="flex items-center justify-between gap-3">
            <div className="text-sm font-medium text-gray-300">allowed_tools（每行一个）</div>
            <Button variant="secondary" onClick={handleDiscover} disabled={loading}>
              发现工具（tools/list）
            </Button>
          </div>
          <Textarea rows={5} value={allowedToolsText} onChange={(e: any) => setAllowedToolsText(e.target.value)} />

          <Textarea label="auth（JSON，可选）" rows={4} value={authText} onChange={(e: any) => setAuthText(e.target.value)} />
          <Textarea label="metadata（JSON，可选）" rows={5} value={metadataText} onChange={(e: any) => setMetadataText(e.target.value)} />

          <div className="text-xs text-gray-500">{hint}</div>
        </div>
        <div className="border border-dark-border rounded-lg bg-dark-card p-3">
          {showTools ? (
            <>
              <div className="flex items-center justify-between mb-3">
                <div className="text-sm font-medium text-gray-200">
                  发现的工具 ({discoveredTools.length})
                </div>
                <Button variant="ghost" size="sm" icon={<RotateCw className="w-3 h-3" />} onClick={handleDiscover} loading={discoveringTools}>
                  重新发现
                </Button>
              </div>
              <div className="space-y-1 max-h-64 overflow-y-auto mb-3">
                {discoveredTools.map((t, i) => (
                  <div
                    key={t.name}
                    onClick={() => toggleToolSelect(i)}
                    className={`flex items-start gap-2 p-2 rounded cursor-pointer transition-colors ${
                      t.selected ? 'bg-primary/10 border border-primary/30' : 'bg-dark-bg border border-dark-border hover:border-dark-border/80'
                    }`}
                  >
                    <span className="flex-shrink-0 mt-0.5">
                      {t.selected ? <CheckSquare className="w-3.5 h-3.5 text-primary" /> : <Square className="w-3.5 h-3.5 text-gray-600" />}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="text-xs font-mono text-gray-200">{t.name}</div>
                      {t.description && <div className="text-[10px] text-gray-500 mt-0.5">{t.description}</div>}
                    </div>
                  </div>
                ))}
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <Button variant="ghost" size="sm" onClick={selectAll} disabled={discoveringTools}>全选</Button>
                <Button variant="ghost" size="sm" onClick={deselectAll} disabled={discoveringTools}>取消全选</Button>
                <Button variant="primary" size="sm" onClick={confirmToolSelection} disabled={discoveringTools}>确认选择</Button>
                <span className="text-[10px] text-gray-500 ml-auto">
                  已选 {discoveredTools.filter(t => t.selected).length}/{discoveredTools.length} 个工具
                </span>
              </div>
            </>
          ) : (
            <>
              <div className="text-sm font-medium text-gray-200 mb-2">使用说明 / 示例</div>
              <div className="text-xs text-gray-300 whitespace-pre-wrap leading-relaxed">
                {isInternal ? LOCAL_TOOLS_HELP : MCP_HELP}
              </div>
              {!isInternal && (
              <div className="mt-3 space-y-2">
                <div className="text-xs font-medium text-gray-300">常用片段（复制）</div>
                <div className="flex gap-2 flex-wrap">
                  <Button
                    variant="secondary"
                    onClick={async () => {
                      try { await navigator.clipboard.writeText('{\n  \"type\": \"bearer\",\n  \"token\": \"\"\n}'); toast.success('已复制'); } catch { toast.error('复制失败'); }
                    }}
                    disabled={loading}
                  >
                    复制 bearer auth
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={async () => {
                      try { await navigator.clipboard.writeText('browser_navigate\nbrowser_snapshot'); toast.success('已复制'); } catch { toast.error('复制失败'); }
                    }}
                    disabled={loading}
                  >
                    复制 allowed_tools 示例
                  </Button>
                </div>
              </div>
              )}
            </>
          )}
        </div>
        </div>
      )}
    </Modal>

    <Modal
      open={policyModal.open}
      onClose={() => setPolicyModal({ open: false, title: '', content: '' })}
      title={policyModal.title}
      width={860}
      footer={<Button onClick={() => setPolicyModal({ open: false, title: '', content: '' })}>关闭</Button>}
    >
      <pre className="text-xs bg-dark-hover rounded p-2 overflow-auto max-h-[420px]">{policyModal.content}</pre>
    </Modal>
    </>
  );
};

export default EditMcpModal;
