import React, { useEffect, useMemo, useState } from 'react';
import { workspaceMcpApi } from '../../services/coreApi';
import type { McpServer } from '../../services/coreApi';
import { Alert, Button, Input, Modal, Select, Switch, Textarea, toast } from '../ui';

interface EditMcpModalProps {
  open: boolean;
  server: McpServer | null;
  onClose: () => void;
  onSuccess: () => void;
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
];

const EditMcpModal: React.FC<EditMcpModalProps> = ({ open, server, onClose, onSuccess }) => {
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

  useEffect(() => {
    if (!open || !server?.name) return;
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
      // fallback to list item
      setEnabled(Boolean(server.enabled));
      setTransport(String(server.transport || 'sse'));
      setUrl(String(server.url || ''));
      setCommand(String(server.command || ''));
      setArgsText(JSON.stringify(server.args || [], null, 2));
      setAllowedToolsText((server.allowed_tools || []).join('\n'));
      setMetadataText(server.metadata ? JSON.stringify(server.metadata, null, 2) : '');
    }).finally(() => setFetching(false));
  }, [open, server?.name]);

  const hint = useMemo(() => {
    if (transport === 'stdio') return 'stdio 模式通常使用 command + args（例如：node / python / 本地可执行文件）。';
    return 'sse/http 模式通常使用 url（例如：http://localhost:0/mcp）。';
  }, [transport]);

  const riskHint = useMemo(() => {
    if (transport === 'stdio') {
      return '高风险（L3）：等同于在 core 所在机器上启动本机进程执行。prod 建议使用“服务器白名单 + 命令前缀白名单 + metadata.prod_allowed=true”，并可进一步开启“统一 launcher”强约束。';
    }
    return '中风险（L2）：远程服务型 MCP。建议配置鉴权（auth）并用 allowed_tools 做最小白名单。';
  }, [transport]);

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
    try {
      const res = await workspaceMcpApi.discoverTools(server.name, { timeout_seconds: 10 });
      const tools = (res as any).tools || [];
      if (!tools.length) {
        toast.error('未发现工具（tools/list 返回为空）');
        return;
      }
      setAllowedToolsText(tools.map((t: any) => t.name).filter(Boolean).join('\n'));
      toast.success(`已发现 ${tools.length} 个工具，并已填充到 allowed_tools`);
    } catch (e: any) {
      toast.error('发现工具失败', String(e?.message || ''));
    }
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
      width={820}
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
        <div className="space-y-4">
          <Input label="名称（只读）" value={server?.name || ''} onChange={() => {}} disabled />

          <Alert type={transport === 'stdio' ? 'warning' : 'info'} title="风险提示">
            {riskHint}
          </Alert>

          <div className="flex items-end justify-between gap-3">
            <div className="flex-1">
              <Select label="模板" value={template} onChange={(v) => setTemplate(v)} options={MCP_TEMPLATES} />
            </div>
            <Button variant="secondary" onClick={applyMcpTemplate} disabled={loading}>
              应用模板
            </Button>
          </div>

          {transport === 'stdio' && (
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

          <Input label="url（sse/http）" value={url} onChange={(e: any) => setUrl(e.target.value)} placeholder="http://localhost:0/mcp" />
          {transport === 'stdio' && (
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
