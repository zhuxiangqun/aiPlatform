/**
 * 业务说明书页顶栏：两层能力 + 按现状给出唯一下一步。
 * 避免「结构图有边 / 实例边为 0」混为一谈。
 */
import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

const AUDIT = (domainId: string) =>
  `/api/core/diagnostics/ontology-audit?domain_id=${encodeURIComponent(domainId)}`;
const PENDING = (domainId: string) =>
  `/api/platform/apps/fde/extractions/pending?domain_id=${encodeURIComponent(domainId)}`;
const PROPOSALS = (domainId: string) =>
  `/api/platform/apps/fde/ontology/proposals?domain_id=${encodeURIComponent(domainId)}`;

type GuideMode = 'factory' | 'domains';

type Snapshot = {
  entities: number;
  edges: number;
  orphans: number;
  covered: string;
  pendingExtract: number;
  pendingWrite: number;
};

function loadSnap(domainId: string): Promise<Snapshot> {
  return Promise.all([
    fetch(AUDIT(domainId)).then((r) => r.json()).catch(() => ({})),
    fetch(PENDING(domainId)).then((r) => r.json()).catch(() => ({})),
    fetch(PROPOSALS(domainId)).then((r) => r.json()).catch(() => ({})),
  ]).then(([audit, pend, props]) => {
    const report = audit.report || {};
    const cov = report.relation_coverage || {};
    const proposals = props.proposals || [];
    const pendingWrite = proposals.filter(
      (p: any) => p.status === 'draft' || p.status === 'submitted' || p.status === 'approved',
    ).length;
    return {
      entities: Number(report.total_entities ?? 0),
      edges: Number(report.total_edges ?? 0),
      orphans: (report.orphan_classes || []).length,
      covered:
        cov.total_defined != null
          ? `${cov.covered ?? 0}/${cov.total_defined}`
          : '—',
      pendingExtract: (pend.pending || []).length,
      pendingWrite,
    };
  });
}

/** 只返回一条主行动，避免多建议并列 */
function primaryAction(
  mode: GuideMode,
  domainId: string,
  s: Snapshot,
): { title: string; detail: string; href?: string; anchor?: string } {
  if (s.pendingExtract > 0) {
    return {
      title: `先处理 ${s.pendingExtract} 条待确认抽取`,
      detail: '点「确认」会写入知识图实体/关系；点「忽略」丢弃。不要跳到写入说明书。',
      href: `/knowledge/business?tab=factory&domain=${encodeURIComponent(domainId)}`,
      anchor: mode === 'factory' ? undefined : undefined,
    };
  }
  if (s.pendingWrite > 0) {
    return {
      title: `有 ${s.pendingWrite} 条说明书草稿待同意/写入`,
      detail: '这只改类定义（YAML），不会增加实例边。需要演进说明书时再点「同意→写入」。',
      href: `/knowledge/business?tab=factory&domain=${encodeURIComponent(domainId)}`,
    };
  }
  if (s.entities === 0) {
    return {
      title: '还没有知识图实体',
      detail: '在「从文档生成」上传/粘贴材料 → 开始分析 → 确认。确认才会写入知识图。',
      href: `/knowledge/business?tab=factory&domain=${encodeURIComponent(domainId)}`,
    };
  }
  if (s.edges === 0) {
    return {
      title: '实体有了，但实例边仍是 0',
      detail:
        '结构图上的线是「关系定义」，不算实例边。补边：本页再抽含工单+师傅的文字并确认，或 FDE ⑦ 跑派单。注意：FDE ③ 诊断不依赖实例边，可先回工作台跑诊断。',
      href:
        mode === 'factory'
          ? undefined
          : `/knowledge/business?tab=factory&domain=${encodeURIComponent(domainId)}`,
    };
  }
  if (mode === 'factory') {
    return {
      title: '知识图已有连线，可停',
      detail: '日常不必再写说明书。只有要增删类/关系时才用下方「② 写入说明书」或「手动画类」。',
      href: `/knowledge/business?tab=domains&domain=${encodeURIComponent(domainId)}`,
    };
  }
  return {
    title: '说明书可维护；知识图已有数据',
    detail: '结构图=类关系定义；顶部「实例边」=具体实体连线。继续补知识请回「从文档生成」。',
    href: `/knowledge/business?tab=factory&domain=${encodeURIComponent(domainId)}`,
  };
}

