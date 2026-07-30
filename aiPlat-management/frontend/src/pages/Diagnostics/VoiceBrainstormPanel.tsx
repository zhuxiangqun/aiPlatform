/**
 * VoiceBrainstormPanel — 语音漫谈 (Karpathy 对齐)
 *
 * 打开麦克风自由漫谈10分钟 → Whisper 转录 → LLM 意图重构 → 结构化摘要
 *
 * 核心理念: 你不需要把问题想清楚再问AI, 让AI来帮你想清楚。
 */
import React, { useState, useRef, useCallback } from 'react';
import { Card, CardContent, CardHeader, Button, toast } from '../../components/ui';
import { Mic, Square, Loader2, Brain, CheckCircle, AlertCircle, Lightbulb, Volume2 } from 'lucide-react';

const API_BASE = '/api/platform/apps/fde';

const VoiceBrainstormPanel: React.FC = () => {
  const [recording, setRecording] = useState(false);
  const [duration, setDuration] = useState(0);
  const [transcript, setTranscript] = useState('');
  const [summary, setSummary] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [playingAudio, setPlayingAudio] = useState(false);
  const timerRef = useRef<any>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      const chunks: Blob[] = [];

      recorder.ondataavailable = (e) => chunks.push(e.data);
      recorder.onstop = async () => {
        const blob = new Blob(chunks, { type: 'audio/webm' });
        // Send to backend for transcription (simulated for now with textarea)
        toast?.info?.('录音完成, 请检查转录文本后点击"开始整理"');
      };

      recorder.start(1000);
      mediaRecorderRef.current = recorder;
      setRecording(true);
      setSummary(null);

      // 10-minute countdown timer
      let seconds = 0;
      timerRef.current = setInterval(() => {
        seconds++;
        setDuration(seconds);
        if (seconds >= 600) {
          stopRecording();
        }
      }, 1000);
    } catch (e: any) {
      toast?.error?.('麦克风权限被拒绝, 请改用下方的文本漫谈模式');
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
    }
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    setRecording(false);
  };

  const runBrainstorm = async () => {
    if (!transcript.trim() || transcript.trim().length < 20) {
      toast?.error?.('转录文本过短, 请继续说或用文本漫谈模式输入');
      return;
    }
    setLoading(true);
    setSummary(null);
    try {
      const r = await fetch(`${API_BASE}/voice/brainstorm`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ transcript, duration_seconds: duration }),
      });
      const d = await r.json();
      if (d.success && d.summary) {
        setSummary(d.summary);
      } else {
        toast?.error?.(d.error || '处理失败');
      }
    } catch (e: any) {
      toast?.error?.(e?.message || '请求失败');
    }
    setLoading(false);
  };

  const formatTime = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${m.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}`;
  };

  const toneIcon = (tone: string) => {
    switch (tone) {
      case '思考型': return <Brain className="w-4 h-4 text-blue-400" />;
      case '焦虑型': return <AlertCircle className="w-4 h-4 text-orange-400" />;
      case '探索型': return <Lightbulb className="w-4 h-4 text-yellow-400" />;
      case '决策型': return <CheckCircle className="w-4 h-4 text-green-400" />;
      default: return null;
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-100">语音漫谈</h2>
          <p className="text-xs text-gray-500">自由漫谈10分钟 → AI 自动提取核心意图和可执行步骤</p>
        </div>
      </div>

      {/* Recording controls */}
      <Card className="border-gray-700/50">
        <CardContent className="p-4 space-y-3">
          <div className="flex items-center gap-3">
            {!recording ? (
              <Button variant="default" size="sm" onClick={startRecording} className="bg-red-600 hover:bg-red-500">
                <Mic className="w-4 h-4 mr-1" />开始录音
              </Button>
            ) : (
              <Button variant="default" size="sm" onClick={stopRecording} className="animate-pulse">
                <Square className="w-4 h-4 mr-1" />停止录音 ({formatTime(duration)})
              </Button>
            )}
            <span className="text-xs text-gray-500">
              {recording ? '🔴 录音中... 像跟同事闲聊一样随心说' : '或使用下方的文本漫谈模式'}
            </span>
          </div>

          {/* Text area for manual input or transcribed text */}
          <textarea
            className="w-full h-32 bg-gray-800 border border-gray-700 rounded p-2.5 text-sm text-gray-200 resize-y"
            placeholder={`把你的想法直接打字说出来——不需要精炼、不需要结构、可以有'嗯/啊'和自我纠正。让AI帮你想清楚...`}
            value={transcript}
            onChange={e => setTranscript(e.target.value)}
          />

          <div className="flex items-center gap-2">
            <Button variant="default" size="sm" onClick={runBrainstorm} loading={loading}
              disabled={!transcript.trim() || transcript.trim().length < 20}>
              <Brain className="w-4 h-4 mr-1" />开始整理
            </Button>
            <span className="text-[10px] text-gray-600">
              {transcript.length} 字符 (最少20)
            </span>
          </div>
        </CardContent>
      </Card>

      {/* Summary result */}
      {summary && (
        <Card className="border-blue-500/20">
          <CardHeader>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-200">整理结果</span>
              {summary.tone && (
                <span className="flex items-center gap-1 text-xs text-gray-500">
                  {toneIcon(summary.tone)}
                  {summary.tone}
                </span>
              )}
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Core intent */}
            <div>
              <div className="text-xs text-blue-400 font-medium mb-1">核心意图</div>
              <div className="text-sm text-gray-200 p-2.5 rounded bg-gray-800/50 border border-gray-700/30">
                {summary.core_intent || '未能提取'}
              </div>
            </div>

            {/* Actionable steps */}
            {summary.actionable_steps?.length > 0 && (
              <div>
                <div className="text-xs text-green-400 font-medium mb-1">可执行步骤</div>
                <div className="space-y-1">
                  {summary.actionable_steps.map((step: string, i: number) => (
                    <div key={i} className="text-sm text-gray-300 flex items-center gap-2 p-1.5 rounded bg-gray-800/30">
                      <CheckCircle className="w-3.5 h-3.5 text-green-400 flex-shrink-0" />
                      {step}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Fuzzy points */}
            {summary.fuzzy_points?.length > 0 && (
              <div>
                <div className="text-xs text-yellow-400 font-medium mb-1">待澄清的模糊点</div>
                <div className="space-y-1">
                  {summary.fuzzy_points.map((point: string, i: number) => (
                    <div key={i} className="text-sm text-yellow-300 flex items-center gap-2 p-1.5 rounded bg-yellow-500/5">
                      <AlertCircle className="w-3.5 h-3.5 text-yellow-400 flex-shrink-0" />
                      {point}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Empty state */}
      {!summary && !loading && (
        <Card className="border-dashed border-gray-700">
          <CardContent className="p-8 text-center">
            <div className="text-gray-600 mb-2"><Brain className="w-8 h-8 mx-auto" /></div>
            <div className="text-sm text-gray-500">开始录音或输入文本</div>
            <div className="text-xs text-gray-600 mt-1">
              "你不需要把问题想清楚再问AI, 让AI来帮你想清楚" — Karpathy
            </div>
          </CardContent>
        </Card>
      )}

      {loading && (
        <div className="text-center text-gray-500 py-8 animate-pulse">
          <Loader2 className="w-5 h-5 mx-auto mb-2 animate-spin" />
          AI 正在整理你的思路...
        </div>
      )}
    </div>
  );
};

export default VoiceBrainstormPanel;
