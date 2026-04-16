import React, { useState } from 'react';
import { Modal, Button, Input, toast } from '../ui';
import { memoryApi } from '../../services';

interface CreateSessionModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

const CreateSessionModal: React.FC<CreateSessionModalProps> = ({ open, onClose, onSuccess }) => {
  const [sessionId, setSessionId] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    try {
      setLoading(true);
      await memoryApi.createSession({
        session_id: sessionId || undefined,
        metadata: {},
      });
      toast.success('会话创建成功');
      onSuccess();
      onClose();
      setSessionId('');
    } catch {
      toast.error('创建失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={() => { onClose(); setSessionId(''); }}
      title="创建会话"
      footer={
        <>
          <Button onClick={() => { onClose(); setSessionId(''); }}>取消</Button>
          <Button variant="primary" onClick={handleSubmit} loading={loading}>创建</Button>
        </>
      }
    >
      <div className="space-y-4">
        <Input
          label="会话ID（可选，留空自动生成）"
          placeholder="自定义会话ID"
          value={sessionId}
          onChange={e => setSessionId(e.target.value)}
        />
      </div>
    </Modal>
  );
};

export default CreateSessionModal;
