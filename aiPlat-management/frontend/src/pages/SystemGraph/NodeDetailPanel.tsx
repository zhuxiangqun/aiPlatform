import React, { useEffect, useState } from 'react';
import { X, ExternalLink, GitBranch, Layers, AlertTriangle, ArrowRight } from 'lucide-react';

interface Props {
  nodeId: string;
  tab: 'code' | 'capability' | 'wiki' | 'architecture';
  onClose: () => void;
  graphData: any;
}

const NodeDetailPanel: React.FC<Props> = ({ nodeId, tab, onClose, graphData }) => {
  const [detail, setDetail] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!nodeId) return;
    if (tab === 'capability') {
      // Capability graph: use local node data, no API call
      const capNode = graphData?.nodes?.find((n: any) => n.id === nodeId);
      if (capNode) {
        setDetail({
          id: capNode.id,
          name: capNode.name || capNode.id,
          fullName: capNode.fullName || capNode.id,
          category: capNode.category || 'unknown',
          inDegree: capNode.inDegree ?? 0,
          outDegree: capNode.outDegree ?? 0,
          _isCapNode: true,
        });
      }
      setLoading(false);
      return;
    }
    setLoading(true);
    fetch(`/api/core/knowledge-graph/node/${encodeURIComponent(nodeId)}`)
      .then(r => r.json())
      .then(setDetail)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [nodeId, tab, graphData]);

  const nodeData = graphData?.nodes?.find((n: any) => n.id === nodeId);

  return (
    <div className="w-80 shrink-0 border-l border-dark-border bg-dark-card overflow-y-auto">
      <div className="flex items-center justify-between px-3 py-2 border-b border-dark-border sticky top-0 bg-dark-card z-10">
        <span className="text-xs font-medium text-gray-200">节点详情</span>
        <button onClick={onClose} className="p-0.5 rounded text-gray-400 hover:text-gray-200">
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      <div className="p-3 space-y-3 text-xs">
        {loading ? (
          <div className="text-gray-500">加载中...</div>
        ) : detail ? (
          <>
            {/* Header */}
            <div>
              <div className="text-sm font-medium text-gray-200 break-all mb-1">{detail.name}</div>
              <div className="flex flex-wrap gap-1">
                <span className="px-1.5 py-0.5 rounded text-[10px] bg-dark-bg border border-dark-border text-gray-400">
                  {detail.layer}
                </span>
                {detail.ext && (
                  <span className="px-1.5 py-0.5 rounded text-[10px] bg-dark-bg border border-dark-border text-gray-400">
                    {detail.ext}
                  </span>
                )}
                {detail.issueCount > 0 && (
                  <span className="px-1.5 py-0.5 rounded text-[10px] bg-red-900/20 text-red-300 border border-red-500/20">
                    <AlertTriangle className="w-3 h-3 inline mr-0.5" />{detail.issueCount}
                  </span>
                )}
              </div>
            </div>

            {/* Degree stats */}
            <div className="grid grid-cols-2 gap-2">
              <div className="p-2 rounded bg-dark-bg border border-dark-border">
                <div className="text-gray-500 text-[10px]">入度</div>
                <div className="text-gray-200 font-mono">{detail.inDegree ?? '—'}</div>
              </div>
              <div className="p-2 rounded bg-dark-bg border border-dark-border">
                <div className="text-gray-500 text-[10px]">出度</div>
                <div className="text-gray-200 font-mono">{detail.outDegree ?? '—'}</div>
              </div>
            </div>

            {/* Symbols (functions/classes) */}
            {detail.symbols?.length > 0 && (
              <div>
                <div className="flex items-center gap-1 text-gray-500 text-[10px] mb-1">
                  <GitBranch className="w-3 h-3" />符号 ({detail.symbols.length})
                </div>
                <div className="space-y-0.5 max-h-40 overflow-y-auto">
                  {detail.symbols.map((s: any, i: number) => (
                    <div key={i} className="flex items-center justify-between text-[10px] px-1.5 py-0.5 rounded bg-dark-bg/50">
                      <span className={
                        s[1] === 'class' ? 'text-yellow-400' :
                        s[1] === 'async_function' ? 'text-cyan-400' : 'text-blue-400'
                      }>{s[1]}</span>
                      <span className="text-gray-300 flex-1 ml-2 truncate">{s[0]}</span>
                      <span className="text-gray-600">L{s[2]}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Cross-file calls */}
            {detail.crossCalls?.length > 0 && (
              <div>
                <div className="flex items-center gap-1 text-gray-500 text-[10px] mb-1">
                  <ArrowRight className="w-3 h-3" />跨文件调用 ({detail.crossCalls.length})
                </div>
                <div className="space-y-0.5 max-h-32 overflow-y-auto">
                  {detail.crossCalls.map((c: any, i: number) => (
                    <div key={i} className="flex items-center justify-between text-[10px] px-1">
                      <span className="text-gray-400 truncate">{c.name}</span>
                      <span className="text-gray-600">{c.count}×</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Code snippet */}
            {detail.codeSnippet && (
              <div>
                <div className="text-gray-500 text-[10px] mb-1">代码片段</div>
                <pre className="p-2 rounded bg-dark-bg border border-dark-border text-[10px] text-gray-400 max-h-48 overflow-auto font-mono leading-relaxed">
                  {detail.codeSnippet.slice(0, 1500)}
                </pre>
              </div>
            )}

            {/* Dependencies */}
            {detail.dependencies?.length > 0 && (
              <div>
                <div className="flex items-center gap-1 text-gray-500 text-[10px] mb-1">
                  <GitBranch className="w-3 h-3" />依赖谁 ({detail.outDegree})
                </div>
                <div className="space-y-0.5 max-h-32 overflow-y-auto">
                  {detail.dependencies.map((d: any, i: number) => (
                    <div key={i} className="truncate text-gray-400">{d.name}</div>
                  ))}
                </div>
              </div>
            )}

            {/* Dependents */}
            {detail.dependents?.length > 0 && (
              <div>
                <div className="text-gray-500 text-[10px] mb-1">被谁依赖</div>
                <div className="space-y-0.5 max-h-32 overflow-y-auto">
                  {detail.dependents.map((d: any, i: number) => (
                    <div key={i} className="truncate text-gray-400">{d.name}</div>
                  ))}
                </div>
              </div>
            )}

            {/* Blast radius */}
            {detail.blastCount > 0 && (
              <div>
                <div className="flex items-center gap-1 text-gray-500 text-[10px] mb-1">
                  <Layers className="w-3 h-3" />影响范围 ({detail.blastCount} 文件)
                </div>
                <div className="space-y-0.5 max-h-32 overflow-y-auto">
                  {detail.blastRadius?.slice(0, 10).map((b: any, i: number) => (
                    <div key={i} className="truncate text-gray-400">{b.name}</div>
                  ))}
                </div>
              </div>
            )}

            {/* Open in editor */}
            <button
              onClick={() => window.open(`vscode://file/${detail.fullName}`, '_blank')}
              className="flex items-center gap-1 text-[10px] text-blue-400 hover:text-blue-300"
            >
              <ExternalLink className="w-3 h-3" />在编辑器中打开
            </button>
          </>
        ) : (
          <div className="text-gray-500">无数据</div>
        )}
      </div>
    </div>
  );
};

export default NodeDetailPanel;
