import { useRef, useState, useCallback, useEffect } from 'react';

interface UseWakeWordOptions {
  keyword?: string;
  onWake: () => void;
  enabled?: boolean;
}

export function useWakeWord({ keyword = '小朱', onWake, enabled = false }: UseWakeWordOptions) {
  const [isListening, setIsListening] = useState(false);
  const [lastResult, setLastResult] = useState('');

  const recognitionRef = useRef<any>(null);
  const cooldownRef = useRef(false);
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;

  // ── Speech Recognition (wake word detection) ──
  const startRecognition = useCallback(() => {
    if (cooldownRef.current) return;
    if (!enabledRef.current) return;

    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) return;

    const rec = new SpeechRecognition();
    rec.lang = 'zh-CN';
    rec.continuous = true;
    rec.interimResults = true;
    rec.maxAlternatives = 1;

    rec.onresult = (event: any) => {
      let transcript = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        transcript += event.results[i][0].transcript;
      }
      setLastResult(transcript.trim());
      if (transcript.includes(keyword) || transcript.includes('小朱')) {
        cooldownRef.current = true;
        onWake();
        rec.stop();
        setTimeout(() => { cooldownRef.current = false; }, 3000);
      }
    };

    rec.onerror = () => { rec.stop(); setIsListening(false); };
    rec.onend = () => setIsListening(false);

    try {
      rec.start();
      setIsListening(true);
      recognitionRef.current = rec;
    } catch {
      // already started or not supported
    }
  }, [keyword, onWake]);  // NOTE: `enabled` NOT in deps — uses ref to avoid closure staleness

  const stopRecognition = useCallback(() => {
    recognitionRef.current?.stop();
    setIsListening(false);
  }, []);

  // Auto-start when enabled becomes true
  useEffect(() => {
    if (enabled && !isListening && !cooldownRef.current) {
      startRecognition();
    }
  }, [enabled]);  // Only trigger when enabled flips

  // Auto-restart after recognition ends (if still enabled & in cooldown exit)
  useEffect(() => {
    if (!enabled || isListening || cooldownRef.current) return;
    const id = setTimeout(() => {
      if (enabledRef.current && !cooldownRef.current) {
        startRecognition();
      }
    }, 2000);
    return () => clearTimeout(id);
  }, [enabled, isListening, startRecognition]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      recognitionRef.current?.stop();
    };
  }, []);

  return { isListening, lastResult, startRecognition, stopRecognition };
}
