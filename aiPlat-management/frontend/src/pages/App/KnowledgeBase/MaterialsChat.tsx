import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Button, Card, CardContent, CardHeader, Textarea, toast } from '../../../components/ui';
import { kbApi, KBConversation } from '../../../services/kbApi';
import { runApi } from '../../../services/coreApi';

const _fmtMs = (ms: any) => {
  const n = Number(ms);
  if (!Number.isFinite(n) || n < 0) return '-';
  const total = Math.floor(n / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (x: number) => String(x).padStart(2, '0');
  return h > 0 ? `${pad(h)}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
};

const _citationLabel = (c: any) => {
  const start = c?.start_ms ?? c?.time_ms;
  const end = c?.end_ms;
  if (start !== undefined && start !== null) {
    return end !== undefined && end !== null ? `${_fmtMs(start)} - ${_fmtMs(end)}` : `${_fmtMs(start)}`;
  }
  return `p${String(c?.page_idx ?? '-')}`;
};

const _modeLabel = (meta: any) => {
  const mode = String(meta?.mode || '').trim();
  const strategy = String(meta?.strategy || '').trim();
  const intent = String(meta?.intent || '').trim();
  const route = String(meta?.retrieval_policy?.route || '').trim();
  const granularity = String(meta?.analysis?.evidence_granularity || '').trim();
  const answerStyle = String(meta?.answer_strategy?.style || '').trim();
  const line1 = [strategy, mode, intent].filter(Boolean).join(' · ');
  const line2 = [route, granularity, answerStyle].filter(Boolean).join(' · ');
  return [line1, line2].filter(Boolean).join('\n');
};

const _chip = (label: string, value: any) => {
  const text = String(value ?? '').trim();
  if (!text) return null;
  return (
    <span className="px-2 py-1 rounded bg-dark-hover text-xs text-gray-300">
      {label}: {text}
    </span>
  );
};

const MaterialsChat: React.FC = () => {
  const { sessionId = '' } = useParams();
  const navigate = useNavigate();
  const [conversation, setConversation] = useState<KBConversation | null>(null);
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [activeRunId, setActiveRunId] = useState('');
  const [runStatus, setRunStatus] = useState('');

  const scopeTitle = useMemo(() => {
    const scope = conversation?.scope;
    if (!scope) return '未设置资料范围';
    return `当前范围：${scope.doc_ids?.length || 0} 份资料`;
  }, [conversation]);

  const loadConversation = async () => {
    if (!sessionId) return;
    setLoading(true);
    try {
      const res = await kbApi.getConversation(sessionId);
      setConversation(res);
    } catch (e: any) {
      toast.error(`加载会话失败：${e?.message || e}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadConversation();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  const sendMessage = async () => {
    const text = String(message || '').trim();
    if (!sessionId || !text) return;
    setSending(true);
    setRunStatus('正在提交...');
    try {
      const res = await kbApi.queryConversation(sessionId, {
        message: text,
        options: {
          citation_required: true,
          max_citations: 8,
          top_k: 8,
          language: 'zh-CN',
        },
      });
      const runId = String(res?.run_id || '');
      setActiveRunId(runId);
      if (runId) {
        setRunStatus('正在等待结果...');
        await runApi.wait(runId, { timeout_ms: 30000, after_seq: 0 }).catch(() => null);
      }
      setMessage('');
      await loadConversation();
      setRunStatus('');
    } catch (e: any) {
      toast.error(`发送失败：${e?.message || e}`);
      setRunStatus('');
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader title={conversation?.title || '资料对话'} extra={<Button variant="secondary" onClick={() => navigate('/app/kb')}>返回知识库</Button>} />
        <CardContent>
          <div className="text-xs text-gray-400 mb-3">
            {scopeTitle}
            {activeRunId ? ` · 当前 run: ${activeRunId}` : ''}
            {runStatus ? ` · ${runStatus}` : ''}
          </div>
          <div className="rounded-lg border border-dark-border bg-dark-bg p-3 text-sm text-gray-300">
            使用方式：围绕当前选中的资料连续追问。回答会尽量附带引用页码或视频时间片段。
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_320px] gap-4">
        <Card>
          <CardHeader title="对话消息" />
          <CardContent>
            <div className="text-xs text-gray-400 mb-3">{loading ? '加载中...' : `共 ${conversation?.messages?.length || 0} 条消息`}</div>
            <div className="space-y-3 max-h-[60vh] overflow-auto">
              {(conversation?.messages || []).map((msg: any, idx: number) => {
                const citations = Array.isArray(msg?.metadata?.citations) ? msg.metadata.citations : [];
                const metaLine = msg.role === 'assistant' ? _modeLabel(msg?.metadata || {}) : '';
                const analysis = msg?.metadata?.analysis || {};
                const retrievalPolicy = msg?.metadata?.retrieval_policy || {};
                const answerStrategy = msg?.metadata?.answer_strategy || {};
                return (
                  <div
                    key={String(msg?.id || idx)}
                    className={`rounded-xl border p-3 ${msg.role === 'assistant' ? 'border-primary/30 bg-primary/5' : 'border-dark-border bg-dark-card'}`}
                  >
                    <div className="text-xs text-gray-400 mb-2">{msg.role === 'assistant' ? 'AI' : '你'}</div>
                    {metaLine && <div className="text-xs text-gray-400 mb-2 whitespace-pre-wrap">{metaLine}</div>}
                    <div className="text-sm text-gray-100 whitespace-pre-wrap break-words">{String(msg.content || '')}</div>
                    {msg.role === 'assistant' && (
                      <div className="mt-3 space-y-2">
                        <div className="text-xs text-gray-400">决策信息</div>
                        <div className="flex flex-wrap gap-2">
                          {_chip('intent', analysis?.intent || msg?.metadata?.intent)}
                          {_chip('粒度', analysis?.evidence_granularity)}
                          {_chip('答案形态', analysis?.answer_shape)}
                          {_chip('route', retrievalPolicy?.route)}
                          {_chip('skill', retrievalPolicy?.skill_name)}
                          {_chip('top_k', retrievalPolicy?.top_k)}
                          {_chip('style', answerStrategy?.style)}
                        </div>
                      </div>
                    )}
                    {citations.length > 0 && (
                      <div className="mt-3 space-y-2">
                        <div className="text-xs text-gray-400">引用</div>
                        <div className="flex flex-wrap gap-2">
                        {citations.map((c: any, i: number) => (
                          <div
                            key={`${msg?.id || idx}_${i}`}
                            className="rounded-lg border border-dark-border bg-dark-hover px-2 py-2 text-xs text-gray-300 min-w-[180px]"
                          >
                            <div className="font-medium text-gray-200 break-all">{String(c?.doc_id || '')}</div>
                            <div className="mt-1">{_citationLabel(c)}</div>
                          </div>
                        ))}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
            <div className="mt-4 space-y-3">
              <Textarea
                label="继续提问"
                rows={4}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="例如：比较这几份资料的共同点；或刚才第二点展开说明。"
              />
              <div className="flex items-center justify-end gap-2">
                <Button variant="secondary" onClick={() => setMessage('')} disabled={sending}>
                  清空
                </Button>
                <Button variant="primary" onClick={sendMessage} loading={sending}>
                  发送
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader title="当前资料范围" />
          <CardContent>
            <div className="text-xs text-gray-400 mb-3">本会话只围绕这些资料进行连续对话</div>
            <div className="space-y-2">
              {(conversation?.scope?.doc_ids || []).map((docId) => (
                <div key={docId} className="rounded-lg border border-dark-border bg-dark-card px-3 py-2 text-sm text-gray-200 break-all">
                  {docId}
                </div>
              ))}
              {(!conversation?.scope?.doc_ids || conversation.scope.doc_ids.length === 0) && (
                <div className="text-sm text-gray-400">当前还没有绑定资料。</div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default MaterialsChat;
