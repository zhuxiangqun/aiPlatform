/** Compact Skill row actions: 执行 / 编辑 +「更多」menu (portal). */
import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  Zap,
  Pencil,
  MoreHorizontal,
  Info,
  Layers,
  Clock,
  ShieldCheck,
  Upload,
  Trash2,
  RotateCw,
} from 'lucide-react';
import type { Skill } from '../../services';

type Props = {
  skill: Skill;
  onExecute: (s: Skill) => void;
  onEdit: (s: Skill) => void;
  onDetail: (s: Skill) => void;
  onVersions: (s: Skill) => void;
  onHistory: (s: Skill) => void;
  onSubmitReview: (s: Skill) => void;
  onOpenApproval?: () => void;
  onExport: (s: Skill) => void;
  onDeprecate: (s: Skill) => void;
  onRestore: (s: Skill) => void;
};

const itemCls =
  'w-full text-left px-3 py-2 text-xs hover:bg-dark-hover flex flex-col gap-0.5 transition-colors';

const MENU_W = 208;

export const SkillRowActions: React.FC<Props> = ({
  skill,
  onExecute,
  onEdit,
  onDetail,
  onVersions,
  onHistory,
  onSubmitReview,
  onOpenApproval,
  onExport,
  onDeprecate,
  onRestore,
}) => {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const st = (skill.status || '').toLowerCase();
  const canSubmit = st === 'draft' || st === 'enabled';

  const placeMenu = () => {
    const btn = btnRef.current;
    if (!btn) return;
    const r = btn.getBoundingClientRect();
    const menuH = menuRef.current?.offsetHeight || 280;
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
              onDetail(skill);
              close();
            }}
          >
            <span className="text-gray-200 flex items-center gap-1.5">
              <Info className="w-3.5 h-3.5" /> 详情
            </span>
          </button>
          <button
            type="button"
            className={itemCls}
            onClick={() => {
              onVersions(skill);
              close();
            }}
          >
            <span className="text-gray-200 flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5" /> 版本
            </span>
          </button>
          <button
            type="button"
            className={itemCls}
            onClick={() => {
              onHistory(skill);
              close();
            }}
          >
            <span className="text-gray-200 flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5" /> 历史
            </span>
          </button>
          {canSubmit && (
            <button
              type="button"
              className={itemCls}
              onClick={() => {
                onSubmitReview(skill);
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
            </button>
          )}
          <button
            type="button"
            className={itemCls}
            onClick={() => {
              onExport(skill);
              close();
            }}
          >
            <span className="text-purple-300 flex items-center gap-1.5">
              <Upload className="w-3.5 h-3.5" /> 导出插件
            </span>
          </button>
          {st === 'deprecated' ? (
            <button
              type="button"
              className={itemCls}
              onClick={() => {
                onRestore(skill);
                close();
              }}
            >
              <span className="text-success flex items-center gap-1.5">
                <RotateCw className="w-3.5 h-3.5" /> 恢复
              </span>
            </button>
          ) : (
            <button
              type="button"
              className={itemCls}
              onClick={() => {
                onDeprecate(skill);
                close();
              }}
            >
              <span className="text-red-300 flex items-center gap-1.5">
                <Trash2 className="w-3.5 h-3.5" /> 弃用
              </span>
            </button>
          )}
        </div>,
        document.body
      )
    : null;

  return (
    <div className="flex items-center justify-end gap-1 whitespace-nowrap" ref={rootRef}>
      <button
        type="button"
        onClick={() => onExecute(skill)}
        className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs text-primary hover:bg-primary-light"
        title="执行"
      >
        <Zap className="w-3.5 h-3.5" />
        执行
      </button>
      <button
        type="button"
        onClick={() => onEdit(skill)}
        className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs text-gray-300 hover:bg-dark-hover"
        title="编辑"
      >
        <Pencil className="w-3.5 h-3.5" />
        编辑
      </button>
      <button
        ref={btnRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs text-gray-400 hover:bg-dark-hover hover:text-gray-200"
        aria-expanded={open}
        aria-haspopup="menu"
      >
        <MoreHorizontal className="w-3.5 h-3.5" />
        更多
      </button>
      {menu}
    </div>
  );
};

export default SkillRowActions;
