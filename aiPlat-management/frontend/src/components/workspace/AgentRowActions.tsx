/** Compact row actions: 3 primary + labeled「更多」menu (portal, avoids table overflow clip). */
import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  MessageSquare,
  Zap,
  Pencil,
  MoreHorizontal,
  PlayCircle,
  PauseCircle,
  Info,
  Layers,
  Clock,
  ShieldCheck,
  Upload,
  Trash2,
  RotateCw,
} from 'lucide-react';
import type { Agent } from '../../services';

type Props = {
  agent: Agent;
  onChat: (a: Agent) => void;
  onExecute: (a: Agent) => void;
  onEdit: (a: Agent) => void;
  onDetail: (a: Agent) => void;
  onStart: (a: Agent) => void;
  onStop: (a: Agent) => void;
  onVersions: (a: Agent) => void;
  onHistory: (a: Agent) => void;
  onSubmitReview: (a: Agent) => void;
  onOpenApproval?: () => void;
  onExport: (a: Agent) => void;
  onDelete: (a: Agent) => void;
  onRestore: (a: Agent) => void;
};

const itemCls =
  'w-full text-left px-3 py-2 text-xs hover:bg-dark-hover flex flex-col gap-0.5 transition-colors';

const MENU_W = 208;

export const AgentRowActions: React.FC<Props> = ({
  agent,
  onChat,
  onExecute,
  onEdit,
  onDetail,
  onStart,
  onStop,
  onVersions,
  onHistory,
  onSubmitReview,
  onOpenApproval,
  onExport,
  onDelete,
  onRestore,
}) => {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const isRunning = (agent.runtime_state || '') === 'running';
  const isProtected = Boolean((agent as any)?.metadata?.protected === true || (agent as any)?.protected === true);
  const st = (agent.status || '').toLowerCase();

  const placeMenu = () => {
    const btn = btnRef.current;
    if (!btn) return;
    const r = btn.getBoundingClientRect();
    const menuH = menuRef.current?.offsetHeight || 320;
    const spaceBelow = window.innerHeight - r.bottom;
    const openUp = spaceBelow < menuH + 8 && r.top > spaceBelow;
    const top = openUp ? Math.max(8, r.top - menuH - 4) : Math.min(window.innerHeight - menuH - 8, r.bottom + 4);
    const left = Math.min(window.innerWidth - MENU_W - 8, Math.max(8, r.right - MENU_W));
    setPos({ top, left });
  };

  useLayoutEffect(() => {
    if (!open) {
      setPos(null);
      return;
    }
    placeMenu();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      const t = e.target as Node;
      if (rootRef.current?.contains(t)) return;
      if (menuRef.current?.contains(t)) return;
      setOpen(false);
    };
    const onReposition = () => placeMenu();
    document.addEventListener('mousedown', onDoc);
    window.addEventListener('scroll', onReposition, true);
    window.addEventListener('resize', onReposition);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      window.removeEventListener('scroll', onReposition, true);
      window.removeEventListener('resize', onReposition);
    };
  }, [open]);

  const close = () => setOpen(false);

  const menu = open && pos
    ? createPortal(
        <div
          ref={menuRef}
          className="fixed z-[9999] w-52 rounded-lg border border-dark-border bg-dark-card shadow-xl py-1"
          style={{ top: pos.top, left: pos.left }}
          role="menu"
        >
          <button
            type="button"
            className={itemCls}
            onClick={() => {
              onDetail(agent);
              close();
            }}
          >
            <span className="text-gray-200 flex items-center gap-1.5">
              <Info className="w-3.5 h-3.5" /> 详情
            </span>
            <span className="text-gray-500 pl-5">查看绑定、SOP、签名</span>
          </button>
          <button
            type="button"
            className={itemCls}
            onClick={() => {
              isRunning ? onStop(agent) : onStart(agent);
              close();
            }}
          >
            <span className="text-gray-200 flex items-center gap-1.5">
              {isRunning ? <PauseCircle className="w-3.5 h-3.5 text-warning" /> : <PlayCircle className="w-3.5 h-3.5 text-success" />}
              {isRunning ? '停止运行' : '启动运行'}
            </span>
            <span className="text-gray-500 pl-5">后台 runtime 启停</span>
          </button>
          <button
            type="button"
            className={itemCls}
            onClick={() => {
              onVersions(agent);
              close();
            }}
          >
            <span className="text-gray-200 flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5" /> 版本
            </span>
            <span className="text-gray-500 pl-5">快照与回滚</span>
          </button>
          <button
            type="button"
            className={itemCls}
            onClick={() => {
              onHistory(agent);
              close();
            }}
          >
            <span className="text-gray-200 flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5" /> 历史
            </span>
            <span className="text-gray-500 pl-5">执行记录</span>
          </button>
          {(st === 'draft' || st === 'enabled') && (
            <button
              type="button"
              className={itemCls}
              onClick={() => {
                onSubmitReview(agent);
                close();
              }}
            >
              <span className="text-amber-300 flex items-center gap-1.5">
                <ShieldCheck className="w-3.5 h-3.5" /> 提交审批
              </span>
              <span className="text-gray-500 pl-5">draft → 待审核</span>
            </button>
          )}
          {st === 'ready' && onOpenApproval && (
            <button
              type="button"
              className={itemCls}
              onClick={() => {
                onOpenApproval();
                close();
              }}
            >
              <span className="text-amber-300 flex items-center gap-1.5">
                <ShieldCheck className="w-3.5 h-3.5" /> 去资产审批
              </span>
              <span className="text-gray-500 pl-5">管理员在审批页点「通过」</span>
            </button>
          )}
          <button
            type="button"
            className={itemCls}
            onClick={() => {
              onExport(agent);
              close();
            }}
          >
            <span className="text-purple-300 flex items-center gap-1.5">
              <Upload className="w-3.5 h-3.5" /> 导出插件
            </span>
            <span className="text-gray-500 pl-5">打包分享</span>
          </button>
          {st === 'deprecated' ? (
            <>
              <button
                type="button"
                className={itemCls}
                onClick={() => {
                  onRestore(agent);
                  close();
                }}
              >
                <span className="text-success flex items-center gap-1.5">
                  <RotateCw className="w-3.5 h-3.5" /> 恢复
                </span>
                <span className="text-gray-500 pl-5">从废弃恢复为待审核</span>
              </button>
              {!isProtected && (
                <button
                  type="button"
                  className={itemCls}
                  onClick={() => {
                    onDelete(agent);
                    close();
                  }}
                >
                  <span className="text-red-300 flex items-center gap-1.5">
                    <Trash2 className="w-3.5 h-3.5" /> 彻底删除
                  </span>
                  <span className="text-gray-500 pl-5">从磁盘移除，不可恢复</span>
                </button>
              )}
            </>
          ) : (
            !isProtected && (
              <button
                type="button"
                className={itemCls}
                onClick={() => {
                  onDelete(agent);
                  close();
                }}
              >
                <span className="text-red-300 flex items-center gap-1.5">
                  <Trash2 className="w-3.5 h-3.5" /> 删除
                </span>
                <span className="text-gray-500 pl-5">废弃或彻底删除</span>
              </button>
            )
          )}
        </div>,
        document.body
      )
    : null;

  return (
    <div className="flex items-center justify-end gap-1 whitespace-nowrap" ref={rootRef}>
      <button
        type="button"
        onClick={() => onChat(agent)}
        className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs text-blue-300 hover:bg-blue-500/10"
        title="与该数字员工对话试跑"
      >
        <MessageSquare className="w-3.5 h-3.5" />
        对话
      </button>
      <button
        type="button"
        onClick={() => onExecute(agent)}
        className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs text-primary hover:bg-primary-light"
        title="单次任务执行（非持续对话）"
      >
        <Zap className="w-3.5 h-3.5" />
        执行
      </button>
      <button
        type="button"
        onClick={() => onEdit(agent)}
        className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs text-gray-300 hover:bg-dark-hover"
        title="改绑定、SOP、权限等"
      >
        <Pencil className="w-3.5 h-3.5" />
        编辑
      </button>

      <button
        ref={btnRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-0.5 px-2 py-1 rounded-md text-xs text-gray-400 hover:bg-dark-hover"
        title="更多操作"
        aria-expanded={open}
      >
        <MoreHorizontal className="w-3.5 h-3.5" />
        更多
      </button>
      {menu}
    </div>
  );
};

export default AgentRowActions;
