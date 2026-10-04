import React, { useEffect, useMemo, useState } from 'react';
import { Button, Input, Modal, Select, Textarea, toast } from '../ui';
import { diagnosticsApi } from '../../services';
import { buildFormParamsFromSchema, buildParamSmokeExamples } from '../../utils/executionSamples';
import ExecuteResultPanel from '../execution/ExecuteResultPanel';
import ExecuteFlowFullscreen from '../execution/ExecuteFlowFullscreen';
import ExecutionQualityReviewPanel, {
  type ExecutionQualityReview,
} from '../execution/ExecutionQualityReviewPanel';
import { RunVerdictBanner, deriveRunVerdict, outputAsText } from '../execution/runVerdict';

interface ParameterProperty {
  type?: string;
  description?: string;
  default?: unknown;
  enum?: string[];
}

interface ExecuteToolModalProps {
  open: boolean;
  tool: {
    name: string;
    description?: string;
    parameters?: Record<string, unknown>;
  } | null;
  onClose: () => void;
}

type ToolExecResult = {
  status?: string;
  success?: boolean;
  output?: unknown;
  error?: any;
  error_message?: string;
  error_detail?: any;
  latency?: number;
  duration_ms?: number;
  run_id?: string;
  execution_id?: string;
  quality_review?: ExecutionQualityReview | null;
};

