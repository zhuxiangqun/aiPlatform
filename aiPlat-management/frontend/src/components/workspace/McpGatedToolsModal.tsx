/** MCP gated：高风险工具个别确认（与升格页同级，非一键全开）。 */
import React, { useEffect, useState } from 'react';
import { Button, Modal, toast, toastGateError } from '../ui';
import { workspaceMcpApi, type McpServer } from '../../services';

type GatedTool = {
  name: string;
  risk_level?: string;
  confirmed?: boolean;
  needs_confirm?: boolean;
  approval_required_effective?: boolean;
};

type GatedStatus = {
  ok?: boolean;
  tier?: string;
  ui_state?: string;
  pending_confirm?: string[];
  confirmed_tools?: string[];
  tools?: GatedTool[];
  note?: string;
};

type Props = {
  open: boolean;
  server: McpServer | null;
  onClose: () => void;
  onDone: () => void;
};

const McpGatedToolsModal: React.FC<Props> = ({ open, server, onClose, onDone }) => {
  const [loading, setLoading] = useState(false);
  const [acting, setActing] = useState<string | null>(null);
  const [status, setStatus] = useState<GatedStatus | null>(null);

  const reload = async () => {
    if (!server?.name) return;
    setLoading(true);
    try {
      const r = await workspaceMcpApi.listGatedTools(server.name);
      setStatus(r as GatedStatus);
    } catch (e: any) {
      toastGateError(e, '加载 gated 工具失败');
      onClose();
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!open || !server?.name) {
      setStatus(null);
      return;
    }
    void reload();
  }, [open, server?.name]);

  const confirm = async (tool: string) => {
    if (!server?.name) return;
    setActing(tool);
    try {
      await workspaceMcpApi.confirmGatedTool(server.name, tool);
      toast.success(`已确认工具：${tool}`);
      await reload();
      onDone();
    } catch (e: any) {
      toastGateError(e, '确认失败');
    } finally {
      setActing(null);
    }
  };

  const revoke = async (tool: string) => {
    if (!server?.name) return;
    setActing(tool);
    try {
      await workspaceMcpApi.revokeGatedTool(server.name, tool);
      toast.success(`已撤销确认：${tool}`);
      await reload();
      onDone();
    } catch (e: any) {
      toastGateError(e, '撤销失败');
    } finally {
      setActing(null);
    }
  };

  const tools = status?.tools || [];

  return (
    <Modal open={open} onClose={onClose} title={`MCP 高风险工具确认：${server?.name || ''}`}>
      <div className="space-y-4 text-sm text-gray-300">
        <p className="text-xs text-gray-500">
          档位 <span className="text-amber-400">{status?.tier || '—'}</span>
          {status?.ui_state ? ` · ${status.ui_state}` : ''}
          。确认后该工具调用不再强制审批；未确认的高风险工具仍需个别确认。
        </p>
        {loading ? (
          <p className="text-gray-500">加载中…</p>
        ) : tools.length === 0 ? (
          <p className="text-gray-500">暂无工具列表。可先发现工具或填写 allowed_tools。</p>
        ) : (
          <ul className="divide-y divide-dark-border border border-dark-border rounded-lg overflow-hidden">
            {tools.map((t) => (
              <li key={t.name} className="flex items-center justify-between gap-3 px-3 py-2 bg-dark-card">
                <div className="min-w-0">
                  <div className="font-mono text-xs text-gray-100 truncate">{t.name}</div>
                  <div className="text-[11px] text-gray-500">
                    risk={t.risk_level || '—'}
                    {t.needs_confirm ? ' · 待确认' : t.confirmed ? ' · 已确认' : ' · 无需确认'}
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {t.needs_confirm ? (
                    <Button
                      size="sm"
                      variant="primary"
                      disabled={!!acting}
                      loading={acting === t.name}
                      onClick={() => confirm(t.name)}
                    >
                      确认
                    </Button>
                  ) : t.confirmed ? (
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={!!acting}
                      loading={acting === t.name}
                      onClick={() => revoke(t.name)}
                    >
                      撤销
                    </Button>
                  ) : (
                    <span className="text-[11px] text-gray-600">无需确认</span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
        {status?.note ? <p className="text-[11px] text-gray-600">{status.note}</p> : null}
        <div className="flex justify-end">
          <Button variant="secondary" onClick={onClose}>关闭</Button>
        </div>
      </div>
    </Modal>
  );
};

export default McpGatedToolsModal;
