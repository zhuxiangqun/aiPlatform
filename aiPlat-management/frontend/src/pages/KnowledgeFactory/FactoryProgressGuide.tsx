import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

const AUDIT = (domainId: string) =>
  `/api/core/diagnostics/ontology-audit?domain_id=${encodeURIComponent(domainId)}`;
const PENDING = (domainId: string) =>
  `/api/platform/apps/fde/extractions/pending?domain_id=${encodeURIComponent(domainId)}`;
const PROPOSALS = (domainId: string) =>
  `/api/platform/apps/fde/ontology/proposals?domain_id=${encodeURIComponent(domainId)}`;

type StepState = 'done' | 'todo' | 'optional';

type GuideModel = {
  entities: number;
  edges: number;
  pendingExtract: number;
  pendingWrite: number;
  primary: { title: string; detail: string; href?: string; anchor?: string };
  steps: { id: string; label: string; state: StepState; note?: string }[];
};

function buildGuide(p: {
  entities: number;
  edges: number;
  pendingExtract: number;
  pendingWrite: number;
  domainId: string;
}): GuideModel {
  const { entities, edges, pendingExtract, pendingWrite, domainId } = p;

  const steps: GuideModel['steps'] = [
    {
      id: 'schema',
      label: '说明书有类/关系',
      state: 'done',
      note: '结构图上的线 = 关系定义（已具备）',
    },
    {
      id: 'extract',
      label: '① 分析文档并点「确认」',
      state: pendingExtract > 0 ? 'todo' : entities > 0 ? 'done' : 'todo',
      note:
        pendingExtract > 0
          ? `${pendingExtract} 条待确认 → 点确认会写入知识图`
          : '确认 = 写知识图实体/关系；不是改 YAML',
    },
    {
      id: 'edges',
      label: '知识图出现实例边',
      state: edges > 0 ? 'done' : entities > 0 ? 'todo' : 'todo',
      note:
        edges > 0
          ? `已有 ${edges} 条实例边`
          : entities > 0
            ? `已有 ${entities} 个实体，但实例边还是 0：再确认一段「工单+师傅」同现的文字，或去 FDE 派单`
            : '先完成上一步确认',
    },
    {
      id: 'yaml',
      label: '② 同意 → 写入说明书（可选）',
      state: pendingWrite > 0 ? 'todo' : 'optional',
      note:
        pendingWrite > 0
          ? `${pendingWrite} 条提案待写入 YAML`
          : '只在要增补类定义时做；不会涨实例边',
    },
  ];

  let primary: GuideModel['primary'];
  if (pendingExtract > 0) {
    primary = {
      title: '现在：把待确认点掉',
      detail: `还有 ${pendingExtract} 条抽取结果未确认。确认后才会进知识图。`,
      anchor: '#factory-extract',
    };
  } else if (edges === 0) {
    primary = {
      title: '现在：补「实例边」',
      detail:
        '粘贴一段同时出现工单与师傅（或现场）的文字 → 开始分析 → 确认。或去 FDE 做一次派单。',
      anchor: '#factory-extract',
      href: '/diagnostics/fde',
    };
  } else if (pendingWrite > 0) {
    primary = {
      title: '现在：写入说明书（可选）',
      detail: `有 ${pendingWrite} 条提案已同意或待同意，只改类定义，不改业务订单。`,
      anchor: '#factory-proposals',
    };
  } else {
    primary = {
      title: '本域知识图已初步可用',
      detail: `实体 ${entities} · 实例边 ${edges}。可去手动画类看结构，或继续用文档加深。`,
      href: `/knowledge/business?tab=domains&domain=${encodeURIComponent(domainId)}`,
    };
  }

  return { entities, edges, pendingExtract, pendingWrite, primary, steps };
}

