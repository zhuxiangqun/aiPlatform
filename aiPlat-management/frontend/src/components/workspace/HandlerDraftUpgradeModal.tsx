/** §5.4 升格页：草稿做什么 / 权限（可改）/ SOP 差异 / 可选试跑 → 确认启用或丢弃。 */
import React, { useEffect, useState } from 'react';
import { Button, Input, Modal, toast, toastGateError } from '../ui';
import { workspaceSkillApi, type Skill } from '../../services';

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
  const [permText, setPermText] = useState('');
  const [dryNote, setDryNote] = useState('');

  useEffect(() => {
    if (!open || !skill?.id) {
      setPreview(null);
      setPermText('');
      setDryNote('');
      return;
    }
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const r = await workspaceSkillApi.handlerDraftPreview(skill.id);
        if (!cancelled) {
          setPreview(r as Preview);
          setPermText(((r as Preview).permissions || []).join(', '));
        }
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

  const parsePerms = (): string[] =>
    permText
      .split(/[,，\n]/)
      .map((s) => s.trim())
      .filter(Boolean);

  const dryRun = async () => {
    if (!skill?.id) return;
    setActing(true);
    try {
      const r = await workspaceSkillApi.handlerDraftDryRun(skill.id);
      if (r.ok) {
        setDryNote(`试跑通过：compile_ok=${r.compile_ok} · execute=${r.has_execute}`);
        toast.success('静态试跑通过（未执行代码）');
      } else {
        setDryNote(`试跑未通过：${r.error || (r.errors || []).join('; ') || 'failed'}`);
        toast.error('静态试跑未通过');
      }
    } catch (e: any) {
      toastGateError(e, '试跑失败');
    } finally {
      setActing(false);
    }
  };

  const enable = async () => {
    if (!skill?.id) return;
    setActing(true);
    try {
      await workspaceSkillApi.enableHandlerDraft(skill.id, { permissions: parsePerms() });
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
          <Button variant="secondary" onClick={dryRun} loading={acting} disabled={loading || !preview?.ok}>
            静态试跑
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
            <h3 className="text-gray-200 font-medium mb-1">权限清单（可改）</h3>
            <Input
              value={permText}
              onChange={(e) => setPermText(e.target.value)}
              placeholder="逗号分隔，如 filesystem:read, network"
            />
            <p className="text-xs text-gray-600 mt-1">启用时写入 SKILL.md frontmatter permissions</p>
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
            {dryNote ? <p className="text-xs text-teal-400/90 mt-2">{dryNote}</p> : null}
          </section>

          <p className="text-xs text-gray-600">
            静态试跑仅 compile + execute 签名，不执行任意代码。启用会写入 handler.py 并记审计。生产上架仍走市场审核。
          </p>
        </div>
      )}
    </Modal>
  );
};

export default HandlerDraftUpgradeModal;
