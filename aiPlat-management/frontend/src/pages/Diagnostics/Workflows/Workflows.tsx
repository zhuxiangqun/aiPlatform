import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowLeft, ExternalLink, Play, Wand2 } from 'lucide-react';

import { Badge, Button, Card, CardContent, CardHeader, Input, Textarea, toast } from '../../../components/ui';
import { runApi } from '../../../services';

const Workflows: React.FC = () => {
  const navigate = useNavigate();
  const [runId, setRunId] = useState('');
  const [projectId, setProjectId] = useState('');
  const [url, setUrl] = useState('');
  const [tagTemplate, setTagTemplate] = useState('webapp_basic');
  const [expectedTags, setExpectedTags] = useState('login,create,save');
  const [tagExpectationsJson, setTagExpectationsJson] = useState('{}');
  const [stepsJson, setStepsJson] = useState(
    JSON.stringify(
      [
        { tool: 'browser_click', args: { ref: 'button.login' }, tag: 'login' },
        { tool: 'browser_wait_for', args: { timeoutMs: 1500 }, tag: 'login' },
        { tool: 'browser_click', args: { ref: 'button.save' }, tag: 'save' },
      ],
      null,
      2
    )
  );
  const [loading, setLoading] = useState(false);

  const doAutoEval = async (mode: 'qa_only' | 'qa_gate') => {
    const rid = runId.trim();
    if (!rid) {
      toast.error('请先填写 run_id');
      return;
    }
    setLoading(true);
    try {
      let steps: any = undefined;
      try {
        const parsed = JSON.parse(stepsJson || '[]');
        steps = Array.isArray(parsed) ? parsed : undefined;
      } catch {
        steps = undefined;
      }
      if (stepsJson.trim() && !steps) {
        toast.error('steps JSON 解析失败（应为数组）');
        return;
      }
      let tag_expectations: any = undefined;
      try {
        const parsed = JSON.parse(tagExpectationsJson || '{}');
        tag_expectations = parsed && typeof parsed === 'object' ? parsed : undefined;
      } catch {
        tag_expectations = undefined;
      }
      const expected_tags = expectedTags
        .split(',')
        .map((x) => x.trim())
        .filter(Boolean);

      const res: any = await runApi.autoEvaluate(rid, {
        evaluator: 'auto-llm',
        enforce_gate: mode === 'qa_gate',
        project_id: projectId.trim() || undefined,
        url: url.trim() || undefined,
        steps,
        expected_tags,
        tag_expectations,
        tag_template: tagTemplate.trim() || undefined,
      });
      toast.success(mode === 'qa_gate' ? '已执行 QA + Gate' : '已执行 QA-only（生成报告）');
      if (res?.artifact_id) {
        navigate(`/core/learning/artifacts/${encodeURIComponent(String(res.artifact_id))}`);
      }
    } catch (e: any) {
      toast.error(e?.message || '执行失败');
    } finally {
      setLoading(false);
    }
  };

  const doInvestigate = async () => {
    const rid = runId.trim();
    if (!rid) {
      toast.error('请先填写 run_id');
      return;
    }
    setLoading(true);
    try {
      const res: any = await runApi.autoInvestigate(rid);
      toast.success('已生成 Investigate 报告');
      if (res?.artifact_id) navigate(`/core/learning/artifacts/${encodeURIComponent(String(res.artifact_id))}`);
    } catch (e: any) {
      toast.error(e?.message || '生成失败');
    } finally {
      setLoading(false);
    }
  };

  const rid = runId.trim();

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" icon={<ArrowLeft size={16} />} onClick={() => navigate('/diagnostics')}>
              返回
            </Button>
            <h1 className="text-2xl font-semibold text-gray-200">Workflows</h1>
            <Badge variant="info">As-Is</Badge>
          </div>
          <div className="text-sm text-gray-500 mt-1">把分散能力串成“一键流水线”（先从 QA-only / QA+Gate 开始）</div>
        </div>
        <div className="flex items-center gap-2">
          <Link to="/diagnostics/runs">
            <Button variant="secondary" icon={<ExternalLink size={16} />}>
              打开 Runs
            </Button>
          </Link>
          <Link to="/core/learning/artifacts">
            <Button variant="secondary" icon={<ExternalLink size={16} />}>
              打开 Artifacts
            </Button>
          </Link>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <div className="text-sm font-semibold text-gray-200">输入</div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <Input value={runId} placeholder="run_id（必填）" onChange={(e: any) => setRunId(e.target.value)} />
              <Input value={projectId} placeholder="project_id（可选）" onChange={(e: any) => setProjectId(e.target.value)} />
              <Input value={url} placeholder="URL（可选：启用 integrated_browser 后取证）" onChange={(e: any) => setUrl(e.target.value)} />
              <Input value={tagTemplate} placeholder="tag_template（可选）" onChange={(e: any) => setTagTemplate(e.target.value)} />
              <Input value={expectedTags} placeholder="expected_tags（逗号分隔，可选）" onChange={(e: any) => setExpectedTags(e.target.value)} />
              <Input value={tagExpectationsJson} placeholder='tag_expectations JSON（可选，例如 {"login": {"text_contains":["登录"]}}）' onChange={(e: any) => setTagExpectationsJson(e.target.value)} />
            </div>

            <div className="mt-3">
              <div className="text-xs text-gray-500 mb-1">可选：steps（JSON 数组，建议为关键步骤标注 tag，用于 Coverage Gate）</div>
              <Textarea rows={10} value={stepsJson} onChange={(e: any) => setStepsJson(e.target.value)} />
            </div>

            <div className="flex flex-wrap items-center gap-2 mt-3">
              <Button icon={<Play size={16} />} onClick={() => doAutoEval('qa_only')} loading={loading}>
                QA-only（生成报告）
              </Button>
              <Button variant="secondary" icon={<Wand2 size={16} />} onClick={() => doAutoEval('qa_gate')} loading={loading}>
                QA + Gate（硬门控）
              </Button>
              <Button variant="ghost" onClick={doInvestigate} loading={loading}>
                Investigate（调查报告）
              </Button>
              {rid && (
                <>
                  <Link to={`/diagnostics/runs?run_id=${encodeURIComponent(rid)}`}>
                    <Button variant="ghost">定位 Run</Button>
                  </Link>
                  <Link to={`/core/learning/artifacts?run_id=${encodeURIComponent(rid)}`}>
                    <Button variant="ghost">本 Run Artifacts</Button>
                  </Link>
                </>
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="text-sm font-semibold text-gray-200">下一步（待补齐的“完善项”）</div>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 text-sm text-gray-300">
              <div>1) Canary：定时重跑 auto-eval + diff，对比基线并自动触发 change-control / rollback。</div>
              <div>2) Investigate：把“证据链（trace/run/syscalls/evidence）”聚合成单页调查报告。</div>
              <div>3) Ship：发布前自动跑 QA+Gate + 文档同步护栏，再进入审批。</div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default Workflows;
