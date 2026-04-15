import React, { useState } from 'react';
import { Modal, Button } from '../ui';
import { memoryApi, type MemorySessionDetail } from '../../services';

interface SessionDetailModalProps {
  open: boolean;
  session: MemorySessionDetail | null;
  onClose: () => void;
}

const SessionDetailModal: React.FC<SessionDetailModalProps> = ({ open, session, onClose }) => {
  const [messageInput, setMessageInput] = useState('');
  const [currentSession, setCurrentSession] = useState<MemorySessionDetail | null>(session);

  React.useEffect(() => {
    setCurrentSession(session);
    setMessageInput('');
  }, [session]);

  const handleAddMessage = async () => {
    if (!currentSession?.session_id || !messageInput.trim()) return;
    try {
      await memoryApi.addMessage(currentSession.session_id, {
        role: 'user',
        content: messageInput,
      });
      const detail = await memoryApi.getSession(currentSession.session_id);
      setCurrentSession(detail);
      setMessageInput('');
      alert('消息已添加');
    } catch {
      alert('添加失败');
    }
  };

  return (
    <Modal
      open={open}
      onClose={() => { onClose(); setCurrentSession(null); }}
      title={`会话详情: ${currentSession?.session_id?.slice(0, 16) || ''}...`}
      width={700}
      footer={<Button onClick={() => { onClose(); setCurrentSession(null); }}>关闭</Button>}
    >
      {currentSession && (
        <div>
          <div className="mb-4 max-h-80 overflow-y-auto bg-dark-bg p-4 rounded-xl space-y-2">
            {(currentSession.messages || []).map((msg, idx) => (
              <div key={idx} className="flex items-start gap-2">
                <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${
                  msg.role === 'user' ? 'bg-primary-light text-blue-300' : 'bg-success-light text-green-300'
                }`}>
                  {msg.role}
                </span>
                <span className="text-sm text-gray-300 flex-1">{msg.content}</span>
              </div>
            ))}
            {(!currentSession.messages || currentSession.messages.length === 0) && (
              <div className="text-center text-gray-400 py-4">暂无消息</div>
            )}
          </div>
          <div className="flex gap-2">
            <input
              type="text"
              value={messageInput}
              onChange={e => setMessageInput(e.target.value)}
              placeholder="输入消息..."
              className="flex-1 h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm"
              onKeyDown={e => e.key === 'Enter' && handleAddMessage()}
            />
            <Button variant="primary" onClick={handleAddMessage}>发送</Button>
          </div>
        </div>
      )}
    </Modal>
  );
};

export default SessionDetailModal;
