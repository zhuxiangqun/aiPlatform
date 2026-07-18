import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Database, Box, FileText, BookOpen, Search, RefreshCw, ArrowRight, TrendingUp,
} from 'lucide-react';
import { Card, CardContent } from '../../components/ui';

type HealthData = Record<string, any>;
type PipelineStage = {
  key: string;
  icon: React.FC<any>;
  label: string;
  sublabel: string;
  metrics: { label: string; value: string | number }[];
  link: string;
  linkLabel: string;
};

const PIPELINE: PipelineStage[] = [
  {
    key: 'vault',
    icon: FileText,
    label: '原始资料',
    sublabel: 'DocumentParser → StructuredChunk[]',
    metrics: [],
    link: '/platform/kb?tab=vault',
    linkLabel: '上传文档',
  },
  {
    key: 'ontology',
    icon: Box,
    label: '本体模型',
    sublabel: 'OntologyEngine → 分类/提取/消歧/状态机',
    metrics: [],
    link: '/infra/ontology',
    linkLabel: '管理本体',
  },
  {
    key: 'vector',
    icon: Database,
    label: '向量知识库',
    sublabel: 'Embedding + FTS5 → 语义索引',
    metrics: [],
    link: '/platform/kb?tab=documents',
    linkLabel: '查看索引',
  },
  {
    key: 'wiki',
    icon: BookOpen,
    label: 'LLM Wiki',
    sublabel: 'KnowledgeSynthesizer → 推理链/事实卡',
    metrics: [],
    link: '/platform/kb?tab=wiki',
    linkLabel: '编辑 Wiki',
  },
  {
    key: 'rag',
    icon: Search,
    label: 'RAG 检索',
    sublabel: 'DomainRouter + CRAG + HallucinationTracker',
    metrics: [],
    link: '/platform/kb?tab=eval',
    linkLabel: '查看质量',
  },
  {
    key: 'feedback',
    icon: RefreshCw,
    label: '质量反馈',
    sublabel: 'FeedbackRadar → CandidatePool → ActiveSynthesis',
    metrics: [],
    link: '/platform/kb?tab=quality',
    linkLabel: '查看反馈',
  },
];

