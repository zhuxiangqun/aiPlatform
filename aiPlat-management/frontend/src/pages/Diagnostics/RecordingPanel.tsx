/**
 * RecordingPanel — 操作录制 + Skill 自动生成面板 (P1)
 *
 * ▶️ 录制 / ⏹ 停止 → 预览步骤 → 生成 SKILL.md → 编辑 → 注册
 */
import React, { useState, useRef, useCallback } from 'react';
import { Card, CardContent, CardHeader, Button, toast } from '../../components/ui';
import { Play, Square, FileText, CheckCircle, XCircle, RefreshCw, Save, Edit3 } from 'lucide-react';

const API_BASE = '/api/platform/apps/fde';

const RecordingPanel: React.FC = () => {
  const [recordingId, setRecordingId] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const [steps, setSteps] = useState<any[]>([]);
  const [skillMd, setSkillMd] = useState('');
  const [validation, setValidation] = useState<any>(null);
  const [skillName, setSkillName] = useState('');
  const [editing, setEditing] = useState(false);

  const startRec = async () => {
    try {
      const r = await fetch(`${API_BASE}/recording/start`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description: '录制的操作流程' }),
      });
      const d = await r.json();
      setRecordingId(d.recording_id);
      setIsRecording(true);
      setSteps([]); setSkillMd(''); setValidation(null);
      toast?.info?.('录制中...');
    } catch (e: any) { toast?.error?.(e?.message || '启动失败'); }
  };

  const stopRec = async () => {
    try {
      const r = await fetch(`${API_BASE}/recording/stop`, { method: 'POST' });
      const d = await r.json();
      setIsRecording(false);
      setSteps(d.steps || []);
      toast?.success?.(`录制完成: ${d.step_count} 步`);
    } catch (e: any) { toast?.error?.(e?.message || '停止失败'); }
  };

  const generate = async () => {
    if (!recordingId) return;
    try {
      const r = await fetch(`${API_BASE}/recording/generate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ recording_id: recordingId }),
      });
      const d = await r.json();
      setSkillMd(d.skill_md);
      setValidation(d.validation);
      if (!d.validation?.valid) {
        toast?.warning?.(`质量检查: ${d.validation?.score}/100`);
      } else {
        toast?.success?.('Skill 生成完成');
      }
    } catch (e: any) { toast?.error?.(e?.message || '生成失败'); }
  };

  const register = async () => {
    if (!skillMd || !skillName.trim()) return;
    try {
      await fetch(`${API_BASE}/recording/register`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ skill_md: skillMd, skill_name: skillName.trim() }),
      });
      toast?.success?.('Skill 已注册');
    } catch (e: any) { toast?.error?.(e?.message || '注册失败'); }
  };

  const statusIcon = (status: string) =>
    status === 'success' ? <CheckCircle className="w-3 h-3 text-green-400" /> :
    status === 'failed' ? <XCircle className="w-3 h-3 text-red-400" /> : null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-100">操作录制</h2>
          <p className="text-xs text-gray-500">录制操作 → 一键生成 SKILL.md → 注册</p>
        </div>
        <div className="flex items-center gap-2">
          {!isRecording ? (
            <Button variant="default" size="sm" onClick={startRec} className="bg-red-600 hover:bg-red-500">
              <Play className="w-3 h-3 mr-1" />开始录制
            </Button>
          ) : (
            <Button variant="default" size="sm" onClick={stopRec} className="bg-gray-600 animate-pulse">
              <Square className="w-3 h-3 mr-1" />停止录制 ({steps.length})
            </Button>
          )}
        </div>
      </div>

      {isRecording && (
        <Card className="border-red-500/20 animate-pulse">
          <CardContent className="p-3 text-center text-sm text-red-400">🔴 录制中 — 请执行需要录制的操作...</CardContent>
        </Card>
      )}

      {steps.length > 0 && (
        <Card className="border-gray-700/50">
          <CardHeader><span className="text-sm font-medium text-gray-200">操作步骤 ({steps.length})</span></CardHeader>
          <CardContent>
            <div className="space-y-1 max-h-60 overflow-y-auto">
              {steps.map((s, i) => (
                <div key={i} className="flex items-center gap-2 text-xs text-gray-400 py-1">
                  {statusIcon(s.result)} {s.seq}. {s.tool} ({s.duration_ms?.toFixed(0)}ms)
                </div>
              ))}
            </div>
            <div className="mt-3 flex gap-2">
              <Button variant="default" size="sm" onClick={generate}>生成 SKILL.md</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {skillMd && (
        <Card className="border-gray-700/50">
          <CardHeader>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-200">生成的 SKILL.md</span>
              <div className="flex items-center gap-2">
                {validation && (
                  <span className={`text-xs ${validation.score >= 70 ? 'text-green-400' : 'text-yellow-400'}`}>
                    质量 {validation.score}/100
                  </span>
                )}
                <Button variant="ghost" size="sm" onClick={() => setEditing(!editing)}>
                  <Edit3 className="w-3 h-3 mr-1" />{editing ? '预览' : '编辑'}
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {editing ? (
              <textarea className="w-full h-64 bg-gray-800 border border-gray-700 rounded p-2 text-xs text-gray-200 font-mono resize-y"
                value={skillMd} onChange={e => setSkillMd(e.target.value)} />
            ) : (
              <pre className="text-xs text-gray-300 bg-gray-800 p-2 rounded max-h-64 overflow-y-auto">{skillMd.slice(0, 2000)}</pre>
            )}
            {validation?.issues?.length > 0 && (
              <div className="mt-2 space-y-1">
                {validation.issues.map((i: string, idx: number) => (
                  <div key={idx} className="text-[10px] text-yellow-400">⚠ {i}</div>
                ))}
              </div>
            )}
            <div className="mt-3 flex gap-2">
              <input className="flex-1 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-gray-200"
                value={skillName} onChange={e => setSkillName(e.target.value)} placeholder="Skill 名称" />
              <Button variant="default" size="sm" onClick={register} disabled={!skillName.trim()}>
                <Save className="w-3 h-3 mr-1" />注册 Skill
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default RecordingPanel;
