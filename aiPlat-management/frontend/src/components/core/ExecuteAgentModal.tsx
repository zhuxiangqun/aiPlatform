import React, { useState } from 'react';
import { Modal, Input, message } from 'antd';
import { agentApi, type Agent } from '../../services';

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
      const result = await agentApi.execute(agent.id, { input: parsedInput });
      message.success(`执行完成: ${result.status}`);
      onClose();
      setInput('');
    } catch (error) {
      message.error('执行失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      title={`执行Agent: ${agent?.name || ''}`}
      open={open}
      onOk={handleExecute}
      onCancel={() => { onClose(); setInput(''); }}
      okText="执行"
      cancelText="取消"
      confirmLoading={loading}
      destroyOnHidden
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div>
          <label>输入 (JSON或文本)</label>
          <Input.TextArea
            rows={6}
            value={input}
            onChange={e => setInput(e.target.value)}
            placeholder='输入JSON或文本'
          />
        </div>
      </div>
    </Modal>
  );
};

export default ExecuteAgentModal;