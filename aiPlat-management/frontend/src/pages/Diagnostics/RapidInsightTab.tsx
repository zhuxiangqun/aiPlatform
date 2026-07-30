/**
 * RapidInsightTab — 48h 行业快速认知 (FDE ⑨快速认知)
 *
 * Step 1: 投喂材料 → 实体提取 + 跨域对齐
 * Step 2: 三问认知 → Q1行业共识 + Q2路线之争 + Q3穿透试题
 * Step 3: 盲区修复 → 答题 + 定位 + 回补
 */
import React, { useState, useRef, useCallback } from 'react';
import { Card, CardContent, CardHeader, Button, toast } from '../../components/ui';
import { Upload, Brain, ChevronDown, ChevronRight, CheckCircle, XCircle, AlertTriangle, RefreshCw } from 'lucide-react';

const API_BASE = '/api/platform/apps/fde';

interface Q1Report {
  consensus: string;
  top_conclusions: Array<{ name: string; label: string; confidence: number; normalized: number; domain: string }>;
  supporting_entities: string[];
  aligned_domains: string[];
}

interface Q2Report {
  controversies: Array<{
    topic?: string;
    entity?: string;
    domain?: string;
    type?: string;
    positions?: Array<{ side: string; argument: string }>;
    unresolved?: string;
  }>;
}

interface Q3Question {
  id: string;
  text: string;
  involves_entities: string[];
  involves_relations: string[];
  penetration_score: number;
}

interface BlindSpot {
  entity: string;
  located: boolean;
  source_doc?: string;
  source_chunk?: string;
  source_text_preview?: string;
  message?: string;
}

