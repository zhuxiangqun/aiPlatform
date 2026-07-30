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
  const pendingContextRef = useRef<string>('');

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';

    // Production (vite preview): no proxy, connect directly to core on 8002
    const isProdOn5173 = import.meta.env.PROD && window.location.host.includes(':5173');
    const host = isProdOn5173 ? window.location.host.replace(':5173', ':8002') : window.location.host;
    const wsUrl = `${protocol}//${host}/ws/voice-chat`;
    const ws = new WebSocket(wsUrl);

    // 5s connect timeout (only in dev mode with proxy)
    const connectTimeout = !isProdOn5173 ? setTimeout(() => {
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
            audioRef.current.src = `data:audio/mp3;base64,${data.audio}`;
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
      if (status === 'thinking') setStatus('idle');
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
      // Auto-stop after 10s max
      silenceTimerRef.current = setTimeout(() => stopRecording(), 1500);
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

  const sendContext = useCallback((context: string | { route: string; label?: string; group?: string; groupLabel?: string }) => {
    const payload = typeof context === 'string'
      ? { route: context, label: '', group: '', groupLabel: '' }
      : context;
    pendingContextRef.current = JSON.stringify(payload);
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'context', data: payload }));
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