const ExecuteToolModal: React.FC<ExecuteToolModalProps> = ({ open, tool, onClose }) => {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ToolExecResult | null>(null);
  const [params, setParams] = useState<Record<string, any>>({});
  const [autoSmoke, setAutoSmoke] = useState(false);
  const [flowFullscreen, setFlowFullscreen] = useState(false);
  const [resolvedTool, setResolvedTool] = useState<ExecuteToolModalProps['tool']>(null);
  const [schemaLoading, setSchemaLoading] = useState(false);

  const activeTool = resolvedTool || tool;
  const paramSchema = activeTool?.parameters as any;
  const requiredFields: string[] = paramSchema?.required || [];
  const properties = paramSchema?.properties || {};

  const sortedFields = useMemo(() => {
    return Object.entries(properties).sort(([a], [b]) => {
      const aReq = requiredFields.includes(a) ? 0 : 1;
      const bReq = requiredFields.includes(b) ? 0 : 1;
      return aReq - bReq;
    });
  }, [properties, requiredFields]);

  const smokeExamples = useMemo(() => {
    return buildParamSmokeExamples(paramSchema || {}, activeTool?.name || 'Tool', {
      skillHint: `${activeTool?.name || ''} ${activeTool?.description || ''}`,
    });
  }, [paramSchema, activeTool?.name, activeTool?.description]);

  const exampleArgsText = useMemo(() => {
    const complex = smokeExamples.find((e) => e.title.includes('复杂') || e.title.includes('全量'));
    return complex?.content || smokeExamples[0]?.content || '{}';
  }, [smokeExamples]);

  const fillFromExample = (content: string) => {
    try {
      const obj = JSON.parse(content);
      if (obj && typeof obj === 'object' && !Array.isArray(obj)) {
        const flat = (paramSchema as any)?.properties || {};
        const next: Record<string, any> = {};
        for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
          const typ = String(flat[k]?.type || '').toLowerCase();
          if ((typ === 'object' || typ === 'array') && typeof v === 'object' && v !== null) {
            next[k] = JSON.stringify(v, null, 2);
          } else {
            next[k] = v;
          }
        }
        setParams(next);
        return;
      }
    } catch {
      /* ignore */
    }
    toast.error('用例不是合法 JSON');
  };

  const troubleshooting = useMemo(() => {
    return `### 如何填写输入
- 点右侧「填入」写入测试用例：主路径（必填）/ 边界异常 / 复杂全量。
- 「边界/异常」故意含空值、不可达 URL、0/-1 等，用于验收校验与失败路径。
- object/array 请保持合法 JSON；本页执行前会自动解析。

### 常见问题排查（尤其是 MCP 工具）
- 404 / Not Found：工具未注册或未放行（MCP：allowed_tools 未包含该 tool_name；或 server 未启用）
- 401/403：鉴权失败或权限不足（检查 token/auth 与策略）
- stdio 工具失败：prod 需通过放行策略（allowlist/command prefixes/launcher），并确保目标可执行文件存在
- 参数错误：对 object/array 参数请传合法 JSON（本页会自动解析字符串 JSON）`;
  }, []);

  const displayVerdict = useMemo(
    () =>
      result
        ? deriveRunVerdict({
            status: result.status || (result.success === false ? 'failed' : result.success === true ? 'completed' : ''),
            error: result.error_message || result.error,
            outputText: outputAsText(result.output),
          })
        : null,
    [result],
  );

  useEffect(() => {
    if (!open || !tool?.name) {
      setResolvedTool(null);
      return;
    }
    let cancelled = false;
    setResult(null);
    setFlowFullscreen(false);
    setSchemaLoading(true);
    (async () => {
      try {
        const { toolApi } = await import('../../services');
        const fresh = await toolApi.get(tool.name);
        if (cancelled) return;
        const merged = {
          name: String(fresh?.name || tool.name),
          description: String(fresh?.description || tool.description || ''),
          parameters: (fresh as any)?.parameters || tool.parameters || {},
        };
        setResolvedTool(merged);
        const schema = (merged.parameters as any) || {};
        const hasProps = schema?.properties && Object.keys(schema.properties).length > 0;
        setParams(hasProps ? buildFormParamsFromSchema(schema, { includeOptional: false }) : {});
      } catch {
        if (cancelled) return;
        // Fall back to list-row payload (may be stale / empty schema).
        setResolvedTool(tool);
        const schema = (tool.parameters as any) || {};
        const hasProps = schema?.properties && Object.keys(schema.properties).length > 0;
        setParams(hasProps ? buildFormParamsFromSchema(schema, { includeOptional: false }) : {});
      } finally {
        if (!cancelled) setSchemaLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, tool?.name]);

  const handleExecute = async () => {
    if (!activeTool) return;
    try {
      setLoading(true);
      setResult(null);

      // 允许空串以覆盖「边界/异常」用例；仅缺 key 时拦截
      const missing = requiredFields.filter((f) => params[f] === undefined || params[f] === null);
      if (missing.length) {
        toast.error(`请输入 ${missing[0]}`);
        setLoading(false);
        return;
      }

      const normalized: Record<string, any> = { ...params };
      for (const [k, spec] of Object.entries(properties) as any) {
        const t = (spec as any)?.type;
        if ((t === 'object' || t === 'array') && typeof normalized[k] === 'string' && normalized[k].trim()) {
          try {
            normalized[k] = JSON.parse(normalized[k]);
          } catch {
            toast.error(`参数 ${k} 不是合法 JSON`);
            setLoading(false);
            return;
          }
        }
      }

      const { toolApi } = await import('../../services');
      const res = (await toolApi.execute(activeTool.name, normalized)) as ToolExecResult;
      const status =
        String(res.status || '') ||
        (res.success === false ? 'failed' : res.success === true ? 'completed' : 'completed');
      setResult({
        ...res,
        status,
        duration_ms: res.duration_ms ?? (res.latency != null ? Math.round(res.latency) : undefined),
        run_id: res.run_id || res.execution_id,
        quality_review: (res as any)?.quality_review || null,
      });
      const qr = (res as any)?.quality_review as ExecutionQualityReview | undefined;
      if (qr && (qr.verdict === 'fail' || qr.verdict === 'warn')) {
        toast.warning(qr.headline || '执行结束，产物/返回需改进（见质量复核）');
      } else if (status === 'completed' || res.success !== false) {
        toast.success('执行完成');
      } else {
        toast.error('执行失败');
      }

      if (autoSmoke) {
        try {
          const smoke = await diagnosticsApi.runE2ESmoke({ tenant_id: 'ops_smoke', actor_id: 'admin', agent_model: 'deepseek-reasoner' });
          toast.success(smoke?.ok ? '全链路冒烟通过' : '全链路冒烟失败');
        } catch (e: any) {
          toast.error('全链路冒烟失败', String(e?.message || 'unknown'));
        }
      }

      const rid = res.run_id || res.execution_id;
      if (rid && (status === 'running' || status === 'accepted' || status === 'completed')) {
        setFlowFullscreen(true);
      }
    } catch (error: any) {
      toast.error('执行失败');
      setResult({ status: 'failed', error: error.message || 'Unknown error', success: false });
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setResult(null);
    setParams({});
    setResolvedTool(null);
    setFlowFullscreen(false);
    onClose();
  };

  const handleRerunSameCase = () => {
    setFlowFullscreen(true);
    void handleExecute();
  };

  const renderField = (name: string, spec: ParameterProperty) => {
    const isRequired = requiredFields.includes(name);
    const fieldType = spec.type || 'string';

    if (fieldType === 'integer' || fieldType === 'number') {
      return (
        <div key={name} className="space-y-1">
          <div className="text-sm font-medium text-gray-300">
            {name}{isRequired ? <span className="text-error"> *</span> : null}
          </div>
          <Input
            type="number"
            value={params[name] ?? ''}
            onChange={(e: any) => setParams((p) => ({ ...p, [name]: e.target.value === '' ? '' : Number(e.target.value) }))}
            placeholder={spec.description || `输入 ${name}`}
          />
          {spec.description && <div className="text-xs text-gray-500">{spec.description}</div>}
        </div>
      );
    }

    if (spec.enum && spec.enum.length > 0) {
      return (
        <div key={name} className="space-y-1">
          <div className="text-sm font-medium text-gray-300">
            {name}{isRequired ? <span className="text-error"> *</span> : null}
          </div>
          <Select
            value={params[name] ?? (spec.default as any) ?? ''}
            onChange={(v) => setParams((p) => ({ ...p, [name]: v }))}
            options={spec.enum.map((v) => ({ value: v, label: v }))}
            placeholder={spec.description || `选择 ${name}`}
          />
          {spec.description && <div className="text-xs text-gray-500">{spec.description}</div>}
        </div>
      );
    }

    if (fieldType === 'object' || fieldType === 'array') {
      return (
        <div key={name} className="space-y-1">
          <div className="text-sm font-medium text-gray-300">
            {name}{isRequired ? <span className="text-error"> *</span> : null}
          </div>
          <Textarea
            rows={4}
            value={params[name] ?? ''}
            onChange={(e: any) => setParams((p) => ({ ...p, [name]: e.target.value }))}
            placeholder={spec.description || `输入 ${name}（JSON）`}
          />
          {spec.description && <div className="text-xs text-gray-500">{spec.description}</div>}
        </div>
      );
    }

    return (
      <div key={name} className="space-y-1">
        <div className="text-sm font-medium text-gray-300">
          {name}{isRequired ? <span className="text-error"> *</span> : null}
        </div>
        <Input
          value={params[name] ?? ''}
          onChange={(e: any) => setParams((p) => ({ ...p, [name]: e.target.value }))}
          placeholder={spec.description || `输入 ${name}`}
        />
        {spec.description && <div className="text-xs text-gray-500">{spec.description}</div>}
      </div>
    );
  };

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title={`执行 Tool: ${activeTool?.name || tool?.name || ''}`}
      width={1100}
      footer={
        <>
          <Button variant="secondary" onClick={handleClose} disabled={loading}>关闭</Button>
          <Button variant="primary" onClick={handleExecute} loading={loading || schemaLoading}>执行</Button>
        </>
      }
    >
      <label className="mb-3 flex items-center gap-2 text-sm text-gray-400">
        <input type="checkbox" checked={autoSmoke} onChange={(e) => setAutoSmoke(e.target.checked)} />
        执行后自动运行全链路冒烟（会创建/清理资源）
      </label>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          {activeTool?.description && (
            <div className="mb-4 text-sm text-gray-400">{activeTool.description}</div>
          )}

          {schemaLoading ? (
            <div className="py-4 text-center text-gray-400 text-sm">正在加载参数 Schema…</div>
          ) : sortedFields.length > 0 ? (
            <div className="space-y-4">
              <div className="text-xs text-gray-500">点右侧「填入」按 Schema 写入测试参数，或手动填写后执行。</div>
              {sortedFields.map(([name, spec]) => renderField(name, spec as ParameterProperty))}
            </div>
          ) : (
            <div className="py-4 text-center text-gray-400 text-sm">
              此 Tool 无需参数，直接点击"执行"即可
            </div>
          )}

          {result && !flowFullscreen && (
            <ExecuteResultPanel
              result={result}
              loading={loading}
              qualityReview={result.quality_review}
              onOpenFlow={result.run_id || result.execution_id ? () => setFlowFullscreen(true) : undefined}
              onEditSop={() =>
                toast.info('Tool 请走「编辑 / AI 审核」补 description / parameters，勿套 Skill SOP 一键修复')
              }
              onRerunSameCase={handleRerunSameCase}
              rerunLoading={loading}
            />
          )}
        </div>

        <div className="border border-dark-border rounded-lg bg-dark-card p-3">
          <div className="text-sm font-medium text-gray-200 mb-2">使用说明 / 示例</div>
          <div className="text-xs text-gray-300 whitespace-pre-wrap leading-relaxed mb-3">{troubleshooting}</div>

          <div className="text-xs font-medium text-gray-300 mb-2">参数 Schema（只读）</div>
          <pre className="text-xs text-gray-300 overflow-auto max-h-40 bg-dark-bg border border-dark-border rounded-lg p-3">
            {activeTool?.parameters ? JSON.stringify(activeTool.parameters as object, null, 2) : '{}'}
          </pre>

          <div className="mt-3 space-y-2">
            <div className="text-xs font-medium text-gray-300">测试用例 — 点「填入」写入左侧参数（主路径 / 边界 / 复杂）</div>
            {smokeExamples.map((ex) => (
              <div key={ex.title} className="flex flex-col gap-1">
                <div className="flex items-center justify-between gap-2">
                  <div className="text-xs text-gray-300 truncate font-medium">{ex.title}</div>
                  <div className="flex gap-2">
                    <Button variant="secondary" onClick={() => fillFromExample(ex.content)} disabled={loading || schemaLoading}>填入</Button>
                    <Button
                      variant="secondary"
                      onClick={async () => {
                        try {
                          await navigator.clipboard.writeText(ex.content);
                          toast.success('已复制');
                        } catch {
                          toast.error('复制失败');
                        }
                      }}
                      disabled={loading || schemaLoading}
                    >
                      复制
                    </Button>
                  </div>
                </div>
                <div className="text-xs text-gray-500 truncate" style={{ fontFamily: 'monospace' }}>
                  {ex.content.length > 80 ? `${ex.content.slice(0, 80)}…` : ex.content}
                </div>
              </div>
            ))}
          </div>
          <pre className="mt-2 text-xs text-gray-300 overflow-auto max-h-40 bg-dark-bg border border-dark-border rounded-lg p-3">
            {exampleArgsText}
          </pre>
        </div>
      </div>

      <ExecuteFlowFullscreen
        open={!!(flowFullscreen && (result?.run_id || result?.execution_id))}
        runId={String(result?.run_id || result?.execution_id || '')}
        title={`执行流程 · ${activeTool?.name || 'Tool'}`}
        verdict={displayVerdict}
        status={result?.status}
        running={result?.status === 'running' || result?.status === 'accepted'}
        onClose={() => setFlowFullscreen(false)}
        footer={
          result && displayVerdict ? (
            <div className="space-y-2">
              <RunVerdictBanner verdict={displayVerdict} />
              <ExecutionQualityReviewPanel
                review={result.quality_review}
                persistKey="tool-exec"
                onEditSop={() =>
                  toast.info('Tool 请走「编辑 / AI 审核」补 description / parameters，勿套 Skill SOP 一键修复')
                }
                onRerunSameCase={handleRerunSameCase}
                rerunLoading={loading}
              />
              {outputAsText(result.output) ? (
                <pre className="text-xs text-gray-300 overflow-auto max-h-40 bg-dark-bg border border-dark-border rounded-lg p-3 whitespace-pre-wrap">
                  {outputAsText(result.output).slice(0, 4000)}
                </pre>
              ) : null}
            </div>
          ) : null
        }
      />
    </Modal>
  );
};

export default ExecuteToolModal;
