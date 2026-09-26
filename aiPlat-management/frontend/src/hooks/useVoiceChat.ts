import { useRef, useState, useCallback, useEffect } from 'react';

export type ChatStatus = 'idle' | 'wake' | 'listening' | 'thinking' | 'speaking';
export type Message = { role: 'user' | 'assistant'; text: string; audio?: string };

/** How long the UI waits for an answer once status=thinking (agent + TTS). */
const THINKING_TIMEOUT_MS = 120_000;
/** How long to wait for the WebSocket to become OPEN. */
const CONNECT_TIMEOUT_MS = 8_000;

export function useVoiceChat() {
  const [status, setStatus] = useState<ChatStatus>('idle');
  const [messages, setMessages] = useState<Message[]>([]);
  const [error, setError] = useState('');
  const [answer, setAnswer] = useState('');

  const wsRef = useRef<WebSocket | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const silenceTimerRef = useRef<any>(null);
  const maxTimerRef = useRef<any>(null);
  const pendingContextRef = useRef<string>('');
  const connectPromiseRef = useRef<Promise<boolean> | null>(null);
  // P2-3: 每次会话一个稳定 session（多用户/多标签页隔离对话记忆与轨迹）
  const sessionRef = useRef<string>(`dh_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`);

  const buildWsUrl = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const configured = (import.meta.env.VITE_WS_URL as string | undefined)?.trim();
    const wsToken = (import.meta.env.VITE_VOICE_WS_TOKEN as string | undefined)?.trim();
    let wsUrl: string;
    if (configured) {
      wsUrl = configured.endsWith('/ws/voice-chat')
        ? configured
        : `${configured.replace(/\/$/, '')}/ws/voice-chat`;
    } else if (window.location.host.includes(':5173')) {
      // Static proxy on 5173 has no WebSocket upgrade — talk to core directly.
      wsUrl = `${protocol}//${window.location.host.replace(':5173', ':8002')}/ws/voice-chat`;
    } else {
      wsUrl = `${protocol}//${window.location.host}/ws/voice-chat`;
    }
    if (wsToken) {
      wsUrl += `${wsUrl.includes('?') ? '&' : '?'}token=${encodeURIComponent(wsToken)}`;
    }
    return wsUrl;
  }, []);

  const attachHandlers = useCallback((ws: WebSocket) => {
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'status') {
          // Backend heartbeat while agent/TTS runs — keep UI in thinking
          if (data.data === 'thinking' || data.data === 'tts') {
            setStatus('thinking');
            setError('');
          }
        } else if (data.type === 'text') {
          // Transcription result (optional display)
          if (data.data) {
            setMessages((prev) => {
              const last = prev[prev.length - 1];
              if (last?.role === 'user' && last.text === data.data) return prev;
              return [...prev, { role: 'user', text: String(data.data) }];
            });
          }
        } else if (data.type === 'answer') {
          setStatus(data.audio ? 'speaking' : 'thinking');
          setAnswer(data.text);
          setMessages((prev) => [...prev, { role: 'assistant', text: data.text }]);
          if (data.audio && audioRef.current) {
            const fmt = (data.format || 'wav').replace(/^audio\//, '');
            audioRef.current.src = `data:audio/${fmt};base64,${data.audio}`;
            audioRef.current.play().catch(() => {});
            audioRef.current.onended = () => setStatus('idle');
          } else if (!data.audio) {
            // Text arrived first; TTS may follow as type=tts
            setTimeout(() => {
              setStatus((s) => (s === 'thinking' ? 'idle' : s));
            }, 2500);
          } else {
            setTimeout(() => setStatus('idle'), 3000);
          }
        } else if (data.type === 'tts') {
          if (data.audio && audioRef.current) {
            setStatus('speaking');
            const fmt = (data.format || 'wav').replace(/^audio\//, '');
            audioRef.current.src = `data:audio/${fmt};base64,${data.audio}`;
            audioRef.current.play().catch(() => {});
            audioRef.current.onended = () => setStatus('idle');
          }
        } else if (data.type === 'error') {
          setError(data.data);
          setStatus('idle');
        }
      } catch {
        /* ignore malformed frames */
      }
    };
    ws.onerror = () => {
      setError('语音服务未启动（需要后端 8002 端口运行）');
      setStatus('idle');
    };
    ws.onclose = () => {
      wsRef.current = null;
      connectPromiseRef.current = null;
    };
  }, []);

  const ensureConnected = useCallback((): Promise<boolean> => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return Promise.resolve(true);
    }
    if (connectPromiseRef.current) {
      return connectPromiseRef.current;
    }

    const promise = new Promise<boolean>((resolve) => {
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
            setError('语音服务未启动（需要后端 8002 端口运行）');
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
                }),
              );
            } catch {
              ws.send(
                JSON.stringify({
                  type: 'context',
                  data: pendingContextRef.current,
                  session: sessionRef.current,
                }),
              );
            }
          }
          resolve(true);
        };
      } catch {
        setError('无法连接语音服务');
        connectPromiseRef.current = null;
        resolve(false);
      }
    });

    connectPromiseRef.current = promise;
    return promise;
  }, [attachHandlers, buildWsUrl]);

  useEffect(() => {
    return () => wsRef.current?.close();
  }, []);

  // Timeout: if thinking too long, reset (agent+TTS can exceed 30s)
  useEffect(() => {
    if (status !== 'thinking') return;
    const id = setTimeout(() => {
      setError('处理超时，请重试（知识检索较慢时可再问一次）');
      setStatus('idle');
    }, THINKING_TIMEOUT_MS);
    return () => clearTimeout(id);
  }, [status]);

  const stopRecording = useCallback(() => {
    recorderRef.current?.stop();
  }, []);

  const startRecording = useCallback(async () => {
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
  }, [ensureConnected, stopRecording]);

  const sendText = useCallback(
    async (text: string) => {
      if (!text.trim()) return;
      setError('');
      setAnswer('');
      setMessages((prev) => [...prev, { role: 'user', text }]);
      setStatus('thinking');
      const ok = await ensureConnected();
      if (!ok || wsRef.current?.readyState !== WebSocket.OPEN) {
        setError('语音服务未连接，请确认后端已启动 (port 8002)');
        setStatus('idle');
        return;
      }
      wsRef.current.send(JSON.stringify({ type: 'text', data: text }));
    },
    [ensureConnected],
  );

  const sendContext = useCallback(
    (context: string | { route: string; label?: string; group?: string; groupLabel?: string; data?: string }) => {
      const payload =
        typeof context === 'string'
          ? { route: context, label: '', group: '', groupLabel: '', data: '' }
          : context;
      pendingContextRef.current = JSON.stringify(payload);
      const session = sessionRef.current;
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'context', data: payload, session }));
      }
    },
    [],
  );

  const wake = useCallback(async () => {
    const ok = await ensureConnected();
    if (!ok) {
      setError('语音服务未连接，请确认后端已启动 (port 8002)');
      return;
    }
    setStatus('wake');
    setTimeout(() => startRecording(), 500);
  }, [ensureConnected, startRecording]);

  const minimize = useCallback(() => setStatus('idle'), []);

  return { status, messages, error, answer, wake, sendText, sendContext, minimize, audioRef, setStatus };
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve((reader.result as string).split(',')[1]);
    reader.readAsDataURL(blob);
  });
}