const RapidInsightTab: React.FC = () => {
  const [step, setStep] = useState<'upload' | 'analyze' | 'answer'>('upload');
  const [sessionId, setSessionId] = useState('');
  const [industryName, setIndustryName] = useState('');
  const [uploading, setUploading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [answering, setAnswering] = useState<string>('');

  const [extractResult, setExtractResult] = useState<any>(null);
  const [q1, setQ1] = useState<Q1Report | null>(null);
  const [q2, setQ2] = useState<Q2Report | null>(null);
  const [q3, setQ3] = useState<Q3Question[]>([]);
  const [answers, setAnswers] = useState<Record<string, { correct: boolean; matched: string[]; blindSpots: BlindSpot[] }>>({});
  const [blindSpots, setBlindSpots] = useState<BlindSpot[]>([]);
  const [score, setScore] = useState(0);

  const [q1Expanded, setQ1Expanded] = useState(true);
  const [q2Expanded, setQ2Expanded] = useState(true);
  const [q3Expanded, setQ3Expanded] = useState(true);
  const [blindExpanded, setBlindExpanded] = useState(true);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // ═══════════════════════════════════════════════════════════
  // Step 1: Upload
  // ═══════════════════════════════════════════════════════════
  const handleUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files?.length) return;

    setUploading(true);
    try {
      const formData = new FormData();
      for (let i = 0; i < files.length; i++) {
        formData.append('files', files[i]);
      }

      const name = industryName || '新行业';
      const resp = await fetch(`${API_BASE}/rapid-insight/upload?industry_name=${encodeURIComponent(name)}`, {
        method: 'POST', body: formData,
      });
      const data = await resp.json();
      setSessionId(data.session_id);
      setExtractResult(data);
      toast.success(`✅ 提取完成: ${data.entities_extracted || '?'} 实体, ${data.relations_extracted || '?'} 关系`);
    } catch {
      toast.error('上传失败');
    } finally {
      setUploading(false);
    }
  }, [industryName]);

  // ═══════════════════════════════════════════════════════════
  // Step 2: Analyze (三问)
  // ═══════════════════════════════════════════════════════════
  const handleAnalyze = useCallback(async () => {
    setAnalyzing(true);
    try {
      const resp = await fetch(`${API_BASE}/rapid-insight/analyze`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId }),
      });
      const data = await resp.json();
      setQ1(data.q1);
      setQ2(data.q2);
      setQ3(data.q3?.questions || []);
      setStep('analyze');
      toast.success('三问分析完成');
    } catch {
      toast.error('分析失败');
    } finally {
      setAnalyzing(false);
    }
  }, [sessionId]);

  // ═══════════════════════════════════════════════════════════
  // Step 3: Answer
  // ═══════════════════════════════════════════════════════════
  const handleAnswer = useCallback(async (q: Q3Question) => {
    const ans = answering.trim();
    if (!ans) return;

    setAnswering('');
    try {
      const resp = await fetch(`${API_BASE}/rapid-insight/answer`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, question_id: q.id, answer: ans }),
      });
      const data = await resp.json();
      setAnswers(prev => ({
        ...prev,
        [q.id]: { correct: data.correct, matched: data.matched_entities || [], blindSpots: data.blind_spots || [] },
      }));
      setBlindSpots(prev => [...prev, ...(data.blind_spots || [])]);
      setScore(data.current_score || 0);
      if (data.correct) toast.success('✅ 正确');
      else toast.info('❌ 需加强');
    } catch {
      toast.error('提交失败');
    }
  }, [answering, sessionId]);

  // ═══════════════════════════════════════════════════════════
  // Re-patch
  // ═══════════════════════════════════════════════════════════
  const handleRePatch = useCallback(async () => {
    setAnalyzing(true);
    try {
      const resp = await fetch(`${API_BASE}/rapid-insight/re-patch`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId }),
      });
      const data = await resp.json();
      setQ1(data.q1);
      setQ2(data.q2);
      setQ3(data.q3?.questions || []);
      setAnswers({});
      toast.success(`第 ${data.round} 轮重分析完成`);
    } catch {
      toast.error('重分析失败');
    } finally {
      setAnalyzing(false);
    }
  }, [sessionId]);

  // ═══════════════════════════════════════════════════════════
  // Render
  // ═══════════════════════════════════════════════════════════
  return (
    <div className="space-y-4 p-2">
      {/* ── Step 1: Upload ── */}
      <div className="border border-gray-700/50 rounded-lg p-4">
        <div className="text-sm font-medium text-gray-200 mb-3">Step 1: 投喂材料</div>
        <div className="flex gap-3 items-start">
          <div className="flex-1">
            <input
              type="text"
              placeholder="行业名称（如：储能、FinTech）"
              value={industryName}
              onChange={e => setIndustryName(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 mb-2"
            />
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".pdf,.docx,.md,.txt"
              onChange={handleUpload}
              className="hidden"
            />
            <Button
              variant="secondary"
              icon={<Upload className="w-4 h-4" />}
              loading={uploading}
              onClick={() => fileInputRef.current?.click()}
              disabled={!industryName.trim()}
            >
              上传材料 (PDF/Word/MD)
            </Button>
          </div>
          {extractResult && (
            <div className="bg-gray-800/50 rounded p-3 text-xs space-y-1 min-w-[160px]">
              <div className="text-gray-400">提取结果</div>
              <div className="text-green-400">{extractResult.entities_extracted || 0} 实体</div>
              <div className="text-blue-400">{extractResult.relations_extracted || 0} 关系</div>
              <div className="text-purple-400">对齐 {(extractResult.aligned_domains || []).length} 域</div>
              {extractResult.session_id && (
                <Button
                  variant="ghost" size="sm"
                  icon={<Brain className="w-3 h-3" />}
                  loading={analyzing}
                  onClick={handleAnalyze}
                  className="mt-1 px-2 py-0.5 text-[10px]"
                >
                  开始三问分析
                </Button>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ── Step 2: Three Questions ── */}
      {(q1 || q2 || q3.length > 0) && (
        <div className="space-y-3">
          {/* Q1: Consensus */}
          {q1 && (
            <div className="border border-gray-700/50 rounded">
              <div className="flex items-center justify-between p-3 cursor-pointer" onClick={() => setQ1Expanded(!q1Expanded)}>
                <div className="flex items-center gap-2">
                  {q1Expanded ? <ChevronDown className="w-3 h-3 text-gray-500" /> : <ChevronRight className="w-3 h-3 text-gray-500" />}
                  <span className="text-sm font-medium text-gray-200">Q1: 行业共识</span>
                </div>
              </div>
              {q1Expanded && (
                <div className="px-3 pb-3 border-t border-gray-700/40 space-y-2 pt-2">
                  <p className="text-xs text-gray-400">{q1.consensus}</p>
                  {q1.top_conclusions?.slice(0, 5).map((c, i) => (
                    <div key={i} className="flex items-center justify-between text-xs bg-gray-800/50 rounded px-2 py-1">
                      <span className="text-gray-300">{c.label || c.name}</span>
                      <div className="flex gap-2">
                        <span className="text-gray-500">{c.domain}</span>
                        <span className="text-blue-400">{(c.normalized * 100).toFixed(0)}%</span>
                      </div>
                    </div>
                  ))}
                  {q1.supporting_entities?.length > 0 && (
                    <div className="text-[10px] text-gray-600">
                      支撑实体: {q1.supporting_entities.join(', ')}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Q2: Controversies */}
          {q2 && (
            <div className="border border-gray-700/50 rounded">
              <div className="flex items-center justify-between p-3 cursor-pointer" onClick={() => setQ2Expanded(!q2Expanded)}>
                <div className="flex items-center gap-2">
                  {q2Expanded ? <ChevronDown className="w-3 h-3 text-gray-500" /> : <ChevronRight className="w-3 h-3 text-gray-500" />}
                  <span className="text-sm font-medium text-gray-200">Q2: 路线之争</span>
                </div>
              </div>
              {q2Expanded && q2.controversies?.length > 0 && (
                <div className="px-3 pb-3 border-t border-gray-700/40 space-y-2 pt-2">
                  {q2.controversies.slice(0, 5).map((c, i) => (
                    <div key={i} className="bg-gray-800/50 rounded p-2 text-xs">
                      <div className="text-yellow-400 font-medium mb-1">{c.topic || c.entity || '结构分歧'}</div>
                      {c.positions?.map((p, j) => (
                        <div key={j} className="ml-2 mb-0.5">
                          <span className="text-gray-300">{p.side}</span>
                          <span className="text-gray-500"> — {p.argument}</span>
                        </div>
                      ))}
                      {c.unresolved && <div className="text-gray-600 mt-1">⚠️ {c.unresolved}</div>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Q3: Questions */}
          {q3.length > 0 && (
            <div className="border border-gray-700/50 rounded">
              <div className="flex items-center justify-between p-3 cursor-pointer" onClick={() => setQ3Expanded(!q3Expanded)}>
                <div className="flex items-center gap-2">
                  {q3Expanded ? <ChevronDown className="w-3 h-3 text-gray-500" /> : <ChevronRight className="w-3 h-3 text-gray-500" />}
                  <span className="text-sm font-medium text-gray-200">Q3: 穿透性试题 ({q3.length} 题)</span>
                  <span className="text-[10px] bg-blue-500/20 text-blue-400 px-1 py-0.5 rounded">
                    得分: {(score * 100).toFixed(0)}%
                  </span>
                </div>
              </div>
              {q3Expanded && (
                <div className="px-3 pb-3 border-t border-gray-700/40 space-y-2 pt-2">
                  {q3.map((q, i) => {
                    const a = answers[q.id];
                    return (
                      <div key={i} className="bg-gray-800/50 rounded p-2 text-xs">
                        <div className="flex items-start gap-2 mb-1">
                          {a ? (
                            a.correct ? <CheckCircle className="w-3 h-3 text-green-400 mt-0.5 shrink-0" />
                              : <XCircle className="w-3 h-3 text-red-400 mt-0.5 shrink-0" />
                          ) : (
                            <span className="text-gray-600 w-3 shrink-0">{i + 1}.</span>
                          )}
                          <span className="text-gray-200">{q.text}</span>
                        </div>
                        <div className="flex items-center gap-1 text-[10px] text-gray-500">
                          <span>穿透力: {(q.penetration_score * 100).toFixed(0)}%</span>
                          <span>· 涉及: {q.involves_entities?.join(', ')}</span>
                        </div>
                        {a && (
                          <div className={`mt-1 text-[10px] ${a.correct ? 'text-green-600' : 'text-red-500'}`}>
                            {a.correct ? `✅ 通过 (命中: ${a.matched.join(', ')})` : '❌ 需加强'}
                          </div>
                        )}
                        {!a && (
                          <div className="flex gap-1 mt-1">
                            <input
                              type="text"
                              placeholder="输入你的答案..."
                              className="flex-1 bg-gray-900 border border-gray-700 rounded px-2 py-1 text-xs text-gray-300"
                              onKeyDown={e => {
                                if (e.key === 'Enter') {
                                  setAnswering((e.target as HTMLInputElement).value);
                                  setTimeout(() => handleAnswer(q), 0);
                                }
                              }}
                            />
                            <Button variant="ghost" size="sm" className="text-blue-400 text-[10px] py-0 h-6"
                              onClick={() => handleAnswer(q)}>提交</Button>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── Step 3: Blind Spots ── */}
      {blindSpots.length > 0 && (
        <div className="border border-red-800/30 rounded">
          <div className="flex items-center justify-between p-3 cursor-pointer" onClick={() => setBlindExpanded(!blindExpanded)}>
            <div className="flex items-center gap-2">
              {blindExpanded ? <ChevronDown className="w-3 h-3 text-gray-500" /> : <ChevronRight className="w-3 h-3 text-gray-500" />}
              <span className="text-sm font-medium text-gray-200">Step 3: 盲区修复</span>
              <AlertTriangle className="w-3 h-3 text-yellow-400" />
              <span className="text-[10px] text-yellow-400">{blindSpots.length} 处薄弱点</span>
            </div>
            <Button variant="ghost" size="sm" icon={<RefreshCw className="w-3 h-3" />} loading={analyzing}
              onClick={handleRePatch} className="text-[10px]">回补修正</Button>
          </div>
          {blindExpanded && (
            <div className="px-3 pb-3 border-t border-gray-700/40 space-y-2 pt-2">
              {blindSpots.map((bs, i) => (
                <div key={i} className="bg-red-900/10 border border-red-800/20 rounded p-2 text-xs">
                  <div className="text-red-400 font-medium">{bs.entity}</div>
                  {bs.located ? (
                    <div className="text-gray-400 mt-1">
                      <span className="text-gray-500">📄 {bs.source_doc}</span>
                      {bs.source_chunk && <span className="text-gray-600"> → {bs.source_chunk}</span>}
                      {bs.source_text_preview && (
                        <div className="mt-1 p-1 bg-gray-900/50 rounded text-gray-500 max-h-20 overflow-y-auto">
                          {bs.source_text_preview}
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="text-yellow-600 mt-1">{bs.message || '需从材料补充'}</div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default RapidInsightTab;
