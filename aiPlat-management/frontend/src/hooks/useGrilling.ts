import { useState, useCallback, useRef, useEffect } from 'react';

const API = (path: string) => `/api/core/grilling${path}`;

export interface GrillQuestion {
  id: string;
  text: string;
  label: string;
  options: string[];
  required: boolean;
}

export interface GrillProgress {
  current: number;
  total: number;
  completed_required: number;
  required_count: number;
}

export interface GrillSession {
  session_id: string;
  status: 'asking' | 'completed' | 'no_dimensions' | 'error';
  question?: GrillQuestion;
  progress?: GrillProgress;
  answered?: number;
  total_questions?: number;
  answers_flat?: Record<string, string>;
  summary_markdown?: string;
  message?: string;
}

export function useGrilling(entry_point: string, domain_id: string = '') {
  const [session, setSession] = useState<GrillSession | null>(null);
  const [loading, setLoading] = useState(false);
  const [answers, setAnswers] = useState<{ id: string; label: string; answer: string }[]>([]);
  const sessionRef = useRef<string>('');

  const start = useCallback(async (context?: Record<string, unknown>) => {
    setLoading(true);
    setAnswers([]);
    try {
      const res = await fetch(API('/start'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ entry_point, domain_id, context }),
      });
      const data: GrillSession = await res.json();
      sessionRef.current = data.session_id;
      setSession(data);
      return data;
    } finally {
      setLoading(false);
    }
  }, [entry_point, domain_id]);

  const answer = useCallback(async (answerText: string) => {
    if (!sessionRef.current) return;
    setLoading(true);
    try {
      const res = await fetch(API('/answer'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionRef.current, answer: answerText }),
      });
      const data: GrillSession = await res.json();
      setSession(data);
      if (session?.question) {
        setAnswers((prev) => [...prev, { id: session.question!.id, label: session.question!.label, answer: answerText }]);
      }
      return data;
    } finally {
      setLoading(false);
    }
  }, [session?.question]);

  const skip = useCallback(async () => {
    if (!sessionRef.current) return;
    setLoading(true);
    try {
      const res = await fetch(API('/skip'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionRef.current, answer: '' }),
      });
      const data: GrillSession = await res.json();
      setSession(data);
      return data;
    } finally {
      setLoading(false);
    }
  }, []);

  const finalize = useCallback(async () => {
    if (!sessionRef.current) return;
    setLoading(true);
    try {
      const res = await fetch(API('/finalize'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionRef.current }),
      });
      const data: GrillSession = await res.json();
      setSession(data);
      return data;
    } finally {
      setLoading(false);
    }
  }, []);

  // Auto-start on mount
  const autoStartRef = useRef(false);
  useEffect(() => {
    if (!autoStartRef.current) {
      autoStartRef.current = true;
      start();
    }
  }, [start]);

  return {
    session, loading, answers,
    answer, skip, finalize, start,
  };
}
