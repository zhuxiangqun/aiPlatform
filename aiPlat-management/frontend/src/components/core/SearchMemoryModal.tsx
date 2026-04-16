import React, { useState } from 'react';
import { Modal, Button, toast } from '../ui';
import { memoryApi, type MemorySearchResult } from '../../services';

interface SearchMemoryModalProps {
  open: boolean;
  onClose: () => void;
}

const SearchMemoryModal: React.FC<SearchMemoryModalProps> = ({ open, onClose }) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<MemorySearchResult[]>([]);
  const [loading, setLoading] = useState(false);

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setLoading(true);
    try {
      const res = await memoryApi.search(searchQuery);
      setSearchResults(res.results || []);
    } catch {
      toast.error('搜索失败');
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    onClose();
    setSearchResults([]);
    setSearchQuery('');
  };

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title="搜索记忆"
      width={600}
      footer={
        <Button onClick={handleClose}>关闭</Button>
      }
    >
      <div className="mb-4">
        <div className="flex gap-2">
          <input
            type="text"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            placeholder="搜索关键词..."
            className="flex-1 h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm"
            onKeyDown={e => e.key === 'Enter' && handleSearch()}
          />
          <Button variant="primary" onClick={handleSearch} loading={loading}>
            搜索
          </Button>
        </div>
      </div>
      {searchResults.length > 0 ? (
        <div className="max-h-80 overflow-y-auto space-y-3">
          {searchResults.map((r, idx) => (
            <div key={idx} className="p-4 bg-dark-bg rounded-lg">
              <span className="inline-flex px-2 py-0.5 rounded-full text-xs font-medium bg-primary-light text-blue-300 mb-2">
                {r.role}
              </span>
              <div className="text-sm text-gray-300">{r.content?.slice(0, 200)}</div>
              <div className="text-xs text-gray-400 mt-2">会话: {r.session_id}</div>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-center py-8 text-gray-400">输入关键词搜索记忆</div>
      )}
    </Modal>
  );
};

export default SearchMemoryModal;
