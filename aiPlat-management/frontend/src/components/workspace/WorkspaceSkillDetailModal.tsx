import React, { useEffect, useMemo, useState } from 'react';
import { Copy, Key, Play, Pencil, ShieldCheck, FileText, Layers, RotateCw } from 'lucide-react';
import { Button, Modal, toast } from '../ui';
import { learningApi, workspaceSkillApi, type Skill } from '../../services';
import { toastGateError } from '../ui';
import { GovDetailBadge, StatusBadge, getGovDetailLabel } from '../../utils/statusLabel';

type Props = {
  open: boolean;
  skill: Skill | null;
  onClose: () => void;
  onRefresh: () => void;
  onEdit: (skill: Skill) => void;
  onExecute: (skill: Skill) => void;
  onVersions: (skill: Skill) => void;
};

function copyText(text: string) {
  navigator.clipboard.writeText(text).then(
    () => toast.success('已复制'),
    () => toast.error('复制失败'),
  );
}

function FieldChips({ schema }: { schema?: Record<string, unknown> | null }) {
  const entries = Object.entries(schema || {});
  if (!entries.length) return <span className="text-xs text-gray-500">（未声明）</span>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {entries.map(([k, v]) => {
        const meta = (v && typeof v === 'object' ? v : {}) as Record<string, unknown>;
        const typ = String(meta.type || 'any');
        const req = meta.required === true;
        return (
          <span key={k} className="text-[11px] px-2 py-0.5 rounded border border-dark-border bg-dark-bg text-gray-300">
            <span className="text-gray-100">{k}</span>
            <span className="text-gray-500 ml-1">
              {typ}
              {req ? ' · 必填' : ''}
            </span>
          </span>
        );
      })}
    </div>
  );
}

function ChipList({ items, empty = '（未声明）' }: { items: string[]; empty?: string }) {
  if (!items.length) return <span className="text-xs text-gray-500">{empty}</span>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((t) => (
        <span key={t} className="text-[11px] px-2 py-0.5 rounded bg-dark-hover text-gray-300 border border-dark-border">
          {t}
        </span>
      ))}
    </div>
  );
}

function formatTs(ts?: number | string | null): string {
  if (ts == null || ts === '') return '-';
  const n = typeof ts === 'number' ? ts : Number(ts);
  if (!Number.isFinite(n) || n <= 0) return String(ts);
  const ms = n > 1e12 ? n : n * 1000;
  try {
    return new Date(ms).toLocaleString();
  } catch {
    return String(ts);
  }
}

const GOV_HINT: Record<string, { title: string; body: string; next: string }> = {
  pending: {
    title: '评测 / 冒烟进行中',
    body: '创建后系统会跑自动冒烟与治理检查。通过前「发布」可能仍需审批或等待任务结束。',
    next: '可先点「执行」自测 → 点「刷新状态」看评测是否结束 → 再「发布」或「提交审核」。',
  },
  verified: {
    title: '治理已通过',
    body: '评测/验签状态正常，可按策略发布或上架。',
    next: '需要对外可用时执行「发布」。',
  },
  published: {
    title: '已发布',
    body: '候选版本已发布，可在 Releases 查看发布记录。',
    next: '日常使用可直接「执行」；改内容后需重新评测。',
  },
  failed: {
    title: '治理未通过',
    body: '自动检查失败，请查看 Lint / 评测产物后修正再试。',
    next: '先「编辑」修复 → 再执行或重新提交审核。',
  },
  unsigned: {
    title: '尚未签名',
    body: '未配置/未写入 Ed25519 签名时，部分生产门禁会拦截启用或发布。',
    next: '开发自测可先「执行」；上线前在下方「签名」折叠区完成签名。',
  },
};