const KnowledgeOverview: React.FC = () => {
  const [health, setHealth] = useState<HealthData>({});
  const [risk, setRisk] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.allSettled([
      fetch('/api/core/diagnostics/wiki-quality?limit=1&collection=default').then(r => r.json()),
      fetch('/api/core/diagnostics/rag-quality?hours=24').then(r => r.json()),
      fetch('/api/core/wiki/ontology/domains').then(r => r.json()),
      // Risk indicators
      fetch('/api/core/wiki/ontology/validate').then(r => r.json()).catch(() => ({})),
    ]).then(([wikiR, ragR, domainsR, validateR]) => {
      setHealth({
        wiki: wikiR.status === 'fulfilled' ? wikiR.value : {},
        rag: ragR.status === 'fulfilled' ? ragR.value : {},
        domains: domainsR.status === 'fulfilled' ? domainsR.value : [],
      });
      setRisk({
        validate: validateR.status === 'fulfilled' ? validateR.value : {},
      });
      setLoading(false);
    });
  }, []);

  // Populate metrics from fetched data
  const getMetrics = (key: string) => {
    switch (key) {
      case 'vault':
        return [{ label: '文档', value: '...' }];
      case 'ontology': {
        const domains = health.domains || [];
        const totalClasses = domains.reduce((s: number, d: any) => s + (d.class_count || d.classes?.length || 0), 0);
        return [
          { label: '域', value: Array.isArray(domains) ? domains.length : '...' },
          { label: '类', value: totalClasses || '...' },
        ];
      }
      case 'wiki':
        return [
          { label: '页面', value: health.wiki?.total_pages ?? '...' },
          { label: '健康分', value: health.wiki?.health_score ?? '...' },
        ];
      case 'rag':
        return [
          { label: '忠实度', value: health.rag?.overall?.faithfulness_score ?? '...' },
          { label: '精度', value: health.rag?.overall?.retrieval_precision ?? '...' },
        ];
      case 'feedback':
        return [
          { label: '缺口', value: health.wiki?.low_quality_count ?? '...' },
        ];
      default:
        return [];
    }
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-100">知识管线总览</h1>
          <p className="text-sm text-gray-500 mt-1">
            DocumentParser → OntologyEngine → 向量化+Wiki合成 → RAG检索 → 质量反馈闭环
          </p>
        </div>
      </div>

      {/* ── Pipeline Flow Diagram ── */}
      <div className="grid grid-cols-1 gap-4">
        {PIPELINE.map((stage, idx) => {
          const metrics = getMetrics(stage.key);
          const Icon = stage.icon;
          const isSource = idx === 0;
          const isProcessor = idx === 1;
          const isConsumer = idx >= 2 && idx <= 3;
          const isOutput = idx >= 4;

          return (
            <div key={stage.key}>
              {/* Arrow between stages */}
              {idx > 0 && (
                <div className="flex justify-center py-1">
                  <div className="flex flex-col items-center">
                    <div className="w-px h-4 bg-gray-700" />
                    <ArrowRight className="w-4 h-4 text-gray-600 transform rotate-90" />
                    <div className="w-px h-4 bg-gray-700" />
                  </div>
                </div>
              )}

              <Card className={`
                border-2
                ${isSource ? 'border-green-500/20' : ''}
                ${isProcessor ? 'border-purple-500/20' : ''}
                ${isConsumer ? 'border-blue-500/20' : ''}
                ${isOutput ? 'border-amber-500/20' : ''}
              `}>
                <CardContent className="p-4">
                  <div className="flex items-start gap-4">
                    {/* Icon + label */}
                    <div className={`p-2 rounded-lg shrink-0
                      ${isSource ? 'bg-green-500/10 text-green-400' : ''}
                      ${isProcessor ? 'bg-purple-500/10 text-purple-400' : ''}
                      ${isConsumer ? 'bg-blue-500/10 text-blue-400' : ''}
                      ${isOutput ? 'bg-amber-500/10 text-amber-400' : ''}
                    `}>
                      <Icon className="w-6 h-6" />
                    </div>

                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-gray-600 font-mono">{idx + 1}</span>
                        <span className="text-sm font-semibold text-gray-200">{stage.label}</span>
                        <span className="text-[10px] text-gray-600">{stage.sublabel}</span>
                      </div>

                      {/* Metrics */}
                      {metrics.length > 0 && (
                        <div className="flex gap-4 mt-2">
                          {metrics.map(m => (
                            <div key={m.label} className="text-xs">
                              <span className="text-gray-600">{m.label}: </span>
                              <span className="text-gray-300 font-mono">
                                {loading ? '...' : m.value}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Action button */}
                    <Link
                      to={stage.link}
                      className={`shrink-0 text-xs px-3 py-1.5 rounded border hover:opacity-80 transition-opacity
                        ${isSource ? 'border-green-500/30 text-green-400' : ''}
                        ${isProcessor ? 'border-purple-500/30 text-purple-400' : ''}
                        ${isConsumer ? 'border-blue-500/30 text-blue-400' : ''}
                        ${isOutput ? 'border-amber-500/30 text-amber-400' : ''}
                      `}
                    >
                      {stage.linkLabel}
                    </Link>
                  </div>
                </CardContent>
              </Card>
            </div>
          );
        })}
      </div>

      {/* ── Core Risk Indicators ── */}
      <Card className="border-amber-500/20">
        <CardContent className="p-4">
          <div className="flex items-center gap-2 mb-3">
            <TrendingUp className="w-4 h-4 text-amber-400" />
            <span className="text-sm font-semibold text-gray-200">核心风险指标</span>
            <span className="text-[10px] text-gray-600">（超出阈值 → 告警）</span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
            {[
              { label: '引擎健康', value: risk.validate?.classify_ok != null ? (risk.validate.classify_ok ? '✅' : '⚠️') : '...',
                sub: 'ClassMapper 正常', ok: (v: any) => v === '✅' },
              { label: '未分类文档', value: risk.validate?.unclassified != null ? risk.validate.unclassified : '...',
                sub: '阈值 ≤10', ok: (n: any) => n <= 10 },
              { label: '实体提取失败率', value: risk.validate?.missing_fields != null ? `${risk.validate.missing_fields}%` : '...',
                sub: '阈值 ≤20%', ok: (n: any) => parseFloat(n) <= 20 },
              { label: 'Wiki 健康', value: health.wiki?.health_score ?? '...',
                sub: '阈值 ≥85', ok: (n: any) => n >= 85 },
              { label: 'RAG 忠实度', value: health.rag?.overall?.faithfulness_score ?? '...',
                sub: '阈值 ≥0.7', ok: (n: any) => n >= 0.7 },
              { label: '候选池堆积', value: health.wiki?.low_quality_unreviewed ?? '...',
                sub: '阈值 ≤20', ok: (n: any) => n <= 20 },
            ].map(r => (
              <div key={r.label} className="p-2 rounded bg-dark-bg">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-gray-400 text-xs">{r.label}</span>
                  <span className={`text-xs font-mono font-bold ${loading ? 'text-gray-600' : r.ok(r.value) ? 'text-green-400' : 'text-red-400'}`}>
                    {loading ? '...' : typeof r.value === 'number' ? r.value : r.value}
                  </span>
                </div>
                <div className="text-[10px] text-gray-600">{r.sub}</div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* ── Quick Health Snapshot ── */}
      <Card className="border-primary/20">
        <CardContent className="p-4">
          <div className="flex items-center gap-2 mb-3">
            <TrendingUp className="w-4 h-4 text-primary" />
            <span className="text-sm font-semibold text-gray-200">管线概览</span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            {[
              { label: '域数量', value: Array.isArray(health.domains) ? health.domains.length : '...', ok: (n: any) => n >= 3 },
              { label: '文档数', value: '...', ok: () => false },
              { label: 'Wiki 页面', value: health.wiki?.total_pages ?? '...', ok: () => true },
              { label: 'RAG 会话', value: health.rag?.overall?.total_sessions ?? '...', ok: () => true },
            ].map(h => (
              <div key={h.label} className="p-2 rounded bg-dark-bg text-center">
                <div className="text-gray-500 text-xs mb-1">{h.label}</div>
                <div className="font-bold text-gray-200">
                  {loading ? '...' : typeof h.value === 'number' ? h.value : h.value}
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default KnowledgeOverview;
