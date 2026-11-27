import { useRef, useState, useCallback, useEffect } from 'react';

export type ChatStatus = 'idle' | 'wake' | 'listening' | 'thinking' | 'speaking';
export type Message = { role: 'user' | 'assistant'; text: string; audio?: string };

/** How long the UI waits for an answer once status=thinking (agent + optional TTS). */
const THINKING_TIMEOUT_MS = 120_000;
/** How long to wait for the WebSocket to become OPEN (cold start can exceed 8s). */
const CONNECT_TIMEOUT_MS = 15_000;
const CONSULTANT_SESSION_KEY = 'aiplat.digital_human.session';

/** Probe Core HTTP health via same-origin proxy (or direct) so WS errors are not mislabeled. */
async function probeCoreHealth(): Promise<'ok' | 'down' | 'unknown'> {
  const tryFetch = async (url: string): Promise<'ok' | 'down' | 'unknown'> => {
    const ctrl = new AbortController();
    const timer = window.setTimeout(() => ctrl.abort(), 2500);
    try {
      const r = await fetch(url, { signal: ctrl.signal, cache: 'no-store' });
      return r.ok ? 'ok' : 'down';
    } catch {
      return 'unknown';
    } finally {
      window.clearTimeout(timer);
    }
  };
  const viaProxy = await tryFetch('/api/core/health');
  if (viaProxy !== 'unknown') return viaProxy;
  return tryFetch('http://127.0.0.1:8002/api/core/health');
}

async function explainConnectFailure(serviceLabel: string): Promise<string> {
  const health = await probeCoreHealth();
  if (health === 'ok') {
    return `${serviceLabel} WebSocket 暂不可用（Core HTTP 正常）。请再试一次；若持续失败检查 Vite /ws 代理或刷新页面`;
  }
  if (health === 'down') {
    return `${serviceLabel}未就绪：Core(8002) 健康检查失败。若刚重启，冷启动约需 1–2 分钟后再问`;
  }
  return `${serviceLabel}连接失败（无法确认 Core）。请确认 8002 已监听且前端代理指向 core`;
}