function resolveGovKey(skill: Skill | null): string {
  const { label } = getGovDetailLabel(skill || undefined);
  const low = String(label || '').toLowerCase();
  if (low === 'pending' || label === '评测中') return 'pending';
  if (low === 'verified' || label === '已验签' || label === '已通过') return 'verified';
  if (low === 'published' || label === '已发布') return 'published';
  if (low === 'failed' || label === '未通过') return 'failed';
  return 'unsigned';
}

function isResearchKeywords(kw: any): boolean {
  if (!kw || typeof kw !== 'object') return false;
  const actions = new Set((kw.actions || []).map((x: any) => String(x).toLowerCase()));
  const constraints = new Set((kw.constraints || []).map((x: any) => String(x)));
  return (
    (actions.has('search') || actions.has('research')) &&
    (constraints.has('调研') || constraints.has('只读'))
  );
}

const WorkspaceSkillDetailModal: React.FC<Props> = ({
  open,
  skill: skillProp,
  onClose,
  onRefresh,
  onEdit,
  onExecute,
  onVersions,
}) => {
  const [live, setLive] = useState<Skill | null>(skillProp);
  const [loadingLive, setLoadingLive] = useState(false);
  const [fixing, setFixing] = useState(false);
  const [skillMdOpen, setSkillMdOpen] = useState(false);
  const [skillMdLoading, setSkillMdLoading] = useState(false);
  const [skillMd, setSkillMd] = useState<{ path: string; content: string } | null>(null);
  const [signing, setSigning] = useState(false);
  const [signKey, setSignKey] = useState('');
  const [signResult, setSignResult] = useState<string | null>(null);
  const [publishing, setPublishing] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const skill = live || skillProp;

  const refreshLive = async () => {
    if (!skillProp?.id) return;
    setLoadingLive(true);
    try {
      const res = (await workspaceSkillApi.get(String(skillProp.id))) as Skill;
      setLive(res);
      onRefresh();
    } catch (e: any) {
      toast.error('刷新失败', String(e?.message || e));
    } finally {
      setLoadingLive(false);
    }
  };

  useEffect(() => {
    if (!open) return;
    setLive(skillProp);
    setSignResult(null);
    setSignKey('');
    if (skillProp?.id) {
      void refreshLive();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, skillProp?.id]);

  const meta = (skill?.metadata || {}) as Record<string, any>;
  const gov = (meta.governance || {}) as Record<string, any>;
  const ver = (meta.verification || {}) as Record<string, any>;
  const fs = (meta.filesystem || {}) as Record<string, any>;
  const integrity = (meta.integrity || {}) as Record<string, any>;
  const perms: string[] = Array.isArray(meta.permissions) ? meta.permissions.map(String) : [];
  const triggers: string[] = Array.isArray(meta.trigger_conditions)
    ? meta.trigger_conditions.map(String)
    : [];
  const negatives: string[] = Array.isArray(meta.negative_triggers)
    ? meta.negative_triggers.map(String)
    : [];
  const kw = meta.keywords && typeof meta.keywords === 'object' ? meta.keywords : null;
  const isWrite =
    String(meta.skill_kind || '').toLowerCase() === 'executable' ||
    perms.some((p) => /workspace_fs_write|run_command|file_operations/.test(p));
  const misleadingKw = isWrite && isResearchKeywords(kw);
  const handlerWithoutCode = String(meta.execution_type || '').toLowerCase() === 'handler';

  const skillKindRaw = String(meta.skill_kind || '').trim().toLowerCase();
  const execTypeRaw = String(meta.execution_type || '').trim().toLowerCase();
  const skillKind =
    skillKindRaw === 'executable' || skillKindRaw === 'rule'
      ? skillKindRaw
      : isWrite
        ? 'executable'
        : 'rule';
  const execType =
    execTypeRaw === 'handler' || execTypeRaw === 'python_class' || execTypeRaw === 'prompt'
      ? execTypeRaw
      : 'prompt';
  const skillKindLabel = skillKind === 'executable' ? '可执行 (executable)' : '纯规则 (rule)';
  const execTypeLabel =
    execType === 'handler'
      ? 'handler 脚本'
      : execType === 'python_class'
        ? 'python_class'
        : 'prompt / SOP';
  const displayName = String((meta as any).display_name || skill?.name || skill?.id || '');
  const govKey = useMemo(() => resolveGovKey(skill), [skill]);
  const hint = GOV_HINT[govKey] || GOV_HINT.unsigned;

  const openSkillMd = async () => {
    if (!skill?.id) return;
    setSkillMdOpen(true);
    setSkillMdLoading(true);
    setSkillMd(null);
    try {
      const res = await workspaceSkillApi.getSkillMarkdown(String(skill.id));
      setSkillMd({ path: res.path, content: res.content });
    } catch (e: any) {
      toast.error('预览失败', String(e?.message || ''));
    } finally {
      setSkillMdLoading(false);
    }
  };

  const handleFixMetadata = async () => {
    if (!skill?.id) return;
    setFixing(true);
    try {
      const nextMeta: Record<string, unknown> = {
        ...meta,
        skill_kind: skillKind === 'executable' ? 'executable' : meta.skill_kind || 'rule',
        execution_type: handlerWithoutCode ? 'prompt' : execType,
        keywords: isWrite
          ? {
              objects: ['document', 'file', 'output'],
              actions: ['generate', 'write', 'export'],
              constraints: ['离线', '不编造'],
            }
          : kw || {
              objects: ['topic', 'data', 'content'],
              actions: ['analyze'],
              constraints: [],
            },
        negative_triggers: isWrite
          ? ['联网搜图找素材', '编造未提供的事实或数据', '只要文字稿不要文件']
          : negatives.length
            ? negatives
            : ['不相关', '不在讨论范围'],
      };
      await workspaceSkillApi.update(String(skill.id), { metadata: nextMeta });
      toast.success(
        '已修正元数据',
        handlerWithoutCode ? 'execution_type → prompt；已更新 keywords' : '已更新 keywords / 负向触发',
      );
      await refreshLive();
    } catch (e: any) {
      toastGateError(e, '修正失败');
    } finally {
      setFixing(false);
    }
  };

  const handleSign = async () => {
    if (!skill?.id || !signKey.trim()) return;
    setSigning(true);
    try {
      const res: any = await workspaceSkillApi.sign(String(skill.id), { private_key: signKey });
      const sig = String(res?.signature || res?.metadata?.provenance?.signature || '');
      setSignResult(sig || 'ok');
      toast.success('签名成功');
      await refreshLive();
    } catch (e: any) {
      toastGateError(e, '签名失败');
    } finally {
      setSigning(false);
    }
  };

  const handlePublish = async () => {
    const cid = String(gov.candidate_id || '');
    if (!cid) {
      toast.error('暂无候选版本', '请等待自动冒烟生成 candidate 后再发布');
      return;
    }
    setPublishing(true);
    try {
      const r: any = await learningApi.publishCandidate(cid, {
        user_id: 'admin',
        require_approval: true,
        details: `publish workspace skill ${String(skill?.id || '')}`,
      });
      if (r?.status === 'approval_required' && r?.approval_request_id) {
        toast.error(`需要审批：${String(r.approval_request_id)}`);
        try {
          window.open('/core/approvals', '_blank', 'noopener,noreferrer');
        } catch {
          // ignore
        }
        return;
      }
      toast.success('已发布');
      onRefresh();
      onClose();
    } catch (e: any) {
      toastGateError(e, '发布失败');
    } finally {
      setPublishing(false);
    }
  };

  const handleSubmitReview = async () => {
    if (!skill?.id) return;
    setSubmitting(true);
    try {
      await workspaceSkillApi.submitForReview(String(skill.id));
      toast.success('已提交审核');
      await refreshLive();
    } catch (e: any) {
      toastGateError(e, '提交失败');
    } finally {
      setSubmitting(false);
    }
  };

  if (!skill) return null;

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        title={`Skill 详情：${displayName}`}
        width={880}
        footer={
          <div className="flex flex-wrap items-center justify-end gap-2 w-full">
            <Button variant="secondary" onClick={onClose}>
              关闭
            </Button>
            <Button variant="secondary" icon={<Layers className="w-4 h-4" />} onClick={() => onVersions(skill)}>
              版本
            </Button>
            <Button
              variant="secondary"
              icon={<Pencil className="w-4 h-4" />}
              onClick={() => {
                onClose();
                onEdit(skill);
              }}
            >
              编辑
            </Button>
            <Button
              variant="primary"
              icon={<Play className="w-4 h-4" />}
              onClick={() => {
                onClose();
                onExecute(skill);
              }}
            >
              执行
            </Button>
          </div>
        }
      >
        <div className="space-y-4 text-sm text-gray-300 max-h-[75vh] overflow-y-auto pr-1">
          <div className="rounded-xl border border-dark-border bg-dark-bg p-4 space-y-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-base text-gray-100 font-medium">{displayName}</div>
                <div className="mt-1 flex items-center gap-2 text-xs text-gray-500">
                  <code className="bg-dark-hover px-1.5 py-0.5 rounded break-all">{skill.id}</code>
                  <Button variant="ghost" size="sm" icon={<Copy className="w-3.5 h-3.5" />} onClick={() => copyText(skill.id)}>
                    复制 ID
                  </Button>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge status={skill.status} />
                <GovDetailBadge record={skill as any} />
                <span className="text-[11px] px-2 py-0.5 rounded border border-dark-border text-gray-400">
                  {skill.category || '-'}
                </span>
                <span className="text-[11px] px-2 py-0.5 rounded border border-dark-border text-gray-400">
                  {skillKindLabel}
                </span>
                <span className="text-[11px] px-2 py-0.5 rounded border border-dark-border text-gray-400">
                  {execTypeLabel}
                </span>
              </div>
            </div>
            {skill.description && (
              <p className="text-xs text-gray-400 leading-relaxed line-clamp-4">{skill.description}</p>
            )}
          </div>

          {(misleadingKw || handlerWithoutCode) && (
            <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-4 space-y-2">
              <div className="text-sm text-red-200 font-medium">检测到可自动修复的配置问题</div>
              <ul className="text-xs text-gray-400 space-y-1 list-disc pl-4">
                {handlerWithoutCode && (
                  <li>
                    <code>execution_type=handler</code>，但对话创建通常只有 SKILL.md（无 handler.py）。建议改为{' '}
                    <code>prompt</code>，否则执行可能找不到脚本。
                  </li>
                )}
                {misleadingKw && (
                  <li>
                    keywords 仍是「search/research/只读」，与写文件类 PPT Skill 冲突，会误导路由与 Lint。
                  </li>
                )}
              </ul>
              <Button variant="primary" size="sm" loading={fixing} onClick={handleFixMetadata}>
                一键修正元数据
              </Button>
            </div>
          )}

          <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 space-y-2">
            <div className="flex items-center justify-between gap-2">
              <div className="text-sm text-amber-200 font-medium">下一步：{hint.title}</div>
              <Button
                variant="ghost"
                size="sm"
                icon={<RotateCw className="w-3.5 h-3.5" />}
                loading={loadingLive}
                onClick={refreshLive}
              >
                刷新状态
              </Button>
            </div>
            <p className="text-xs text-gray-400 leading-relaxed">{hint.body}</p>
            <p className="text-xs text-gray-300">{hint.next}</p>
            <div className="flex flex-wrap gap-2 pt-1">
              <Button variant="secondary" size="sm" icon={<FileText className="w-3.5 h-3.5" />} onClick={openSkillMd}>
                预览 SKILL.md
              </Button>
              <Button variant="secondary" size="sm" onClick={handleSubmitReview} loading={submitting}>
                提交审核
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={handlePublish}
                loading={publishing}
                disabled={!gov.candidate_id}
              >
                发布到环境
              </Button>
              {gov.job_id && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    try {
                      window.open(
                        `/core/jobs?job_id=${encodeURIComponent(String(gov.job_id))}`,
                        '_blank',
                        'noopener,noreferrer',
                      );
                    } catch {
                      // ignore
                    }
                  }}
                >
                  查看冒烟任务
                </Button>
              )}
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  try {
                    window.open('/core/learning/releases', '_blank', 'noopener,noreferrer');
                  } catch {
                    // ignore
                  }
                }}
              >
                打开 Releases
              </Button>
            </div>
            {(gov.candidate_id || gov.job_id) && (
              <div className="text-[11px] text-gray-500 pt-1 space-y-0.5">
                {gov.candidate_id && (
                  <div>
                    候选版本 <code className="text-gray-400">{String(gov.candidate_id).slice(0, 8)}…</code>
                    <button
                      className="ml-2 text-primary hover:underline"
                      onClick={() => copyText(String(gov.candidate_id))}
                    >
                      复制
                    </button>
                  </div>
                )}
                {gov.job_id && (
                  <div>
                    冒烟任务 <code className="text-gray-400">{String(gov.job_id)}</code>
                  </div>
                )}
                {(gov.updated_at || ver.updated_at) && (
                  <div>更新于 {formatTs(gov.updated_at || ver.updated_at)}</div>
                )}
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="rounded-lg border border-dark-border p-3 space-y-2">
              <div className="text-xs text-gray-500">输入契约</div>
              <FieldChips schema={skill.input_schema as any} />
            </div>
            <div className="rounded-lg border border-dark-border p-3 space-y-2">
              <div className="text-xs text-gray-500">输出契约</div>
              <FieldChips schema={skill.output_schema as any} />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="rounded-lg border border-dark-border p-3 space-y-2">
              <div className="text-xs text-gray-500">权限</div>
              <ChipList items={perms} />
              {(meta?.config?.require_confirmation === true ||
                (skill.config as any)?.require_confirmation === true) && (
                <div className="text-[11px] text-amber-400">已开启 require_confirmation（高风险二次确认）</div>
              )}
            </div>
            <div className="rounded-lg border border-dark-border p-3 space-y-2">
              <div className="text-xs text-gray-500">触发说法</div>
              <ChipList items={triggers} />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="rounded-lg border border-dark-border p-3 space-y-2">
              <div className="text-xs text-gray-500">路由关键词</div>
              {kw ? (
                <div className="text-[11px] text-gray-400 space-y-1">
                  <div>
                    <span className="text-gray-500">对象 </span>
                    {(kw.objects || []).join(' · ') || '-'}
                  </div>
                  <div>
                    <span className="text-gray-500">动作 </span>
                    {(kw.actions || []).join(' · ') || '-'}
                  </div>
                  <div>
                    <span className="text-gray-500">约束 </span>
                    {(kw.constraints || []).join(' · ') || '-'}
                  </div>
                </div>
              ) : (
                <span className="text-xs text-gray-500">（未声明）</span>
              )}
            </div>
            <div className="rounded-lg border border-dark-border p-3 space-y-2">
              <div className="text-xs text-gray-500">负向触发（减少误命中）</div>
              <ChipList items={negatives} />
            </div>
          </div>

          <div className="rounded-lg border border-dark-border p-3 space-y-2">
            <div className="text-xs text-gray-500">文件位置</div>
            <div className="flex items-start justify-between gap-2">
              <code className="text-[11px] bg-dark-hover px-1.5 py-0.5 rounded break-all text-gray-300">
                {String(fs.skill_md || meta?.provenance?.skill_dir || '-')}
              </code>
              <div className="flex gap-1 shrink-0">
                {fs.skill_md && (
                  <Button
                    variant="ghost"
                    size="sm"
                    icon={<Copy className="w-3.5 h-3.5" />}
                    onClick={() => copyText(String(fs.skill_md))}
                  >
                    复制路径
                  </Button>
                )}
                <Button variant="secondary" size="sm" onClick={openSkillMd}>
                  预览
                </Button>
              </div>
            </div>
            {integrity?.bundle_sha256 && (
              <div className="text-[11px] text-gray-500">
                完整性 {String(integrity.file_count || 1)} 个文件 · {String(integrity.total_bytes || 0)} bytes · sha256{' '}
                <code>{String(integrity.bundle_sha256).slice(0, 12)}…</code>
              </div>
            )}
          </div>

          <details className="rounded-lg border border-dark-border p-3">
            <summary className="cursor-pointer text-xs text-gray-400 hover:text-gray-200 select-none">
              高级：签名（上线门禁可选）
            </summary>
            <div className="mt-3 space-y-2">
              <p className="text-[11px] text-gray-500">
                生产环境可能要求 Ed25519 签名。开发自测可不签；发布前建议签名。私钥仅用于本次签名请求。
              </p>
              {signResult ? (
                <div className="flex items-center gap-2 text-success text-xs">
                  <ShieldCheck size={14} />
                  <span>已签名 · {signResult.slice(0, 16)}...</span>
                  <Button variant="ghost" size="sm" onClick={() => setSignResult(null)}>
                    重新签名
                  </Button>
                </div>
              ) : (
                <div className="flex items-start gap-2">
                  <textarea
                    className="flex-1 h-20 px-3 py-2 bg-dark-hover border border-dark-border rounded-lg text-xs text-gray-200 placeholder-gray-500 font-mono focus:outline-none focus:border-primary resize-none"
                    placeholder="粘贴 Ed25519 私钥 PEM（-----BEGIN PRIVATE KEY-----...）"
                    value={signKey}
                    onChange={(e) => setSignKey(e.target.value)}
                  />
                  <div className="flex flex-col gap-1">
                    <Button
                      variant="primary"
                      size="sm"
                      icon={<Key size={14} />}
                      onClick={handleSign}
                      loading={signing}
                      disabled={!signKey.trim() || signing}
                    >
                      签名
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        try {
                          window.open('/onboarding?step=sign_keys', '_blank', 'noopener,noreferrer');
                        } catch {
                          // ignore
                        }
                      }}
                    >
                      生成密钥
                    </Button>
                  </div>
                </div>
              )}
            </div>
          </details>

          <details className="rounded-lg border border-dark-border p-3">
            <summary className="cursor-pointer text-xs text-gray-400 hover:text-gray-200 select-none">
              高级：原始 metadata / governance JSON
            </summary>
            <pre className="mt-2 text-[11px] bg-dark-hover rounded p-2 overflow-auto max-h-56 text-gray-400">
              {JSON.stringify(
                {
                  governance: gov,
                  verification: ver,
                  provenance: meta.provenance,
                  integrity,
                  filesystem: fs,
                  keywords: kw,
                  negative_triggers: negatives,
                },
                null,
                2,
              )}
            </pre>
          </details>
        </div>
      </Modal>

      <Modal
        open={skillMdOpen}
        onClose={() => {
          setSkillMdOpen(false);
          setSkillMd(null);
        }}
        title={`SKILL.md 预览：${skill.id}`}
        width={980}
        footer={
          <Button
            onClick={() => {
              setSkillMdOpen(false);
              setSkillMd(null);
            }}
          >
            关闭
          </Button>
        }
      >
        <div className="space-y-3 text-sm text-gray-300">
          <div className="text-xs text-gray-500">path</div>
          <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded break-all">{skillMd?.path || '-'}</code>
          <pre className="text-xs bg-dark-hover rounded p-3 overflow-auto max-h-[520px] whitespace-pre-wrap">
            {skillMdLoading ? '加载中...' : skillMd?.content || ''}
          </pre>
        </div>
      </Modal>
    </>
  );
};

export default WorkspaceSkillDetailModal;
