import React, { useMemo, useState } from 'react';
import { Search } from 'lucide-react';
import { workspaceMcpApi } from '../../services';
import type { McpServer } from '../../services';
import { Alert, Button, Input, Modal, Select, Switch, Textarea, toast } from '../ui';
import { diagnosticsApi } from '../../services';

interface DiscoveredTool {
  name: string;
  description: string;
  has_parameters: boolean;
}

interface AddMcpModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
  onCreated?: (serverName: string) => void;
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

const MCP_HELP = `### 如何创建 MCP Server
**目标：** 把一组 MCP tools 安全地接入平台，并用 allowed_tools 做最小白名单。

#### transport 怎么选
- **sse/http（推荐优先）**：远程服务型 MCP，风险更可控。填写 \`url\`，建议配置 \`auth\`。
- **stdio（高风险）**：等同于在 core 机器上启动本机进程。prod 必须走放行策略（白名单/前缀/launcher）。

#### allowed_tools 怎么填
- 新建后先保持 enabled=false
- 进入编辑页点击"发现工具（tools/list）"获取工具列表
- 只把你确实需要的工具加入 allowed_tools

#### 常见问题排查
- 404 / Not Found：服务未更新或路由未转发；或 MCP server 未启用/未被加载
- tools/call 失败：常见是 auth/token 不对、allowed_tools 未放行
- stdio prod：若 policy-check 不通过，需要配置 allowlist/command prefixes（以及可选统一 launcher 强制）`;

const LOCAL_TOOLS_HELP = `### 📦 本地工作台工具
**自动扫描 ~/.aiplat/tools/ 下的 Python 工具文件，以 MCP 协议暴露给 Agent。**

#### 工作原理
1. 启用后 aiPlat 启动内置的 MCP stdio 子进程
2. 子进程读取 ~/.aiplat/tools/*.py 中的 TOOL_DEF
3. Agent 可通过 \`mcp.<name>.<tool>\` 调用（如 \`mcp.my-tools.test-1\`）

#### 使用建议
- 点击"发现工具"查看可用工具列表
- 勾选你要暴露的工具（不勾 = 不暴露）
- 在 ~/.aiplat/tools/ 下新增 .py 后，重新启用 MCP 即可同步`;

