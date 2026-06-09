import React, { useState, useMemo } from 'react';
import { Modal, Button, Input, toast } from '../ui';
import { toolApi } from '../../services';

interface ParamRow { key: string; type: string; desc: string }

const AddToolModal: React.FC<{ open: boolean; onClose: () => void; onSuccess: () => void }> = ({ open, onClose, onSuccess }) => {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [advanced, setAdvanced] = useState(false);
  const [code, setCode] = useState('');
  const [params, setParams] = useState<ParamRow[]>([{ key: '', type: 'string', desc: '' }]);
  const [loading, setLoading] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiWarning, setAiWarning] = useState('');

  const generatedCode = useMemo(() => {
    if (advanced) return code;
    const validParams = params.filter(p => p.key.trim());
    const propsLines = validParams.map(p => `      "${p.key}": {"type": "${p.type}", "description": "${p.desc}"}`);
    const hasParams = validParams.length > 0;
    let result = 'TOOL_DEF = {\n';
    result += `  "id": "${name || 'my_tool'}",\n`;
    result += `  "name": "${name || 'my_tool'}",\n`;
    result += `  "description": "${description || '...'}",\n`;
    if (hasParams) {
      result += '  "parameters": {\n    "type": "object",\n    "properties": {\n';
      result += propsLines.join(',\n') + '\n';
      result += '    }\n  },\n';
    } else {
      result += '  "parameters": {},\n';
    }
    result += '  "execute": lambda params: {"result": "ok"}\n';
    result += '}';
    return result;
  }, [name, description, params, advanced, code]);

  const handleAiGenerate = async () => {
    if (!name.trim() || !description.trim()) return;
    setAiLoading(true);
    try {
      const res = await toolApi.autoFill({ name: name.trim(), description: description.trim() });
      setCode(res.code || '');
      setAiWarning(res.warning || '');
      // Populate params table from AI-extracted parameters
      const r = res as any;
      if (r.parameters && typeof r.parameters === 'object' && r.parameters.properties) {
        const newParams: ParamRow[] = [];
        const props = r.parameters.properties || {};
        for (const key of Object.keys(props)) {
          const prop = props[key] || {};
          newParams.push({ key, type: prop.type || 'string', desc: prop.description || '' });
        }
        if (newParams.length > 0) setParams(newParams);
      }
      setAdvanced(true);
    } catch (e: any) {
      toast.error('AI 生成失败', e?.detail || e?.message || String(e));
    } finally { setAiLoading(false); }
  };

  const handleCreate = async () => {
    const finalCode = advanced ? code.trim() : generatedCode.trim();
    if (!name.trim() || !finalCode) return;
    setLoading(true);
    try {
      await toolApi.create({ name: name.trim(), description: description.trim(), code: finalCode });
      toast.success(`Tool ${name} 已保存`);
      setName(''); setDescription(''); setCode(''); setParams([{ key: '', type: 'string', desc: '' }]); setAdvanced(false);
      onSuccess();
      onClose();
    } catch (e: any) {
      toast.error('保存失败', e?.detail || e?.message || String(e));
    } finally { setLoading(false); }
  };

  const addParam = () => setParams([...params, { key: '', type: 'string', desc: '' }]);
  const updateParam = (i: number, field: keyof ParamRow, val: string) => {
    const next = [...params];
    next[i] = { ...next[i], [field]: val };
    setParams(next);
  };
  const removeParam = (i: number) => {
    if (params.length <= 1) return;
    setParams(params.filter((_, idx) => idx !== i));
  };

  return (
    <Modal open={open} onClose={onClose} title="新增 Tool" width={680}
      footer={
        <div className="flex gap-2 justify-end">
          <Button variant="ghost" onClick={() => setAdvanced(!advanced)}>{advanced ? '普通模式' : '高级模式'}</Button>
          <Button variant="secondary" onClick={onClose}>取消</Button>
          <Button variant="primary" onClick={handleCreate} loading={loading}
            disabled={!name.trim() || (!advanced && !name.trim()) || (advanced && !code.trim())}>保存</Button>
        </div>
      }>
      <div className="space-y-3 text-sm text-gray-300">
        <p className="text-xs text-gray-500">新增一个 workspace Tool。代码写入 ~/.aiplat/tools/ 目录，重启 Core 后自动加载。</p>
        <div className="flex gap-1 text-xs mb-2">
          <button onClick={() => setAdvanced(false)} className={`px-3 py-1 rounded text-xs ${!advanced ? 'bg-primary/20 text-primary' : 'text-gray-500 hover:text-gray-300'}`}>向导模式</button>
          <button onClick={() => setAdvanced(true)} className={`px-3 py-1 rounded text-xs ${advanced ? 'bg-primary/20 text-primary' : 'text-gray-500 hover:text-gray-300'}`}>直接写代码</button>
          <span className="flex-1" />
          <Button variant="secondary" size="sm" onClick={handleAiGenerate} loading={aiLoading}
            disabled={!name.trim() || !description.trim() || aiLoading}>
            ✨ AI 智能填充
          </Button>
          <span className="text-xs text-gray-500">根据名称和功能描述自动生成工具代码（参数定义 + execute 函数）</span>
        </div>

        <div><div className="text-xs text-gray-400 mb-1">名称（英文，如 my_calculator）</div>
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="my-tool" /></div>
        <div><div className="text-xs text-gray-400 mb-1">描述</div>
          <Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="简要描述 Tool 的功能（如：调用外部 API 获取天气数据）" /></div>
        {aiWarning && (
          <div className="text-xs text-amber-400 bg-amber-900/20 border border-amber-500/30 rounded p-2">
            ⚠️ {aiWarning}
          </div>
        )}

        {!advanced && (
          <div>
            <div className="flex items-center justify-between mb-1">
              <div className="text-xs text-gray-400">输入参数</div>
              <button onClick={addParam} className="text-xs text-primary hover:underline">+ 添加参数</button>
            </div>
            <div className="space-y-1">
              {params.map((p, i) => (
                <div key={i} className="flex gap-1">
                  <input className="flex-1 px-2 py-1 bg-dark-hover border border-dark-border rounded text-xs text-gray-200 placeholder-gray-500" placeholder="key"
                    value={p.key} onChange={(e) => updateParam(i, 'key', e.target.value)} />
                  <select className="w-20 px-1 py-1 bg-dark-hover border border-dark-border rounded text-xs text-gray-200"
                    value={p.type} onChange={(e) => updateParam(i, 'type', e.target.value)}>
                    <option value="string">string</option>
                    <option value="integer">integer</option>
                    <option value="number">number</option>
                    <option value="boolean">boolean</option>
                    <option value="object">object</option>
                  </select>
                  <input className="flex-[2] px-2 py-1 bg-dark-hover border border-dark-border rounded text-xs text-gray-200 placeholder-gray-500" placeholder="描述"
                    value={p.desc} onChange={(e) => updateParam(i, 'desc', e.target.value)} />
                  <button onClick={() => removeParam(i)} className="px-2 text-xs text-red-400 hover:text-red-300">✕</button>
                </div>
              ))}
            </div>
          </div>
        )}

        {advanced ? (
          <div>
            <div className="text-xs text-gray-400 mb-1">Python 代码</div>
            <textarea className="w-full h-52 px-3 py-2 bg-dark-hover border border-dark-border rounded text-xs text-gray-200 placeholder-gray-500 font-mono resize-none"
              placeholder={`TOOL_DEF = {\n  "id": "my_tool",\n  "name": "my_tool",\n  "description": "...",\n  "parameters": {"type": "object", "properties": {}},\n  "execute": lambda params: {"result": "ok"}\n}`}
              value={code} onChange={(e) => setCode(e.target.value)} />
          </div>
        ) : (
          <div>
            <div className="text-xs text-gray-400 mb-1">生成预览</div>
            <pre className="text-xs text-gray-300 bg-dark-hover border border-dark-border rounded p-2 overflow-auto max-h-48 font-mono">
              {generatedCode}
            </pre>
          </div>
        )}
      </div>
    </Modal>
  );
};

export default AddToolModal;
