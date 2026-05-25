import React, { useEffect, useMemo, useState } from 'react';

import { modelApi, type Provider, type Model } from '../../services';
import { Alert, Button, Input, Modal, Select, Textarea, toast } from '../ui';

interface AddModelModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
  providers: Provider[];
  editingModel?: Model | null;
}

const AddModelModal: React.FC<AddModelModalProps> = ({ open, onClose, onSuccess, providers, editingModel }) => {
  const [loading, setLoading] = useState(false);
  const [testLoading, setTestLoading] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);

  const [provider, setProvider] = useState('');
  const [name, setName] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [type, setType] = useState<'chat' | 'embedding' | 'rerank'>('chat');
  const [description, setDescription] = useState('');
  const [tags, setTags] = useState('');

  const [baseUrl, setBaseUrl] = useState('');
  const [apiKeyEnv, setApiKeyEnv] = useState('');
  const [temperature, setTemperature] = useState('0.7');
  const [maxTokens, setMaxTokens] = useState('2048');
  const [topP, setTopP] = useState('1.0');

  const providerOptions = useMemo(
    () => providers.map((p) => ({ value: p.id, label: `${p.name}${p.requires_api_key ? ' (需要 API Key)' : ''}` })),
    [providers]
  );
  const selectedProviderInfo = useMemo(() => providers.find((p) => p.id === provider), [providers, provider]);

  // Provider-level base config
  const PROVIDER_BASE: Record<string, { baseUrl: string; apiKeyEnv: string }> = {
    deepseek: { baseUrl: 'https://api.deepseek.com/v1', apiKeyEnv: 'AIPLAT_LLM_API_KEY' },
    openai: { baseUrl: 'https://api.openai.com/v1', apiKeyEnv: 'OPENAI_API_KEY' },
    anthropic: { baseUrl: 'https://api.anthropic.com/v1', apiKeyEnv: 'ANTHROPIC_API_KEY' },
    local: { baseUrl: 'http://localhost:11434/v1', apiKeyEnv: '' },
  };

  // Dynamic model catalog from backend
  const [providerModels, setProviderModels] = useState<Record<string, Array<{
    name: string; display: string; type: string; temperature: number; max_tokens: number; top_p: number;
  }>>>({});
  const modelsForProvider = providerModels[provider] || [];
  const modelOptions = modelsForProvider.map((m) => ({ value: m.name, label: m.display }));
  const [selectedModel, setSelectedModel] = useState('');

  const _initialized = useMemo(() => Object.keys(providerModels).length > 0, [providerModels]);

  // Load dynamic model catalog from backend
  useEffect(() => {
    modelApi.getProviderModels().then((data) => {
      if (data.providers) setProviderModels(data.providers);
    }).catch(() => {});
  }, []);

  // Initialize form on open (editing → pre-fill, new → reset)
  useEffect(() => {
    if (!open || !_initialized) return;
    if (editingModel) {
      const catalogModels = providerModels[editingModel.provider || ''] || [];
      const catalog = catalogModels.find((m) => m.name === editingModel.name);
      setProvider(editingModel.provider || '');
      setSelectedModel(catalog ? catalog.name : (editingModel.name || ''));
      setName(catalog ? catalog.name : (editingModel.name || ''));
      setDisplayName(catalog ? catalog.display : (editingModel.displayName || ''));
      setType((catalog ? catalog.type : (editingModel.type || 'chat')) as 'chat' | 'embedding' | 'rerank');
      setDescription(editingModel.description || '');
      setTags((editingModel.tags || []).join(', '));
      setBaseUrl(editingModel.config?.baseUrl || PROVIDER_BASE[editingModel.provider || '']?.baseUrl || '');
      setApiKeyEnv(editingModel.config?.apiKeyEnv || PROVIDER_BASE[editingModel.provider || '']?.apiKeyEnv || '');
      setTemperature(String(catalog?.temperature ?? editingModel.config?.temperature ?? 0.7));
      setMaxTokens(String(catalog?.max_tokens ?? editingModel.config?.maxTokens ?? 2048));
      setTopP(String(catalog?.top_p ?? editingModel.config?.topP ?? 1.0));
      setTestResult(null);
      return;
    }
    setTestResult(null);
    setProvider('');
    setSelectedModel('');
    setName('');
    setDisplayName('');
    setType('chat');
    setDescription('');
    setTags('');
    setBaseUrl('');
    setApiKeyEnv('');
    setTemperature('0.7');
    setMaxTokens('2048');
    setTopP('1.0');
  }, [open, _initialized, editingModel]);

  useEffect(() => {
    if (!provider) return;
    const base = PROVIDER_BASE[provider];
    if (base) {
      setBaseUrl(base.baseUrl);
      setApiKeyEnv(base.apiKeyEnv);
    }
    const models = modelsForProvider;
    if (models.length > 0 && !selectedModel) {
      setSelectedModel(models[0].name);
    }
  }, [provider, modelsForProvider]);

  useEffect(() => {
    const model = modelsForProvider.find((m) => m.name === selectedModel);
    if (!model) return;
    setName(model.name);
    setDisplayName(model.display);
    setType((model.type || 'chat') as 'chat' | 'embedding' | 'rerank');
    setTemperature(String(model.temperature ?? 0.7));
    setMaxTokens(String(model.max_tokens ?? 2048));
    setTopP(String(model.top_p ?? 1.0));
  }, [selectedModel, modelsForProvider]);

  const handleTestConnectivity = async () => {
    if (!baseUrl.trim()) return toast.warning('请输入 baseUrl');
    setTestLoading(true);
    setTestResult(null);
    try {
      const url = new URL(baseUrl.trim());
      setTestResult({ success: true, message: `端点 ${url.host} 格式正确` });
      toast.success('端点格式正确');
    } catch {
      setTestResult({ success: false, message: '无效的 URL 格式' });
      toast.error('请输入有效的 URL');
    } finally {
      setTestLoading(false);
    }
  };

  const handleSubmit = async () => {
    if (!provider) return toast.error('请选择 Provider');
    if (!name.trim()) return toast.error('请输入模型 name');
    if (!displayName.trim()) return toast.error('请输入模型 displayName');
    if (!baseUrl.trim()) return toast.error('请输入 baseUrl');
    if (selectedProviderInfo?.requires_api_key && !apiKeyEnv.trim()) return toast.error('该 Provider 需要 apiKeyEnv');

    setLoading(true);
    try {
      const modelData = {
        name: name.trim(),
        displayName: displayName.trim(),
        type,
        provider,
        description,
        tags: tags
          .split(',')
          .map((t) => t.trim())
          .filter(Boolean),
        config: {
          baseUrl: baseUrl.trim(),
          apiKeyEnv: apiKeyEnv.trim(),
          temperature: Number(temperature),
          maxTokens: Number(maxTokens),
          topP: Number(topP),
        },
      };

      await (editingModel
        ? modelApi.update(editingModel.id, modelData as any)
        : modelApi.add(modelData as any));
      toast.success(editingModel ? '模型已更新' : '模型添加成功');
      onSuccess();
      onClose();
    } catch (e: any) {
      toast.error(e?.message || '添加失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={editingModel ? '编辑模型' : '添加模型'}
      width={760}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={loading}>取消</Button>
          <Button variant="primary" onClick={handleSubmit} loading={loading}>保存</Button>
        </>
      }
    >
      <div className="space-y-4">
        <Select label="Provider" value={provider} onChange={setProvider} options={providerOptions} placeholder="选择 Provider" />

        {selectedProviderInfo && (
          <Alert type="info" title={selectedProviderInfo.name}>
            {selectedProviderInfo.requires_api_key ? '该 Provider 需要配置 API Key 环境变量（apiKeyEnv）' : '该 Provider 不需要 API Key'}
          </Alert>
        )}

        {Object.keys(providerModels).length > 0 && (
          <Select label="选择模型" value={selectedModel} onChange={setSelectedModel} options={modelOptions} placeholder="选择模型" />
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Input label="name" value={name} onChange={(e: any) => setName(e.target.value)} placeholder="例如: gpt-4o-mini" />
          <Input label="displayName" value={displayName} onChange={(e: any) => setDisplayName(e.target.value)} placeholder="例如: GPT-4o Mini" />
        </div>

        <Select
          label="type"
          value={type}
          onChange={(v) => setType(v as any)}
          options={[
            { value: 'chat', label: 'chat' },
            { value: 'embedding', label: 'embedding' },
            { value: 'rerank', label: 'rerank' },
          ]}
        />

        <Textarea label="description" rows={3} value={description} onChange={(e: any) => setDescription(e.target.value)} />
        <Input label="tags（逗号分隔）" value={tags} onChange={(e: any) => setTags(e.target.value)} placeholder="tag1,tag2" />

        <div className="border-t border-dark-border pt-4">
          <div className="text-sm font-semibold text-gray-200 mb-3">连接配置</div>
          <Input label="baseUrl" value={baseUrl} onChange={(e: any) => setBaseUrl(e.target.value)} placeholder="https://api.openai.com/v1" />
          <div className="flex items-center gap-2 mt-2">
            <Button variant="secondary" onClick={handleTestConnectivity} loading={testLoading}>测试 baseUrl</Button>
            {testResult && (
              <div className={`text-sm ${testResult.success ? 'text-green-400' : 'text-red-400'}`}>{testResult.message}</div>
            )}
          </div>

          <Input
            label="apiKeyEnv"
            value={apiKeyEnv}
            onChange={(e: any) => setApiKeyEnv(e.target.value)}
            placeholder="例如: OPENAI_API_KEY"
          />

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Input label="temperature" type="number" value={temperature} onChange={(e: any) => setTemperature(e.target.value)} />
            <Input label="maxTokens" type="number" value={maxTokens} onChange={(e: any) => setMaxTokens(e.target.value)} />
            <Input label="topP" type="number" value={topP} onChange={(e: any) => setTopP(e.target.value)} />
          </div>
        </div>
      </div>
    </Modal>
  );
};

export default AddModelModal;
