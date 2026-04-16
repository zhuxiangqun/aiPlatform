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
  const [result, setResult] = useState<{ output?: unknown; error?: string; success?: boolean; latency?: number } | null>(null);
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
      width={720}
      footer={
        <>
          <Button variant="secondary" onClick={handleClose} disabled={loading}>关闭</Button>
          <Button variant="primary" onClick={handleExecute} loading={loading}>执行</Button>
        </>
      }
    >
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
          {result.error && !result.output && (
            <div className="text-xs text-red-300">{result.error}</div>
          )}
        </div>
      )}
    </Modal>
  );
};

export default ExecuteToolModal;
