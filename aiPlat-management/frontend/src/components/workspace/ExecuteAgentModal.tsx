import React, { useState } from 'react';
import { workspaceAgentApi } from '../../services/coreApi';
import type { Agent } from '../../services';
import { Button, Modal, Textarea, notify, toast } from '../ui';

interface ExecuteAgentModalProps {
  open: boolean;
  agent: Agent | null;
  onClose: () => void;
}

const ExecuteAgentModal: React.FC<ExecuteAgentModalProps> = ({ open, agent, onClose }) => {
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);

  const handleExecute = async () => {
    if (!agent) return;
    let parsedInput: Record<string, unknown> = {};
    if (input.trim()) {
      try {
        parsedInput = JSON.parse(input);
      } catch {
        parsedInput = { message: input };
      }
    }
    setLoading(true);
    try {
      const result = await workspaceAgentApi.execute(agent.id, { input: parsedInput });
      toast.success('执行完成', String((result as any)?.status || 'ok'));
      if ((result as any)?.execution_id) {
        notify.success(
          `Agent 执行完成：${agent.name}`,
          `execution_id: ${(result as any).execution_id}`,
          `/diagnostics/links?execution_id=${encodeURIComponent(String((result as any).execution_id))}`
        );
      }
      onClose();
      setInput('');
    } catch {
      toast.error('执行失败');
      notify.error(`Agent 执行失败：${agent.name}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={() => { onClose(); setInput(''); }}
      title={`执行 Agent: ${agent?.name || ''}`}
      width={640}
      footer={
        <>
          <Button variant="secondary" onClick={() => { onClose(); setInput(''); }} disabled={loading}>取消</Button>
          <Button variant="primary" onClick={handleExecute} loading={loading}>执行</Button>
        </>
      }
    >
      <Textarea
        label="输入（JSON 或文本）"
        rows={8}
        value={input}
        onChange={(e: any) => setInput(e.target.value)}
        placeholder="输入 JSON 或文本"
      />
    </Modal>
  );
};

export default ExecuteAgentModal;
