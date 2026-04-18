import React, { useMemo, useState } from 'react';
import { workspaceMcpApi } from '../../services/coreApi';
import type { McpServer } from '../../services/coreApi';
import { Alert, Button, Input, Modal, Select, Switch, Textarea, toast } from '../ui';

interface AddMcpModalProps {
  open: boolean;
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

const AddMcpModal: React.FC<AddMcpModalProps> = ({ open, onClose, onSuccess }) => {
  const [loading, setLoading] = useState(false);
  const [name, setName] = useState('');
  const [enabled, setEnabled] = useState(false);
  const [transport, setTransport] = useState('sse');
  const [url, setUrl] = useState('');
  const [command, setCommand] = useState('');
  const [argsText, setArgsText] = useState('[]');
  const [allowedToolsText, setAllowedToolsText] = useState('');
  const [authText, setAuthText] = useState('');
  const [metadataText, setMetadataText] = useState('{\n  "description": ""\n}');
  const [launcherPath, setLauncherPath] = useState('/opt/aiplat/mcp/bin/launch');
  const [template, setTemplate] = useState('sse_internal');

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

    // templates: do NOT auto fill allowed_tools (user will manually click tools/list after create)
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

      const allowed_tools = allowedToolsText
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean);

      const payload: McpServer = {
        name: name.trim(),
        enabled,
        transport,
        url: url.trim() || undefined,
        command: command.trim() || undefined,
        args,
        allowed_tools,
        ...(auth ? { auth } : {}),
        ...(metadata ? { metadata } : {}),
      } as any;

      await workspaceMcpApi.upsertServer(payload);
      toast.success('已创建 MCP Server');
      onSuccess();
      onClose();
      setName('');
    } catch (e: any) {
      toast.error('创建失败', String(e?.message || ''));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="新增应用库 MCP Server"
      width={820}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={loading}>
            取消
          </Button>
          <Button variant="primary" onClick={handleSubmit} loading={loading}>
            创建
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Input label="名称" value={name} onChange={(e: any) => setName(e.target.value)} placeholder="例如：integrated_browser" />

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

        <Textarea label="allowed_tools（每行一个）" rows={5} value={allowedToolsText} onChange={(e: any) => setAllowedToolsText(e.target.value)} placeholder="browser_navigate\nbrowser_snapshot" />

        <Textarea label="auth（JSON，可选）" rows={4} value={authText} onChange={(e: any) => setAuthText(e.target.value)} placeholder='{"type":"bearer","token":"..."}' />
        <Textarea label="metadata（JSON，可选）" rows={5} value={metadataText} onChange={(e: any) => setMetadataText(e.target.value)} />

        <div className="text-xs text-gray-500">{hint}</div>
      </div>
    </Modal>
  );
};

export default AddMcpModal;