export const BusinessOntologyGuide: React.FC<{
  domainId: string;
  mode: GuideMode;
}> = ({ domainId, mode }) => {
  const [snap, setSnap] = useState<Snapshot | null>(null);

  useEffect(() => {
    let cancelled = false;
    loadSnap(domainId).then((s) => {
      if (!cancelled) setSnap(s);
    });
    const t = window.setInterval(() => {
      loadSnap(domainId).then((s) => {
        if (!cancelled) setSnap(s);
      });
    }, 15000);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, [domainId]);

  const action = snap ? primaryAction(mode, domainId, snap) : null;

  return (
    <div className="rounded-lg border border-sky-800/50 bg-gradient-to-b from-sky-950/40 to-gray-950/40 px-4 py-3 space-y-3">
      <div>
        <div className="text-[12px] font-medium text-sky-100">先分清两件事</div>
        <div className="mt-1.5 grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px]">
          <div className="rounded border border-gray-700/60 bg-gray-900/50 px-2.5 py-2">
            <div className="text-gray-300 font-medium">① 说明书（类 / 关系）</div>
            <div className="text-gray-500 mt-0.5 leading-relaxed">
              「有哪些种类、怎么连」——结构图上的线。改它用：写入说明书 / 手动画类。
            </div>
          </div>
          <div className="rounded border border-emerald-800/40 bg-emerald-950/20 px-2.5 py-2">
            <div className="text-emerald-200/90 font-medium">② 知识图（实体 / 实例边）</div>
            <div className="text-gray-500 mt-0.5 leading-relaxed">
              「具体工单、师傅」——确认抽取 或 FDE 动作才会写。结构图有线 ≠ 这里有边。
            </div>
          </div>
        </div>
      </div>

      {snap && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-gray-400">
          <span>
            实体 <strong className="text-gray-200">{snap.entities}</strong>
          </span>
          <span>
            实例边 <strong className={snap.edges === 0 ? 'text-amber-300' : 'text-gray-200'}>{snap.edges}</strong>
          </span>
          <span>
            关系覆盖 <strong className="text-gray-200">{snap.covered}</strong>
          </span>
          {snap.pendingExtract > 0 && (
            <span className="text-amber-300">待确认抽取 {snap.pendingExtract}</span>
          )}
          {snap.pendingWrite > 0 && (
            <span className="text-amber-300">待写入说明书 {snap.pendingWrite}</span>
          )}
        </div>
      )}

      {action && (
        <div className="flex items-start justify-between gap-3 flex-wrap rounded-md border border-amber-700/40 bg-amber-950/25 px-3 py-2.5">
          <div className="min-w-0 flex-1">
            <div className="text-[10px] text-amber-400/90 uppercase tracking-wide">你现在只需做这一步</div>
            <div className="text-sm text-amber-50 font-medium mt-0.5">{action.title}</div>
            <div className="text-[11px] text-gray-400 mt-1 leading-relaxed">{action.detail}</div>
          </div>
          {action.href && (
            <Link
              to={action.href}
              className="shrink-0 px-3 py-1.5 rounded-md text-xs font-medium bg-amber-600 hover:bg-amber-500 text-white"
            >
              {action.href.includes('tab=domains')
                ? '去手动画类'
                : action.href.includes('tab=factory')
                  ? '去从文档生成'
                  : '去处理'}
            </Link>
          )}
          {!action.href && mode === 'factory' && snap && snap.edges === 0 && snap.entities > 0 && (
            <span className="shrink-0 text-[11px] text-amber-200/80 self-center">↓ 在本页继续粘贴并确认</span>
          )}
        </div>
      )}

      {!snap && <div className="text-[11px] text-gray-500">正在读取当前域进度…</div>}
    </div>
  );
};

export default BusinessOntologyGuide;