/** 工厂页顶部：用数据驱动「你该点哪里」 */
export const FactoryProgressGuide: React.FC<{ domainId: string }> = ({ domainId }) => {
  const [guide, setGuide] = useState<GuideModel | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [audit, pending, props] = await Promise.all([
          fetch(AUDIT(domainId)).then((r) => r.json()).catch(() => ({})),
          fetch(PENDING(domainId)).then((r) => r.json()).catch(() => ({})),
          fetch(PROPOSALS(domainId)).then((r) => r.json()).catch(() => ({})),
        ]);
        if (cancelled) return;
        const report = audit.report || {};
        const pendingList = pending.pending || pending.items || [];
        const proposals = props.proposals || [];
        const pendingWrite = proposals.filter((p: any) =>
          ['draft', 'submitted', 'approved'].includes(String(p.status || '')),
        ).length;
        setGuide(
          buildGuide({
            domainId,
            entities: Number(report.total_entities) || 0,
            edges: Number(report.total_edges) || 0,
            pendingExtract: Array.isArray(pendingList) ? pendingList.length : 0,
            pendingWrite,
          }),
        );
      } catch {
        if (!cancelled) setGuide(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [domainId]);

  if (!guide) {
    return (
      <div className="rounded-lg border border-gray-700/50 bg-gray-900/40 px-4 py-3 text-[12px] text-gray-500">
        正在判断你当前该做什么…
      </div>
    );
  }

  const stateIcon = (s: StepState) =>
    s === 'done' ? '✓' : s === 'todo' ? '→' : '·';

  return (
    <div className="rounded-lg border border-sky-700/40 bg-sky-950/25 px-4 py-3 space-y-3">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className="text-[12px] font-medium text-sky-100">你现在该做什么</div>
          <div className="text-sm text-gray-100 mt-1">{guide.primary.title}</div>
          <p className="text-[12px] text-gray-400 mt-1 leading-relaxed max-w-2xl">
            {guide.primary.detail}
          </p>
        </div>
        <div className="flex gap-2 flex-wrap shrink-0">
          {guide.primary.anchor && (
            <a
              href={guide.primary.anchor}
              className="px-3 py-1.5 rounded-md text-xs font-medium bg-sky-600 hover:bg-sky-500 text-white"
            >
              去这一步
            </a>
          )}
          {guide.primary.href && (
            <Link
              to={guide.primary.href}
              className="px-3 py-1.5 rounded-md text-xs font-medium border border-sky-600/50 text-sky-200 hover:bg-sky-900/40"
            >
              {guide.primary.href.includes('fde') ? '去 FDE 派单' : '去手动画类'}
            </Link>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-3 text-[11px] text-gray-500">
        <span>
          知识图：实体 <strong className="text-gray-300">{guide.entities}</strong> · 实例边{' '}
          <strong className={guide.edges > 0 ? 'text-emerald-300' : 'text-amber-300'}>
            {guide.edges}
          </strong>
        </span>
        <span className="text-gray-600">|</span>
        <span>
          待确认 <strong className="text-gray-300">{guide.pendingExtract}</strong> · 待写入说明书{' '}
          <strong className="text-gray-300">{guide.pendingWrite}</strong>
        </span>
      </div>

      <ol className="space-y-1.5 text-[12px]">
        {guide.steps.map((s, i) => (
          <li
            key={s.id}
            className={`flex gap-2 leading-relaxed ${
              s.state === 'todo' ? 'text-gray-200' : s.state === 'done' ? 'text-gray-500' : 'text-gray-600'
            }`}
          >
            <span className="w-4 shrink-0 text-center opacity-80">{stateIcon(s.state)}</span>
            <span>
              <span className="text-gray-500 mr-1">{i + 1}.</span>
              {s.label}
              {s.note && <span className="block text-[11px] text-gray-500 mt-0.5 pl-0">{s.note}</span>}
            </span>
          </li>
        ))}
      </ol>

      <p className="text-[11px] text-gray-600 leading-relaxed border-t border-sky-900/40 pt-2">
        容易混的一点：<strong className="text-gray-500">结构图的线 ≠ 知识图的实例边</strong>
        。结构图只说明「类可以怎么连」；实例边才是「这张工单派给了哪个师傅」。
      </p>
    </div>
  );
};

export default FactoryProgressGuide;
