import React, { useEffect, useState } from 'react';
import { toolApi } from '../../services';
import { Button, Input, Modal, toast } from '../ui';

interface EditToolConfigModalProps {
  open: boolean;
  tool: { name: string; config?: Record<string, unknown> } | null;
  onClose: () => void;
  onSuccess: () => void;
}

const EditToolConfigModal: React.FC<EditToolConfigModalProps> = ({ open, tool, onClose, onSuccess }) => {
  const [loading, setLoading] = useState(false);
  const [fetching, setFetching] = useState(false);
  const [timeoutSeconds, setTimeoutSeconds] = useState<string>('');
  const [maxConcurrent, setMaxConcurrent] = useState<string>('');

  useEffect(() => {
    if (open && tool) {
      setFetching(true);
      toolApi.get(tool.name).then((detail) => {
        const data = detail as any;
        const cfg = data.config || {};
        setTimeoutSeconds(cfg.timeout_seconds != null ? String(cfg.timeout_seconds) : '');
        setMaxConcurrent(cfg.max_concurrent != null ? String(cfg.max_concurrent) : '');
      }).catch(() => {
        const cfg = tool.config || {};
        setTimeoutSeconds(cfg.timeout_seconds != null ? String(cfg.timeout_seconds) : '');
        setMaxConcurrent(cfg.max_concurrent != null ? String(cfg.max_concurrent) : '');
      }).finally(() => {
        setFetching(false);
      });
    }
  }, [open, tool]);

  const handleSubmit = async () => {
    if (!tool) return;
    try {
      setLoading(true);

      const config: Record<string, unknown> = {};
      if (timeoutSeconds.trim()) config.timeout_seconds = Number(timeoutSeconds);
      if (maxConcurrent.trim()) config.max_concurrent = Number(maxConcurrent);

      await toolApi.updateConfig(tool.name, config);
      toast.success(`Tool "${tool.name}" 配置更新成功`);
      onSuccess();
      onClose();
    } catch (error: any) {
      if (error.message) {
        toast.error('更新失败', String(error.message || ''));
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`编辑配置: ${tool?.name || ''}`}
      width={520}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={loading}>
            取消
          </Button>
          <Button variant="primary" onClick={handleSubmit} loading={loading} disabled={fetching}>
            保存
          </Button>
        </>
      }
    >
      {fetching ? (
        <div className="text-sm text-gray-500">加载中...</div>
      ) : (
        <div className="space-y-4">
          <Input
            label="超时时间（秒）"
            placeholder="默认 60"
            type="number"
            min={1}
            max={600}
            value={timeoutSeconds}
            onChange={(e: any) => setTimeoutSeconds(e.target.value)}
          />
          <Input
            label="最大并发数"
            placeholder="默认 10"
            type="number"
            min={1}
            max={100}
            value={maxConcurrent}
            onChange={(e: any) => setMaxConcurrent(e.target.value)}
          />
          <div className="text-xs text-gray-500">
            timeout_seconds：Tool 执行最大等待时间；max_concurrent：同时执行的最大任务数
          </div>
        </div>
      )}
    </Modal>
  );
};

export default EditToolConfigModal;