const AddMcpModal: React.FC<AddMcpModalProps> = ({ open, onClose, onSuccess, onCreated }) => {
  const [loading, setLoading] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [name, setName] = useState('');
  const [enabled, setEnabled] = useState(false);
  const [transport, setTransport] = useState('sse');
  const [url, setUrl] = useState('');
  const [command, setCommand] = useState('');
  const [argsText, setArgsText] = useState('[]');
  const [allowedToolsText, setAllowedToolsText] = useState('');
  const [authText, setAuthText] = useState('');
  const [metadataText, setMetadataText] = useState('{\n  "description": ""\n}');
  const [autoSmoke, setAutoSmoke] = useState(true);
  const [launcherPath, setLauncherPath] = useState('/opt/aiplat/mcp/bin/launch');
  const [template, setTemplate] = useState('sse_internal');
  const [wizOpen, setWizOpen] = useState(false);
  const [wizTransport, setWizTransport] = useState<'sse' | 'http' | 'stdio'>('sse');
  const [wizIsProd, setWizIsProd] = useState(false);
  const [wizNeedAuth, setWizNeedAuth] = useState(true);
  const [genWarnings, setGenWarnings] = useState<string[]>([]);

  // Local tools discovery state
  const [discoveredTools, setDiscoveredTools] = useState<DiscoveredTool[]>([]);
  const [discovering, setDiscovering] = useState(false);
  const [checkedTools, setCheckedTools] = useState<Set<string>>(new Set());

  const isLocalTools = template === 'local_tools';

  const hint = useMemo(() => {
    if (isLocalTools) return 'STDIO 模式 — 自动连接 ~/.aiplat/tools/ 下的 Python 工具。';
    if (transport === 'stdio') return 'stdio 模式通常使用 command + args（例如：node / python / 本地可执行文件）。';
    return 'sse/http 模式通常使用 url（例如：http://localhost:0/mcp）。';
  }, [transport, isLocalTools]);

  const riskHint = useMemo(() => {
    if (isLocalTools) return '低风险（L1）：本地工具，仅暴露 ~/.aiplat/tools/ 下已勾选的文件。';
    if (transport === 'stdio') {
      return '高风险（L3）：等同于在 core 所在机器上启动本机进程执行。prod 建议使用"服务器白名单 + 命令前缀白名单 + metadata.prod_allowed=true"，并可进一步开启"统一 launcher"强约束。';
    }
    return '中风险（L2）：远程服务型 MCP。建议配置鉴权（auth）并用 allowed_tools 做最小白名单。';
  }, [transport, isLocalTools]);

  const applyLauncherTemplate = () => {
    const serverName = (name || 'server_name').trim() || 'server_name';
    setTransport('stdio');
    setCommand(launcherPath);
    setArgsText(JSON.stringify([serverName, '--config', `/etc/aiplat/mcp/${serverName}.yaml`], null, 2));
  };

  const applyMcpTemplate = () => {
    const serverName = (name || 'server_name').trim() || 'server_name';
    const baseMeta = (() => {
      try {
        return metadataText.trim() ? JSON.parse(metadataText) : {};
      } catch {
        return {};
      }
    })();

    if (template === 'local_tools') {
      setTransport('stdio');
      setUrl('');
      setCommand('python3');
      setArgsText(JSON.stringify(['-m', 'core.apps.mcp.local_tools_server'], null, 2));
      setAuthText('');
      setAllowedToolsText('');
      setMetadataText(JSON.stringify({ ...baseMeta, description: baseMeta.description || '本地工作台工具（~/.aiplat/tools/）', prod_allowed: false }, null, 2));
      setGenWarnings(['点击下方"发现工具"查看可暴露的工具列表，勾选后创建。']);
      return;
    }

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
  };

  const handleAiFill = async () => {
    if (!name.trim()) return;
    setAiLoading(true);
    try {
      let desc = '';
      try {
        const meta = JSON.parse(metadataText || '{}');
        desc = meta.description || '';
      } catch {}
      const res = await fetch('/api/core/workspace/mcp/servers/auto-fill', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim(), description: desc.trim() || name.trim() }),
      });
      const data = await res.json();
      if (!res.ok) {
        toast.error('AI 填充失败', data.detail || data.message || `HTTP ${res.status}`);
        return;
      }
      if (data.error) {
        toast.error('AI 填充失败', data.error);
        return;
      }
      if (data.transport) setTransport(data.transport);
      if (data.url !== undefined) setUrl(data.url || '');
      if (data.command !== undefined) setCommand(data.command || '');
      if (data.args) setArgsText(JSON.stringify(data.args, null, 2));
      if (data.allowed_tools) setAllowedToolsText(data.allowed_tools.join('\n'));
      if (data.auth) setAuthText(JSON.stringify(data.auth, null, 2));
      if (data.metadata) setMetadataText(JSON.stringify(data.metadata, null, 2));
      toast.success('AI 已填充 MCP 配置');
    } catch (e: any) {
      toast.error('AI 填充失败', e?.message || String(e));
    } finally { setAiLoading(false); }
  };

  const handleDiscover = async () => {
    setDiscovering(true);
    setDiscoveredTools([]);
    try {
      if (isLocalTools) {
        const res = await fetch('/api/core/workspace/tools/discover', { method: 'POST' });
        const data = await res.json();
        const tools: DiscoveredTool[] = data.tools || [];
        setDiscoveredTools(tools);
        setCheckedTools(new Set(tools.map(t => t.name)));
        if (tools.length === 0) {
          toast.info('未发现工具，请先在 ~/.aiplat/tools/ 下创建 .py 文件');
        } else {
          toast.success(`发现 ${tools.length} 个工具`);
        }
      } else {
        toast.info('外部 MCP Server 请先创建并启用，然后在编辑页使用发现工具获取工具列表。', { duration: 5000 } as any);
      }
    } catch {
      toast.error('发现工具失败');
      setDiscoveredTools([]);
    } finally {
      setDiscovering(false);
    }
  };

  const toggleTool = (toolName: string) => {
    setCheckedTools(prev => {
      const next = new Set(prev);
      if (next.has(toolName)) next.delete(toolName);
      else next.add(toolName);
      return next;
    });
  };

  const toggleAll = () => {
    if (checkedTools.size === discoveredTools.length) {
      setCheckedTools(new Set());
    } else {
      setCheckedTools(new Set(discoveredTools.map(t => t.name)));
    }
  };

  const openWizard = () => {
    setWizOpen(true);
    setWizTransport((transport as any) || 'sse');
    const meta = (() => {
      try {
        return metadataText.trim() ? JSON.parse(metadataText) : {};
      } catch {
        return {};
      }
    })();
    setWizIsProd(Boolean((meta as any)?.prod_allowed));
    setWizNeedAuth(Boolean(url) || transport === 'sse' || transport === 'http');
  };

  const applyWizardGenerate = () => {
    if (wizTransport === 'stdio') setTemplate(wizIsProd ? 'stdio_launcher_prod' : 'stdio_launcher_dev');
    else if (wizTransport === 'http') setTemplate('http_internal');
    else setTemplate('sse_internal');

    const serverName = (name || 'server_name').trim() || 'server_name';
    const baseMeta = (() => {
      try {
        return metadataText.trim() ? JSON.parse(metadataText) : {};
      } catch {
        return {};
      }
    })();

    if (wizTransport === 'stdio') {
      setTransport('stdio');
      setUrl('');
      setCommand(launcherPath);
      setArgsText(JSON.stringify([serverName, '--config', `/etc/aiplat/mcp/${serverName}.yaml`], null, 2));
      setAllowedToolsText('');
      setAuthText('');
      setMetadataText(
        JSON.stringify(
          { ...baseMeta, description: baseMeta.description || `STDIO MCP（${wizIsProd ? 'prod 受控' : 'dev/staging'}，launcher）`, prod_allowed: wizIsProd },
          null, 2
        )
      );
    } else if (wizTransport === 'http') {
      setTransport('http');
      setUrl('http://localhost:0/mcp');
      setCommand('');
      setArgsText('[]');
      setAllowedToolsText('');
      setAuthText(wizNeedAuth ? '{\n  "type": "bearer",\n  "token": ""\n}' : '');
      setMetadataText(JSON.stringify({ ...baseMeta, description: baseMeta.description || '内部 HTTP MCP Server' }, null, 2));
    } else {
      setTransport('sse');
      setUrl('http://localhost:0/mcp');
      setCommand('');
      setArgsText('[]');
      setAllowedToolsText('');
      setAuthText(wizNeedAuth ? '{\n  "type": "bearer",\n  "token": ""\n}' : '');
      setMetadataText(JSON.stringify({ ...baseMeta, description: baseMeta.description || '内部 SSE MCP Server' }, null, 2));
    }

    const warns: string[] = [];
    if (wizTransport === 'stdio' && wizIsProd) {
      warns.push('STDIO prod 受控：需要 metadata.prod_allowed=true 且 prod 放行策略环境变量已配置。');
      warns.push('allowed_tools 不会自动填充：创建后请点击"发现工具"并再启用。');
    }
    if ((wizTransport === 'http' || wizTransport === 'sse') && !wizNeedAuth) {
      warns.push('HTTP/SSE 未启用鉴权：请确认该 MCP Server 仅在内网可信环境使用。');
    }
    setGenWarnings(warns);
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

  const handleSubmit = async () => {
    if (!name.trim()) {
      toast.error('请输入 MCP Server 名称');
      return;
    }
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

      // For local tools: use checked tools as allowed_tools
      let finalAllowedTools: string[] = [];
      if (isLocalTools) {
        finalAllowedTools = Array.from(checkedTools);
      } else {
        finalAllowedTools = allowedToolsText
          .split('\n')
          .map((s) => s.trim())
          .filter(Boolean);
      }

      const payload: McpServer = {
        name: name.trim(),
        enabled,
        transport,
        url: url.trim() || undefined,
        command: command.trim() || undefined,
        args,
        allowed_tools: finalAllowedTools,
        source: isLocalTools ? 'internal' : 'external',
        ...(auth ? { auth } : {}),
        ...(metadata ? { metadata } : {}),
      } as any;

      await workspaceMcpApi.upsertServer(payload);
      toast.success('已创建 MCP Server');
      onSuccess();
      if (onCreated && enabled) {
        onCreated(name.trim());
      }
      if (autoSmoke) {
        try {
          const smoke = await diagnosticsApi.runE2ESmoke({ tenant_id: 'ops_smoke', actor_id: 'admin', agent_model: 'deepseek-reasoner' });
          if (smoke?.ok) {
            toast.success('全链路冒烟通过');
          } else {
            toast.warning('MCP Server 已创建，但全链路冒烟未全部通过（可在诊断页查看详情）');
          }
        } catch (e: any) {
          toast.warning('MCP Server 已创建，但全链路冒烟异常（可在诊断页重试）');
        }
      }
      resetForm();
      onClose();
    } catch (e: any) {
      toast.error('创建失败', String(e?.message || ''));
    } finally {
      setLoading(false);
    }
  };

  const resetForm = () => {
    setName('');
    setEnabled(false);
    setTransport('sse');
    setUrl('');
    setCommand('');
    setArgsText('[]');
    setAllowedToolsText('');
    setAuthText('');
    setMetadataText('{\n  "description": ""\n}');
    setTemplate('sse_internal');
    setDiscoveredTools([]);
    setCheckedTools(new Set());
    setGenWarnings([]);
  };

  return (
    <>
    <Modal
      open={open}
      onClose={() => { resetForm(); onClose(); }}
      title="新增应用库 MCP Server"
      width={isLocalTools ? 1080 : 1080}
      footer={
        <>
          <Button variant="secondary" onClick={() => { resetForm(); onClose(); }} disabled={loading}>
            取消
          </Button>
          <Button variant="primary" onClick={handleSubmit} loading={loading}>
            保存
          </Button>
        </>
      }
    >
      <label className="mb-3 flex items-center gap-2 text-sm text-gray-400">
        <input type="checkbox" checked={autoSmoke} onChange={(e) => setAutoSmoke(e.target.checked)} />
        创建后自动运行全链路冒烟（会创建/清理资源）
      </label>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-4">
          <Input label="名称" value={name} onChange={(e: any) => setName(e.target.value)} placeholder="例如：my-tools" />

          <Alert type={isLocalTools ? 'success' : transport === 'stdio' ? 'warning' : 'info'} title="风险提示">
            {riskHint}
          </Alert>

          <div className="flex items-end justify-between gap-3">
            <div className="flex-1">
              <Select label="模板" value={template} onChange={(v) => setTemplate(v)} options={MCP_TEMPLATES} />
            </div>
            <Button variant="secondary" onClick={() => applyMcpTemplate()} disabled={loading}>
              应用模板
            </Button>
            <Button variant="secondary" onClick={() => { handleDiscover(); }} disabled={loading}>
              发现工具
            </Button>
            {!isLocalTools && (
              <>
                <Button variant="primary" onClick={openWizard} disabled={loading}>
                  向导
                </Button>
              </>
            )}
            <Button variant="secondary" onClick={handleAiFill} loading={aiLoading}
              disabled={!name.trim() || aiLoading}>
              ✨ AI 智能填充
            </Button>
            <span className="text-xs text-gray-500">根据名称和功能描述自动推荐 transport / url / command / Args / allowed_tools / 鉴权配置</span>
          </div>

          {!isLocalTools && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Select label="Transport" value={transport} onChange={(v) => setTransport(v)} options={TRANSPORTS} />
              <div className="flex items-center justify-between gap-3 pt-6">
                <div className="text-sm text-gray-300">enabled</div>
                <Switch checked={enabled} onChange={() => setEnabled(!enabled)} />
              </div>
            </div>
          )}

          {!isLocalTools && (
            <Input label="url（sse/http）" value={url} onChange={(e: any) => setUrl(e.target.value)} placeholder="http://localhost:0/mcp" />
          )}

          {!isLocalTools && transport === 'stdio' && (
            <div className="flex items-end justify-between gap-3">
              <Input label="prod launcher（可选）" value={launcherPath} onChange={(e: any) => setLauncherPath(e.target.value)} placeholder="/opt/aiplat/mcp/bin/launch" />
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

          {!isLocalTools && (
            <>
              <Input label="command（stdio）" value={command} onChange={(e: any) => setCommand(e.target.value)} placeholder="例如：node /usr/local/bin/mcp-server.js" />
              <Textarea label="args（JSON 数组）" rows={3} value={argsText} onChange={(e: any) => setArgsText(e.target.value)} />
              <Textarea label="allowed_tools（每行一个）" rows={5} value={allowedToolsText} onChange={(e: any) => setAllowedToolsText(e.target.value)} placeholder="browser_navigate\nbrowser_snapshot" />
              <Textarea label="auth（JSON，可选）" rows={4} value={authText} onChange={(e: any) => setAuthText(e.target.value)} placeholder='{"type":"bearer","token":"..."}' />
              <Textarea label="metadata（JSON，可选）" rows={5} value={metadataText} onChange={(e: any) => setMetadataText(e.target.value)} />
            </>
          )}

          {/* === 发现工具（所有类型通用）=== */}
          <div className="space-y-3 border border-dark-border rounded-lg p-3 bg-dark-card">
            <div className="flex items-center justify-between">
              <div className="text-sm font-medium text-gray-200">
                {isLocalTools ? '可暴露的工具' : 'allowed_tools'}
              </div>
              <Button
                variant="secondary"
                icon={<Search size={14} />}
                onClick={handleDiscover}
                loading={discovering}
                size="sm"
              >
                发现工具
              </Button>
            </div>

            {isLocalTools && (
              <>
                {discoveredTools.length === 0 && !discovering && (
                  <p className="text-xs text-gray-500 text-center py-2">
                    点击"发现工具"扫描 ~/.aiplat/tools/ 下的可用工具
                  </p>
                )}
                {discovering && <p className="text-xs text-gray-500 text-center py-2">扫描中...</p>}
                {discoveredTools.length > 0 && (
                  <div className="max-h-48 overflow-y-auto space-y-1">
                    <div className="flex items-center gap-2 mb-1">
                      <button onClick={toggleAll} className="text-xs text-primary hover:text-primary-hover">
                        {checkedTools.size === discoveredTools.length ? '取消全选' : '全选'}
                      </button>
                    </div>
                    {discoveredTools.map((t) => (
                      <label key={t.name}
                        className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-dark-hover cursor-pointer text-sm text-gray-300">
                        <input
                          type="checkbox"
                          checked={checkedTools.has(t.name)}
                          onChange={() => toggleTool(t.name)}
                          className="w-3.5 h-3.5 rounded"
                        />
                        <span className="font-mono text-xs text-gray-200">{t.name}</span>
                        <span className="text-xs text-gray-500 truncate flex-1">— {t.description || '无描述'}</span>
                      </label>
                    ))}
                  </div>
                )}
              </>
            )}

            {!isLocalTools && (
              <p className="text-xs text-gray-500 text-center py-2">
                外部 MCP：点击"发现工具"获取提示。创建并启用后，在编辑页可实时调用 tools/list 获取工具列表。
              </p>
            )}

            {/* Transport + enabled for local tools */}
            {isLocalTools && (
              <div className="grid grid-cols-2 gap-3 pt-2 border-t border-dark-border">
                <div>
                  <div className="text-xs text-gray-400 mb-1">Transport</div>
                  <div className="text-sm text-gray-200 font-mono bg-dark-bg px-2 py-1.5 rounded border border-dark-border">stdio</div>
                </div>
                <div className="flex items-center gap-3 pt-5">
                  <div className="text-sm text-gray-300">enabled</div>
                  <Switch checked={enabled} onChange={() => setEnabled(!enabled)} />
                </div>
              </div>
            )}
          </div>

          {genWarnings.length > 0 && (
            <Alert type="warning" title="提示">
              <ul className="list-disc pl-5 space-y-1">
                {genWarnings.map((w, i) => (
                  <li key={i} className="text-xs">{w}</li>
                ))}
              </ul>
            </Alert>
          )}

          <div className="text-xs text-gray-500">{hint}</div>
        </div>

        <div className="border border-dark-border rounded-lg bg-dark-card p-3">
          <div className="text-sm font-medium text-gray-200 mb-2">使用说明 / 示例</div>
          <div className="text-xs text-gray-300 whitespace-pre-wrap leading-relaxed">
            {isLocalTools ? LOCAL_TOOLS_HELP : MCP_HELP}
          </div>
          {!isLocalTools && (
            <div className="mt-3 space-y-2">
              <div className="text-xs font-medium text-gray-300">常用片段（复制）</div>
              <div className="flex gap-2 flex-wrap">
                <Button variant="secondary" size="sm"
                  onClick={async () => {
                    try { await navigator.clipboard.writeText('{\n  \"type\": \"bearer\",\n  \"token\": \"\"\n}'); toast.success('已复制'); } catch { toast.error('复制失败'); }
                  }} disabled={loading}>
                  复制 bearer auth
                </Button>
                <Button variant="secondary" size="sm"
                  onClick={async () => {
                    try { await navigator.clipboard.writeText('browser_navigate\nbrowser_snapshot'); toast.success('已复制'); } catch { toast.error('复制失败'); }
                  }} disabled={loading}>
                  复制 allowed_tools 示例
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </Modal>

    <Modal
      open={wizOpen}
      onClose={() => setWizOpen(false)}
      title="MCP 向导"
      width={760}
      footer={
        <>
          <Button variant="secondary" onClick={() => setWizOpen(false)} disabled={loading}>取消</Button>
          <Button variant="primary" onClick={() => { applyWizardGenerate(); setWizOpen(false); }} disabled={loading}>生成</Button>
        </>
      }
    >
      <div className="space-y-4">
        <Alert type="info" title="说明">
          通过向导明确 transport 与 prod 约束，避免 stdio/prod 放行配置歧义。allowed_tools 仍需你手动点击 tools/list 发现填充。
        </Alert>
        <div>
          <div className="text-sm font-medium text-gray-300 mb-2">Transport</div>
          <select
            value={wizTransport}
            onChange={(e) => setWizTransport(e.target.value as any)}
            className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100"
          >
            <option value="sse">sse</option>
            <option value="http">http</option>
            <option value="stdio">stdio</option>
          </select>
        </div>
        {wizTransport === 'stdio' && (
          <div>
            <div className="text-sm font-medium text-gray-300 mb-2">是否用于 prod？</div>
            <label className="flex items-center gap-2 text-sm text-gray-200">
              <input type="checkbox" checked={wizIsProd} onChange={() => setWizIsProd(!wizIsProd)} />
              是（将套用 prod 受控 launcher，并设置 metadata.prod_allowed=true）
            </label>
          </div>
        )}
        {(wizTransport === 'http' || wizTransport === 'sse') && (
          <div>
            <div className="text-sm font-medium text-gray-300 mb-2">是否需要鉴权？</div>
            <label className="flex items-center gap-2 text-sm text-gray-200">
              <input type="checkbox" checked={wizNeedAuth} onChange={() => setWizNeedAuth(!wizNeedAuth)} />
              需要（将预填 bearer token auth）
            </label>
          </div>
        )}
      </div>
    </Modal>
    </>
  );
};

export default AddMcpModal;
