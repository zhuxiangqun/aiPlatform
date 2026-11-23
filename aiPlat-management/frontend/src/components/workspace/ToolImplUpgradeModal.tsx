/** §5.4 对齐：Tool 实现草稿预览 → 试跑 / 丢弃 / 确认启用（禁止一键直启用）。 */
import React, { useEffect, useState } from 'react';
import { Button, Modal, toast, toastGateError } from '../ui';
import { workspaceToolApi, type ToolInfo } from '../../services';

type Preview = {
  ok?: boolean;
  draft_summary?: string;
  draft_preview?: string;
  draft_sha256_16?: string;
  has_tool_def?: boolean;
  risk_hints?: string[];
  sop_vs_draft?: string[];
  compat?: { tier?: string; ui_state?: string; schedulable?: boolean };
};

type Props = {
  open: boolean;
  tool: ToolInfo | null;
  onClose: () => void;
  onDone: () => void;
};

const ToolImplUpgradeModal: React.FC<Props> = ({ open, tool, onClose, onDone }) => {
  const [loading, setLoading] = useState(false);
  const [acting, setActing] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [dryNote, setDryNote] = useState<string>('');

  useEffect(() => {
    if (!open || !tool?.name) {
      setPreview(null);
      setDryNote('');
      return;
    }
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const r = await workspaceToolApi.implDraftPreview(tool.name);
        if (!cancelled) setPreview(r as Preview);
      } catch (e: any) {
        if (!cancelled) {
          toastGateError(e, '加载实现草稿预览失败');
          onClose();
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, tool?.name]);

  const dryRun = async () => {
    if (!tool?.name) return;
    setActing(true);
    try {
      const r = await workspaceToolApi.implDraftDryRun(tool.name);
      if (r.ok) {
        setDryNote(`试跑通过：compile_ok=${r.compile_ok} · TOOL_DEF=${r.has_tool_def}`);
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
    if (!tool?.name) return;
    setActing(true);
    try {
      await workspaceToolApi.enableImplDraft(tool.name);
      toast.success(`已启用实现：${tool.name}`);
      onDone();
      onClose();
    } catch (e: any) {
      toastGateError(e, '启用实现失败');
    } finally {
      setActing(false);
    }
  };

  const discard = async () => {
    if (!tool?.name) return;
    setActing(true);
    try {
      await workspaceToolApi.discardImplDraft(tool.name);
      toast.success(`已丢弃草稿：${tool.name}`);
      onDone();
      onClose();
    } catch (e: any) {
      toastGateError(e, '丢弃草稿失败');
    } finally {
      setActing(false);
    }
  };

  const title = tool ? `启用实现草稿 · ${tool.name}` : '启用实现草稿';
  const diffs = preview?.sop_vs_draft || [];
  const risks = preview?.risk_hints || [];

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
            丢弃草稿
          </Button>
          <Button onClick={enable} loading={acting} disabled={loading || !preview?.ok}>
            确认启用
          </Button>
        </div>
      }
    >
      {loading ? (
        <div className="py-10 text-center text-gray-400 text-sm">加载实现草稿预览…</div>
      ) : !preview?.ok ? (
        <div className="py-8 text-center text-amber-400 text-sm">无可用 .py.draft</div>
      ) : (
        <div className="space-y-5 text-sm">
          <section>
            <h3 className="text-gray-200 font-medium mb-1">草稿做什么</h3>
            <p className="text-gray-400 leading-relaxed">{preview.draft_summary || '（无摘要）'}</p>
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
            <h3 className="text-gray-200 font-medium mb-1">差异与风险</h3>
            <ul className="list-disc pl-5 space-y-1 text-gray-400">
              {diffs.map((d) => (
                <li key={d}>{d}</li>
              ))}
            </ul>
            {risks.length > 0 ? (
              <p className="text-xs text-amber-400/90 mt-2">潜在调用：{risks.join(', ')}</p>
            ) : null}
            {dryNote ? <p className="text-xs text-teal-400/90 mt-2">{dryNote}</p> : null}
          </section>

          <p className="text-xs text-gray-600">
            启用会写入 .py 并注册到 ToolRegistry。静态试跑仅 compile + TOOL_DEF，不执行任意代码。
            启用后无运行时沙箱，以工作区用户权限与已授权工具集执行（PolicyGate 只管能否调用）。
            生产上架仍走 listing 门禁。详见外源互通方案 §2.1 信任边界。
          </p>
        </div>
      )}
    </Modal>
  );
};

export default ToolImplUpgradeModal;
