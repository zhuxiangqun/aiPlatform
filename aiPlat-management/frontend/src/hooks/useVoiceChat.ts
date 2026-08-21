import { useRef, useState, useCallback, useEffect } from 'react';

export type ChatStatus = 'idle' | 'wake' | 'listening' | 'thinking' | 'speaking';
export type Message = { role: 'user' | 'assistant'; text: string; audio?: string };

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
  // P2-3: 每次会话一个稳定 session（多用户/多标签页隔离对话记忆与轨迹）
  const sessionRef = useRef<string>(`dh_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';

    // P2-2 修复: 生产环境 WS 地址可配置。优先 VITE_WS_URL（部署时指向后端），
    // 其次 dev(5173) 时替换端口到 core 8002；否则默认同域 /ws/voice-chat。
    const configured = (import.meta.env.VITE_WS_URL as string | undefined)?.trim();
    const wsToken = (import.meta.env.VITE_VOICE_WS_TOKEN as string | undefined)?.trim();
    let wsUrl: string;
    if (configured) {
      wsUrl = configured.endsWith('/ws/voice-chat') ? configured : `${configured.replace(/\/$/, '')}/ws/voice-chat`;
    } else if (import.meta.env.PROD && window.location.host.includes(':5173')) {
      wsUrl = `${protocol}//${window.location.host.replace(':5173', ':8002')}/ws/voice-chat`;
    } else {
      wsUrl = `${protocol}//${window.location.host}/ws/voice-chat`;
    }
    // P2-1: 后端配置 AIPLAT_VOICE_WS_TOKEN 时，前端经 VITE_VOICE_WS_TOKEN 携带同名令牌
    if (wsToken) {
      wsUrl += `${wsUrl.includes('?') ? '&' : '?'}token=${encodeURIComponent(wsToken)}`;
    }
    const ws = new WebSocket(wsUrl);

    // 5s connect timeout (only in dev mode with proxy)
    const connectTimeout = !import.meta.env.PROD ? setTimeout(() => {
      if (ws.readyState !== WebSocket.OPEN) {
        ws.close();
        setError('语音服务未启动（需要后端 8002 端口运行）');
      }
    }, 5000) : null;

    ws.onopen = () => {
      clearTimeout(connectTimeout);
      if (pendingContextRef.current) {
        ws.send(JSON.stringify({ type: 'context', data: pendingContextRef.current }));
      }
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'text') {
          // Transcription result
        } else if (data.type === 'answer') {
          setStatus('speaking');
          setAnswer(data.text);
          setMessages(prev => [...prev, { role: 'assistant', text: data.text }]);
          if (data.audio && audioRef.current) {
            // P1-3 修复: 按后端返回的 format 设置 MIME（Piper TTS 输出 WAV），
            // 不再硬编码 audio/mp3 导致声明与实际格式不符。
            const fmt = (data.format || 'wav').replace(/^audio\//, '');
            audioRef.current.src = `data:audio/${fmt};base64,${data.audio}`;
            audioRef.current.play().catch(() => {});
            audioRef.current.onended = () => setStatus('idle');
          } else {
            setTimeout(() => setStatus('idle'), 3000);
          }
        } else if (data.type === 'error') {
          setError(data.data);
          setStatus('idle');
        }
      } catch {}
    };
    ws.onerror = () => {
      setError('语音服务未启动（需要后端 8002 端口运行）');
      setStatus('idle');  // P2-3 修复: 不再引用过期的 status 闭包变量
    };
    ws.onclose = () => { wsRef.current = null; };

    wsRef.current = ws;
  }, []);

  useEffect(() => {
    // Lazy connect: only connect when user explicitly interacts with 小朱,
    // not on page load.  This avoids unnecessary WS connections on every page.
    return () => wsRef.current?.close();
  }, []);

  // Timeout: if thinking > 30s, reset to idle
  useEffect(() => {
    if (status !== 'thinking') return;
    const id = setTimeout(() => {
      setError('处理超时，请重试');
      setStatus('idle');
    }, 30000);
    return () => clearTimeout(id);
  }, [status]);

  const startRecording = useCallback(async () => {
    setError('');
    setAnswer('');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      recorderRef.current = recorder;
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunksRef.current.push(e.data);
          // Reset silence timer on audio data
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
        }
        stream.getTracks().forEach(t => t.stop());
      };

      recorder.start();
      setStatus('listening');
      // P2-3 修复: 独立的 10s 最大时长上限（注释声明过但从未实现），
      // 与 1.5s 静默超时分开管理，两者先到先停。
      silenceTimerRef.current = setTimeout(() => stopRecording(), 1500);
      maxTimerRef.current = setTimeout(() => stopRecording(), 10000);
    } catch {
      setError('Microphone access denied');
    }
  }, []);

  const stopRecording = useCallback(() => {
    recorderRef.current?.stop();
  }, []);

  const sendText = useCallback((text: string) => {
    if (!text.trim()) return;
    setMessages(prev => [...prev, { role: 'user', text }]);
    setStatus('thinking');
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'text', data: text }));
    }
  }, []);

  const sendContext = useCallback((context: string | { route: string; label?: string; group?: string; groupLabel?: string; data?: string }) => {
    const payload = typeof context === 'string'
      ? { route: context, label: '', group: '', groupLabel: '', data: '' }
      : context;
    pendingContextRef.current = JSON.stringify(payload);
    const session = sessionRef.current;  // P2-3: 每次连接带稳定 session，隔离多用户对话记忆
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'context', data: payload, session }));
    }
  }, []);

  const wake = useCallback(async () => {
    connect();
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      setError('语音服务未连接，请确认后端已启动 (port 8002)');
      return;
    }
    setStatus('wake');
    setTimeout(() => startRecording(), 500);
  }, [startRecording, connect]);

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
