import React, { useMemo, useState } from 'react';
import { Button, Input, Modal, Select, Textarea, toast } from '../ui';

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

const ExecuteToolModal: React.FC<ExecuteToolModalProps> = ({ open, tool, onClose }) => {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ output?: unknown; error?: any; error_message?: string; error_detail?: any; success?: boolean; latency?: number } | null>(null);
  const [params, setParams] = useState<Record<string, any>>({});

  const paramSchema = tool?.parameters as any;
  const requiredFields: string[] = paramSchema?.required || [];
  const properties = paramSchema?.properties || {};

  const sortedFields = useMemo(() => {
    return Object.entries(properties).sort(([a], [b]) => {
      const aReq = requiredFields.includes(a) ? 0 : 1;
      const bReq = requiredFields.includes(b) ? 0 : 1;
      return aReq - bReq;
    });
  }, [properties, requiredFields]);

  const exampleArgsText = useMemo(() => {
    const ex: Record<string, any> = {};
    for (const [k, specAny] of Object.entries(properties) as any) {
      const spec = specAny as ParameterProperty;
      const isReq = requiredFields.includes(k);
      if (!isReq && spec.default === undefined) continue;
      const t = (spec.type || 'string').toLowerCase();
      if (spec.default !== undefined) ex[k] = spec.default;
      else if (t === 'integer' || t === 'number') ex[k] = 0;
      else if (t === 'boolean') ex[k] = false;
      else if (t === 'array') ex[k] = [];
      else if (t === 'object') ex[k] = {};
      else ex[k] = `<填写 ${k}>`;
    }
    // ensure required fields exist
    for (const k of requiredFields) {
      if (ex[k] !== undefined) continue;
      const spec = (properties as any)?.[k] as ParameterProperty | undefined;
      const t = (spec?.type || 'string').toLowerCase();
      if (t === 'integer' || t === 'number') ex[k] = 0;
      else if (t === 'boolean') ex[k] = false;
      else if (t === 'array') ex[k] = [];
      else if (t === 'object') ex[k] = {};
      else ex[k] = `<填写 ${k}>`;
    }
    return JSON.stringify(ex, null, 2);
  }, [properties, requiredFields]);

  const troubleshooting = useMemo(() => {
    return `### 常见问题排查（尤其是 MCP 工具）
- 404 / Not Found：工具未注册或未放行（MCP：allowed_tools 未包含该 tool_name；或 server 未启用）
- 401/403：鉴权失败或权限不足（检查 token/auth 与策略）
- stdio 工具失败：prod 需通过放行策略（allowlist/command prefixes/launcher），并确保目标可执行文件存在
- 参数错误：对 object/array 参数请传合法 JSON（本页会自动解析字符串 JSON）`;
  }, []);

  const handleExecute = async () => {
    if (!tool) return;
    try {
      setLoading(true);
      setResult(null);

      // 简单校验 required
      for (const f of requiredFields) {
        const v = params[f];
        if (v === undefined || v === null || v === '') {
          toast.error(`请输入 ${f}`);
          setLoading(false);
          return;
        }
      }

      // 对 object/array 字段做 JSON 解析（若是字符串）
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
      const res = await toolApi.execute(tool.name, normalized);
      setResult(res as any);
      toast.success(res.success !== false ? '执行成功' : '执行完成');
    } catch (error: any) {
      toast.error('执行失败');
      setResult({ error: error.message || 'Unknown error', success: false });
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setResult(null);
    setParams({});
    onClose();
  };

  const renderError = () => {
    if (!result) return null;
    const errObj = (result as any).error_detail || (typeof (result as any).error === 'object' ? (result as any).error : null);
    const errMsg =
      (result as any).error_message ||
      (typeof (result as any).error === 'string' ? (result as any).error : '') ||
      (errObj?.message ? String(errObj.message) : '');
    const errCode = errObj?.code ? String(errObj.code) : '';
    if (!errMsg && !errCode) return null;
    return (
      <div className="text-xs text-red-300 mt-2">
        {errCode ? `[${errCode}] ` : ''}
        {errMsg}
      </div>
    );
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
            value={params[name] ?? (spec.default as any) ?? ''}
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

    // object / array: 用 JSON 输入
    if (fieldType === 'object' || fieldType === 'array') {
      return (
        <div key={name} className="space-y-1">
          <div className="text-sm font-medium text-gray-300">
            {name}{isRequired ? <span className="text-error"> *</span> : null}
          </div>
          <Textarea
            rows={4}
            value={params[name] ?? (spec.default ? JSON.stringify(spec.default, null, 2) : '')}
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
          value={params[name] ?? (spec.default as any) ?? ''}
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
      title={`执行 Tool: ${tool?.name || ''}`}
      width={1100}
      footer={
        <>
          <Button variant="secondary" onClick={handleClose} disabled={loading}>关闭</Button>
          <Button variant="primary" onClick={handleExecute} loading={loading}>执行</Button>
        </>
      }
    >
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          {tool?.description && (
            <div className="mb-4 text-sm text-gray-400">{tool.description}</div>
          )}

          {sortedFields.length > 0 ? (
            <div className="space-y-4">
              {sortedFields.map(([name, spec]) => renderField(name, spec as ParameterProperty))}
            </div>
          ) : (
            <div className="py-4 text-center text-gray-400 text-sm">
              此 Tool 无需参数，直接点击"执行"即可
            </div>
          )}

          {result && (
            <div className="mt-4 p-4 rounded-lg border border-dark-border bg-dark-bg">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-gray-100">执行结果</span>
                <span className={`text-xs px-2 py-0.5 rounded ${result.success !== false ? 'bg-green-900/50 text-green-300' : 'bg-red-900/50 text-red-300'}`}>
                  {result.success !== false ? '成功' : '失败'}
                </span>
              </div>
              {result.latency != null && (
                <div className="text-xs text-gray-400 mb-2">耗时: {result.latency.toFixed(1)}ms</div>
              )}
              {result.output !== undefined && result.output !== null && (
                <pre className="text-xs text-gray-300 overflow-auto max-h-60 bg-dark-card border border-dark-border rounded-lg p-3">
                  {typeof result.output === 'string' ? result.output : JSON.stringify(result.output as object, null, 2)}
                </pre>
              )}
              {!result.output && renderError()}
            </div>
          )}
        </div>

        <div className="border border-dark-border rounded-lg bg-dark-card p-3">
          <div className="text-sm font-medium text-gray-200 mb-2">使用说明 / 示例</div>
          <div className="text-xs text-gray-300 whitespace-pre-wrap leading-relaxed mb-3">{troubleshooting}</div>

          <div className="text-xs font-medium text-gray-300 mb-2">参数 Schema（只读）</div>
          <pre className="text-xs text-gray-300 overflow-auto max-h-40 bg-dark-bg border border-dark-border rounded-lg p-3">
            {tool?.parameters ? JSON.stringify(tool.parameters as object, null, 2) : '{}'}
          </pre>

          <div className="mt-3 flex items-center justify-between">
            <div className="text-xs font-medium text-gray-300">调用参数示例（JSON）</div>
            <Button
              variant="secondary"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(exampleArgsText);
                  toast.success('已复制');
                } catch {
                  toast.error('复制失败');
                }
              }}
              disabled={loading}
            >
              复制示例
            </Button>
          </div>
          <pre className="mt-2 text-xs text-gray-300 overflow-auto max-h-40 bg-dark-bg border border-dark-border rounded-lg p-3">
            {exampleArgsText}
          </pre>
        </div>
      </div>
    </Modal>
  );
};

export default ExecuteToolModal;
