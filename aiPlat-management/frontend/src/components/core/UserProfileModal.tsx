import React, { useEffect, useState } from 'react';
import { Modal, Button, Switch, toast } from '../ui';
import { memoryApi } from '../../services';

interface UserProfileModalProps {
  open: boolean;
  onClose: () => void;
}

const UserProfileModal: React.FC<UserProfileModalProps> = ({ open, onClose }) => {
  const [loading, setLoading] = useState(false);
  const [ignoreGreetings, setIgnoreGreetings] = useState(true);
  const [captureErrors, setCaptureErrors] = useState(true);
  const [ignorePatterns, setIgnorePatterns] = useState<string>('');
  const [capturePatterns, setCapturePatterns] = useState<string>('');

  useEffect(() => {
    if (!open) return;
    loadRules();
  }, [open]);

  const loadRules = async () => {
    try {
      const res = await memoryApi.getRules();
      setIgnoreGreetings(res.ignore_greetings ?? true);
      setCaptureErrors(res.capture_errors ?? true);
      setIgnorePatterns((res.ignore_patterns || []).join(', '));
      setCapturePatterns((res.capture_patterns || []).join(', '));
    } catch (e: any) {
      toast.error('加载规则失败', String(e?.message || ''));
    }
  };

  const saveRules = async () => {
    setLoading(true);
    try {
      await memoryApi.updateRules({
        ignore_greetings: ignoreGreetings,
        capture_errors: captureErrors,
        ignore_patterns: ignorePatterns.split(',').map((s: string) => s.trim()).filter(Boolean),
        capture_patterns: capturePatterns.split(',').map((s: string) => s.trim()).filter(Boolean),
      });
      toast.success('记忆规则已保存');
    } catch (e: any) {
      toast.error('保存失败', String(e?.message || ''));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="记忆规则"
      width={520}
      footer={
        <div className="flex gap-2">
          <Button onClick={onClose}>取消</Button>
          <Button variant="primary" onClick={saveRules} loading={loading}>保存</Button>
        </div>
      }
    >
      <div className="space-y-4 text-sm">
        <div className="text-xs text-gray-500 mb-2">
          配置记忆系统的元认知规则——哪些对话值得记住，哪些应该忽略。
        </div>

        <div className="flex items-center justify-between bg-dark-card rounded-lg p-3 border border-dark-border">
          <div>
            <div className="text-gray-200 font-medium">忽略寒暄</div>
            <div className="text-xs text-gray-500">不将 "你好/谢谢/再见" 等无信息量对话写入长期记忆</div>
          </div>
          <Switch checked={ignoreGreetings} onChange={(v: boolean) => setIgnoreGreetings(v)} />
        </div>

        <div className="flex items-center justify-between bg-dark-card rounded-lg p-3 border border-dark-border">
          <div>
            <div className="text-gray-200 font-medium">必记报错</div>
            <div className="text-xs text-gray-500">所有包含 error/failed/exception 的对话强制写入记忆</div>
          </div>
          <Switch checked={captureErrors} onChange={(v: boolean) => setCaptureErrors(v)} />
        </div>

        <div className="bg-dark-card rounded-lg p-3 border border-dark-border space-y-1">
          <div className="text-gray-200 font-medium">忽略模式（逗号分隔）</div>
          <div className="text-xs text-gray-500">匹配这些关键词/模式的对话不会写入长期记忆</div>
          <input
            type="text"
            value={ignorePatterns}
            onChange={(e) => setIgnorePatterns(e.target.value)}
            placeholder="hello, hi, thanks, ok"
            className="w-full h-9 px-3 bg-dark-hover border border-dark-border rounded-lg text-sm mt-1"
          />
        </div>

        <div className="bg-dark-card rounded-lg p-3 border border-dark-border space-y-1">
          <div className="text-gray-200 font-medium">捕获模式（逗号分隔）</div>
          <div className="text-xs text-gray-500">匹配这些模式的对话强制写入长期记忆</div>
          <input
            type="text"
            value={capturePatterns}
            onChange={(e) => setCapturePatterns(e.target.value)}
            placeholder="error, failed, timeout, exception, database"
            className="w-full h-9 px-3 bg-dark-hover border border-dark-border rounded-lg text-sm mt-1"
          />
        </div>
      </div>
    </Modal>
  );
};

export default UserProfileModal;
