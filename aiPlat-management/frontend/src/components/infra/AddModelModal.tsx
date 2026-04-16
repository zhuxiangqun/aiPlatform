import React, { useEffect, useMemo, useState } from 'react';

import { modelApi, type Provider } from '../../services';
import { Alert, Button, Input, Modal, Select, Textarea, toast } from '../ui';

interface AddModelModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
  providers: Provider[];
}

const AddModelModal: React.FC<AddModelModalProps> = ({ open, onClose, onSuccess, providers }) => {
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
    () => providers.map((p) => ({ value: p.id, label: `${p.name}${p.requiresApiKey ? ' (需要 API Key)' : ''}` })),
    [providers]
  );
  const selectedProviderInfo = useMemo(() => providers.find((p) => p.id === provider), [providers, provider]);

  useEffect(() => {
    if (!open) return;
    setTestResult(null);
    setProvider('');
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
  }, [open]);

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
    if (selectedProviderInfo?.requiresApiKey && !apiKeyEnv.trim()) return toast.error('该 Provider 需要 apiKeyEnv');

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

      await modelApi.add(modelData as any);
      toast.success('模型添加成功');
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
      title="添加模型"
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
            {selectedProviderInfo.requiresApiKey ? '该 Provider 需要配置 API Key 环境变量（apiKeyEnv）' : '该 Provider 不需要 API Key'}
          </Alert>
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
