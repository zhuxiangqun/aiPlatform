/** §5.4 升格页：草稿做什么 / 权限清单 / 与 SOP 差异 → 确认启用或丢弃。 */
import React, { useEffect, useState } from 'react';
import { Button, Modal, toast } from '../ui';
import { toastGateError, workspaceSkillApi, type Skill } from '../../services';

type Preview = {
  ok?: boolean;
  draft_summary?: string;
  draft_preview?: string;
  draft_sha256_16?: string;
  permissions?: string[];
  sop_excerpt?: string;
  sop_vs_draft?: string[];
  execution_type?: string;
  compat?: { tier?: string; ui_state?: string; schedulable?: boolean };
};

type Props = {
  open: boolean;
  skill: Skill | null;
  onClose: () => void;
  onDone: () => void;
};

const HandlerDraftUpgradeModal: React.FC<Props> = ({ open, skill, onClose, onDone }) => {
  const [loading, setLoading] = useState(false);
  const [acting, setActing] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);

  useEffect(() => {
    if (!open || !skill?.id) {
      setPreview(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const r = await workspaceSkillApi.handlerDraftPreview(skill.id);
        if (!cancelled) setPreview(r as Preview);
      } catch (e: any) {
        if (!cancelled) {
          toastGateError(e, '加载升格预览失败');
          onClose();
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, skill?.id]);

  const enable = async () => {
    if (!skill?.id) return;
    setActing(true);
    try {
      await workspaceSkillApi.enableHandlerDraft(skill.id);
      toast.success(`已启用 handler：${skill.name || skill.id}`);
      onDone();
      onClose();
    } catch (e: any) {
      toastGateError(e, '启用 handler 失败');
    } finally {
      setActing(false);
    }
  };

  const discard = async () => {
    if (!skill?.id) return;
    setActing(true);
    try {
      await workspaceSkillApi.discardHandlerDraft(skill.id);
      toast.success(`已丢弃草稿，继续 prompt：${skill.name || skill.id}`);
      onDone();
      onClose();
    } catch (e: any) {
      toastGateError(e, '丢弃草稿失败');
    } finally {
      setActing(false);
    }
  };

  const title = skill ? `启用 handler 草稿 · ${skill.name || skill.id}` : '启用 handler 草稿';
  const perms = preview?.permissions || [];
  const diffs = preview?.sop_vs_draft || [];

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      width={720}
      footer={
        <div className="flex items-center justify-end gap-2">
          <Button variant="secondary" onClick={onClose} disabled={acting}>
            取消
          </Button>
          <Button variant="secondary" onClick={discard} loading={acting} disabled={loading || !preview?.ok}>
            丢弃草稿（继续 prompt）
          </Button>
          <Button onClick={enable} loading={acting} disabled={loading || !preview?.ok}>
            确认启用
          </Button>
        </div>
      }
    >
      {loading ? (
        <div className="py-10 text-center text-gray-400 text-sm">加载升格预览…</div>
      ) : !preview?.ok ? (
        <div className="py-8 text-center text-amber-400 text-sm">无可用 handler.py.draft</div>
      ) : (
        <div className="space-y-5 text-sm">
          <section>
            <h3 className="text-gray-200 font-medium mb-1">草稿做什么</h3>
            <p className="text-gray-400 leading-relaxed">
              {preview.draft_summary || '（无摘要）'}
            </p>
            {preview.draft_sha256_16 ? (
              <p className="text-xs text-gray-600 mt-1">fingerprint · {preview.draft_sha256_16}</p>
            ) : null}
            {preview.draft_preview ? (
              <pre className="mt-2 max-h-40 overflow-auto rounded border border-dark-border bg-dark-bg p-2 text-xs text-gray-500 whitespace-pre-wrap">
                {preview.draft_preview}
              </pre>
            ) : null}
          </section>

          <section>
            <h3 className="text-gray-200 font-medium mb-1">权限清单</h3>
            {perms.length === 0 ? (
              <p className="text-gray-500">SKILL.md 未声明 permissions</p>
            ) : (
              <ul className="flex flex-wrap gap-1.5">
                {perms.map((p) => (
                  <li
                    key={p}
                    className="px-2 py-0.5 rounded border border-dark-border text-xs text-amber-300/90"
                  >
                    {p}
                  </li>
                ))}
              </ul>
            )}
            {preview.execution_type ? (
              <p className="text-xs text-gray-600 mt-1">当前 execution_type · {preview.execution_type}</p>
            ) : null}
          </section>

          <section>
            <h3 className="text-gray-200 font-medium mb-1">与 SOP 差异</h3>
            <ul className="list-disc pl-5 space-y-1 text-gray-400">
              {diffs.map((d) => (
                <li key={d}>{d}</li>
              ))}
            </ul>
            {preview.sop_excerpt ? (
              <pre className="mt-2 max-h-32 overflow-auto rounded border border-dark-border bg-dark-bg p-2 text-xs text-gray-600 whitespace-pre-wrap">
                {preview.sop_excerpt}
              </pre>
            ) : null}
          </section>

          <p className="text-xs text-gray-600">
            启用会写入 handler.py 并记审计（操作者 / 草稿指纹 / 权限快照）。生产上架仍走市场审核，不挡工作区试用。
          </p>
        </div>
      )}
    </Modal>
  );
};

export default HandlerDraftUpgradeModal;