function loadConsultantSessionId(): string {
  try {
    const existing = localStorage.getItem(CONSULTANT_SESSION_KEY) || '';
    if (/^dh_[A-Za-z0-9._-]{6,56}$/.test(existing)) return existing;
  } catch {
    /* ignore */
  }
  const created = `dh_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  try {
    localStorage.setItem(CONSULTANT_SESSION_KEY, created);
  } catch {
    /* ignore */
  }
  return created;
}

/** Same source as apiClient X-AIPLAT-TENANT-ID — scopes 小朱 personal notes (G9). */
function activeTenantId(): string {
  try {
    const tid = (localStorage.getItem('active_tenant_id') || 'default').trim();
    if (/^[A-Za-z0-9._-]{1,64}$/.test(tid)) return tid;
  } catch {
    /* ignore */
  }
  return 'default';
}

export type EvolutionProposalChip = {
  id: string;
  kind?: string;
  title?: string;
  summary?: string;
  status?: string;
};

export type UseVoiceChatOptions = {
  /** When true: never request mic, never play TTS (小朱 text consultant). */
  textOnly?: boolean;
};

export function useVoiceChat(options: UseVoiceChatOptions = {}) {
  const textOnly = Boolean(options.textOnly);
  const [status, setStatus] = useState<ChatStatus>('idle');
  const [messages, setMessages] = useState<Message[]>([]);
  const [error, setError] = useState('');
  const [answer, setAnswer] = useState('');
  const [modelName, setModelName] = useState('');
  const [modelPurpose, setModelPurpose] = useState('');
  const [evolutionPending, setEvolutionPending] = useState(0);
  const [evolutionProposals, setEvolutionProposals] = useState<EvolutionProposalChip[]>([]);

  const wsRef = useRef<WebSocket | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const silenceTimerRef = useRef<any>(null);
  const maxTimerRef = useRef<any>(null);
  const pendingContextRef = useRef<string>('');
  const connectPromiseRef = useRef<Promise<boolean> | null>(null);
  const sessionRef = useRef<string>(loadConsultantSessionId());

  const buildWsUrl = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const configured = (import.meta.env.VITE_WS_URL as string | undefined)?.trim();
    const wsToken = (import.meta.env.VITE_VOICE_WS_TOKEN as string | undefined)?.trim();
    let wsUrl: string;
    if (configured) {
      wsUrl = configured.endsWith('/ws/voice-chat')
        ? configured
        : `${configured.replace(/\/$/, '')}/ws/voice-chat`;
    } else if (window.location.port === '5173' || window.location.host.includes(':5173')) {
      // Prefer same-origin /ws (proxy_server or Vite → core). Fallback: core on
      // 127.0.0.1 — browsers often resolve localhost→::1 while core binds IPv4 only.
      const useDirect =
        String(import.meta.env.VITE_VOICE_WS_DIRECT || '').trim() === '1';
      if (useDirect) {
        wsUrl = `${protocol}//127.0.0.1:8002/ws/voice-chat`;
      } else {
        wsUrl = `${protocol}//${window.location.host}/ws/voice-chat`;
      }
    } else {
      wsUrl = `${protocol}//${window.location.host}/ws/voice-chat`;
    }
    if (wsToken) {
      wsUrl += `${wsUrl.includes('?') ? '&' : '?'}token=${encodeURIComponent(wsToken)}`;
    }
    return wsUrl;
  }, []);

  const serviceLabel = textOnly ? '咨询服务' : '语音服务';

  const attachHandlers = useCallback(
    (ws: WebSocket) => {
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'status') {
            if (data.data === 'thinking' || data.data === 'tts') {
              setStatus('thinking');
              setError('');
            }
            if (data.model) setModelName(String(data.model));
            if (data.purpose) setModelPurpose(String(data.purpose));
          } else if (data.type === 'text') {
            if (data.data) {
              setMessages((prev) => {
                const last = prev[prev.length - 1];
                if (last?.role === 'user' && last.text === data.data) return prev;
                return [...prev, { role: 'user', text: String(data.data) }];
              });
            }
          } else if (data.type === 'answer') {
            setAnswer(data.text);
            if (data.model) setModelName(String(data.model));
            if (data.purpose) setModelPurpose(String(data.purpose));
            setMessages((prev) => [...prev, { role: 'assistant', text: data.text }]);
            if (!textOnly && data.audio && audioRef.current) {
              setStatus('speaking');
              const fmt = (data.format || 'wav').replace(/^audio\//, '');
              audioRef.current.src = `data:audio/${fmt};base64,${data.audio}`;
              audioRef.current.play().catch(() => {});
              audioRef.current.onended = () => setStatus('idle');
            } else {
              setStatus('idle');
            }
          } else if (data.type === 'tts') {
            if (!textOnly && data.audio && audioRef.current) {
              setStatus('speaking');
              const fmt = (data.format || 'wav').replace(/^audio\//, '');
              audioRef.current.src = `data:audio/${fmt};base64,${data.audio}`;
              audioRef.current.play().catch(() => {});
              audioRef.current.onended = () => setStatus('idle');
            }
          } else if (data.type === 'error') {
            setError(data.data);
            setStatus('idle');
          } else if (data.type === 'evolution_list_ack') {
            if (data.ok) {
              setEvolutionPending(Number(data.pending) || 0);
              const rows = Array.isArray(data.proposals) ? data.proposals : [];
              setEvolutionProposals(
                rows.map((p: EvolutionProposalChip) => ({
                  id: String(p?.id || ''),
                  kind: p?.kind,
                  title: p?.title,
                  summary: p?.summary,
                  status: p?.status,
                })).filter((p: EvolutionProposalChip) => !!p.id),
              );
            }
          } else if (data.type === 'evolution_decide_ack') {
            if (typeof data.pending === 'number') {
              setEvolutionPending(data.pending);
            }
            if (data.ok) {
              setEvolutionProposals((prev) =>
                prev.filter((p) => p.id !== String(data.proposal?.id || '')),
              );
            }
          } else if (data.type === 'evolution_scan_ack') {
            if (data.ok) {
              setEvolutionPending(Number(data.pending) || 0);
              const rows = Array.isArray(data.proposals) ? data.proposals : [];
              setEvolutionProposals(
                rows
                  .map((p: EvolutionProposalChip) => ({
                    id: String(p?.id || ''),
                    kind: p?.kind,
                    title: p?.title,
                    summary: p?.summary,
                    status: p?.status,
                  }))
                  .filter((p: EvolutionProposalChip) => !!p.id),
              );
            }
          } else if (data.type === 'feedback_ack' && data.proposal_id) {
            // 反馈产生提案后刷新待批列表
            try {
              ws.send(JSON.stringify({ type: 'evolution_list', session: sessionRef.current }));
            } catch {
              /* ignore */
            }
          }
        } catch {
          /* ignore malformed frames */
        }
      };
      ws.onerror = () => {
        void explainConnectFailure(serviceLabel).then(setError);
        setStatus('idle');
      };
      ws.onclose = () => {
        wsRef.current = null;
        connectPromiseRef.current = null;
      };
    },
    [serviceLabel, textOnly],
  );

  const openSocketOnce = useCallback((): Promise<boolean> => {
    return new Promise<boolean>((resolve) => {
      try {
        const ws = new WebSocket(buildWsUrl());
        wsRef.current = ws;
        attachHandlers(ws);

        const timer = setTimeout(() => {
          if (ws.readyState !== WebSocket.OPEN) {
            try {
              ws.close();
            } catch {
              /* ignore */
            }
            connectPromiseRef.current = null;
            resolve(false);
          }
        }, CONNECT_TIMEOUT_MS);

        ws.onopen = () => {
          clearTimeout(timer);
          if (pendingContextRef.current) {
            try {
              const payload = JSON.parse(pendingContextRef.current);
              ws.send(
                JSON.stringify({
                  type: 'context',
                  data: payload,
                  session: sessionRef.current,
                  tenant_id: activeTenantId(),
                }),
              );
            } catch {
              ws.send(
                JSON.stringify({
                  type: 'context',
                  data: pendingContextRef.current,
                  session: sessionRef.current,
                  tenant_id: activeTenantId(),
                }),
              );
            }
          }
          resolve(true);
        };
      } catch {
        connectPromiseRef.current = null;
        resolve(false);
      }
    });
  }, [attachHandlers, buildWsUrl]);

  const ensureConnected = useCallback((): Promise<boolean> => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return Promise.resolve(true);
    }
    if (connectPromiseRef.current) {
      return connectPromiseRef.current;
    }

    const promise = (async () => {
      let ok = await openSocketOnce();
      if (!ok) {
        // One retry: covers Core restart / brief proxy blip without blaming "未启动".
        await new Promise((r) => setTimeout(r, 600));
        ok = await openSocketOnce();
      }
      if (!ok) {
        setError(await explainConnectFailure(serviceLabel));
      } else {
        setError('');
      }
      connectPromiseRef.current = null;
      return ok;
    })();

    connectPromiseRef.current = promise;
    return promise;
  }, [openSocketOnce, serviceLabel]);

  useEffect(() => {
    return () => wsRef.current?.close();
  }, []);

  useEffect(() => {
    if (status !== 'thinking') return;
    const id = setTimeout(() => {
      setError(
        textOnly
          ? '处理超时，请重试（本页问题可再问一次；本地模型较慢时稍候）'
          : '处理超时，请重试（知识检索较慢时可再问一次）',
      );
      setStatus('idle');
    }, THINKING_TIMEOUT_MS);
    return () => clearTimeout(id);
  }, [status, textOnly]);

  const stopRecording = useCallback(() => {
    recorderRef.current?.stop();
  }, []);

  const startRecording = useCallback(async () => {
    if (textOnly) {
      setError('小朱已关闭语音，请使用文字输入');
      return;
    }
    setError('');
    setAnswer('');
    const ok = await ensureConnected();
    if (!ok) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      recorderRef.current = recorder;
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunksRef.current.push(e.data);
          if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
          silenceTimerRef.current = setTimeout(() => stopRecording(), 1500);
        }
      };

      recorder.onstop = async () => {
        if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
        if (maxTimerRef.current) clearTimeout(maxTimerRef.current);
        if (chunksRef.current.length === 0) {
          setStatus('idle');
          return;
        }
        setStatus('thinking');
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
        const base64 = await blobToBase64(blob);
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ type: 'audio', data: base64 }));
          wsRef.current.send(JSON.stringify({ type: 'end' }));
        } else {
          setError('连接已断开，请重试');
          setStatus('idle');
        }
        stream.getTracks().forEach((t) => t.stop());
      };

      recorder.start();
      setStatus('listening');
      silenceTimerRef.current = setTimeout(() => stopRecording(), 1500);
      maxTimerRef.current = setTimeout(() => stopRecording(), 10000);
    } catch {
      setError('无法使用麦克风，请改用文字输入');
      setStatus('idle');
    }
  }, [ensureConnected, stopRecording, textOnly]);

  const sendText = useCallback(
    async (text: string) => {
      if (!text.trim()) return;
      setError('');
      setAnswer('');
      setMessages((prev) => [...prev, { role: 'user', text }]);
      setStatus('thinking');
      const ok = await ensureConnected();
      if (!ok || wsRef.current?.readyState !== WebSocket.OPEN) {
        setError(await explainConnectFailure(serviceLabel));
        setStatus('idle');
        return;
      }
      wsRef.current.send(
        JSON.stringify({
          type: 'text',
          data: text,
          session: sessionRef.current,
          tenant_id: activeTenantId(),
        }),
      );
    },
    [ensureConnected, serviceLabel],
  );

  const sendContext = useCallback(
    (context: string | { route: string; label?: string; group?: string; groupLabel?: string; purpose?: string; data?: string }) => {
      const payload =
        typeof context === 'string'
          ? { route: context, label: '', group: '', groupLabel: '', data: '' }
          : context;
      pendingContextRef.current = JSON.stringify(payload);
      const session = sessionRef.current;
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(
          JSON.stringify({
            type: 'context',
            data: payload,
            session,
            tenant_id: activeTenantId(),
          }),
        );
      }
    },
    [],
  );

  const sendFeedback = useCallback(
    async (rating: 'good' | 'bad', correction?: string) => {
      const ok = await ensureConnected();
      if (!ok || wsRef.current?.readyState !== WebSocket.OPEN) {
        setError(`${serviceLabel}未连接，无法提交反馈`);
        return false;
      }
      wsRef.current.send(
        JSON.stringify({
          type: 'feedback',
          rating,
          correction: correction || '',
          session: sessionRef.current,
          tenant_id: activeTenantId(),
        }),
      );
      return true;
    },
    [ensureConnected, serviceLabel],
  );

  const refreshEvolutionProposals = useCallback(async () => {
    const ok = await ensureConnected();
    if (!ok || wsRef.current?.readyState !== WebSocket.OPEN) return false;
    wsRef.current.send(
      JSON.stringify({
        type: 'evolution_list',
        session: sessionRef.current,
        tenant_id: activeTenantId(),
      }),
    );
    return true;
  }, [ensureConnected]);

  const decideEvolutionProposal = useCallback(
    async (decision: 'approve' | 'reject', proposalId?: string, index?: number) => {
      const ok = await ensureConnected();
      if (!ok || wsRef.current?.readyState !== WebSocket.OPEN) {
        setError(`${serviceLabel}未连接，无法处理进化提案`);
        return false;
      }
      wsRef.current.send(
        JSON.stringify({
          type: 'evolution_decide',
          decision,
          proposal_id: proposalId || '',
          index: index ?? null,
          session: sessionRef.current,
          tenant_id: activeTenantId(),
        }),
      );
      return true;
    },
    [ensureConnected, serviceLabel],
  );

  const scanDomainEvolution = useCallback(async () => {
    const ok = await ensureConnected();
    if (!ok || wsRef.current?.readyState !== WebSocket.OPEN) {
      setError(`${serviceLabel}未连接，无法扫描领域进化`);
      return false;
    }
    wsRef.current.send(
      JSON.stringify({
        type: 'evolution_scan',
        session: sessionRef.current,
        tenant_id: activeTenantId(),
      }),
    );
    return true;
  }, [ensureConnected, serviceLabel]);

  const wake = useCallback(async () => {
    if (textOnly) {
      setError('小朱已关闭语音，请使用文字输入');
      return;
    }
    const ok = await ensureConnected();
    if (!ok) {
      setError(await explainConnectFailure(serviceLabel));
      return;
    }
    setStatus('wake');
    setTimeout(() => startRecording(), 500);
  }, [ensureConnected, serviceLabel, startRecording, textOnly]);

  const minimize = useCallback(() => setStatus('idle'), []);

  return {
    status,
    messages,
    error,
    answer,
    modelName,
    modelPurpose,
    evolutionPending,
    evolutionProposals,
    wake,
    sendText,
    sendContext,
    sendFeedback,
    refreshEvolutionProposals,
    decideEvolutionProposal,
    scanDomainEvolution,
    minimize,
    audioRef,
    setStatus,
  };
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve((reader.result as string).split(',')[1]);
    reader.readAsDataURL(blob);
  });
}
