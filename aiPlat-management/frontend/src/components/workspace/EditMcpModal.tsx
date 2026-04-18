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
      return '高风险（L3）：等同于在 core 所在机器上启动本机进程执行。建议仅 dev/staging 使用；prod 默认禁止启用与工具发现。';
    }
    return '中风险（L2）：远程服务型 MCP。建议配置鉴权（auth）并用 allowed_tools 做最小白名单。';
  }, [transport]);

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

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Select label="Transport" value={transport} onChange={(v) => setTransport(v)} options={TRANSPORTS} />
            <div className="flex items-center justify-between gap-3 pt-6">
              <div className="text-sm text-gray-300">enabled</div>
              <Switch checked={enabled} onChange={() => setEnabled(!enabled)} />
            </div>
          </div>

          <Input label="url（sse/http）" value={url} onChange={(e: any) => setUrl(e.target.value)} placeholder="http://localhost:0/mcp" />
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
  );
};

export default EditMcpModal;
