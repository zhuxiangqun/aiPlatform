import React, { useState } from 'react';
import { Modal, Button } from '../ui';
import { skillApi } from '../../services';

interface SkillDetailModalProps {
  open: boolean;
  skillId: string | null;
  onClose: () => void;
}

const SkillDetailModal: React.FC<SkillDetailModalProps> = ({ open, skillId, onClose }) => {
  const [detail, setDetail] = useState<any>(null);
  const [sop, setSop] = useState<string | null>(null);
  const [sopLoading, setSopLoading] = useState(false);
  const [loading, setLoading] = useState(false);

  React.useEffect(() => {
    if (open && skillId) {
      setLoading(true);
      skillApi.get(skillId).then((res: any) => setDetail(res)).catch(() => setDetail(null)).finally(() => setLoading(false));
      setSop(null);
    } else { setDetail(null); setSop(null); }
  }, [open, skillId]);

  const loadSop = () => {
    if (!skillId) return;
    setSopLoading(true);
    skillApi.getSop(skillId).then((r: any) => setSop(r?.sop || '(无 SOP 内容)')).catch(() => setSop('(加载失败)')).finally(() => setSopLoading(false));
  };

  if (!skillId) return null;
  const meta = detail?.metadata || {};
  const displayName = detail?.name || meta?.display_name || skillId;
  const desc = detail?.description || meta?.description || '';

  return (
    <Modal open={open} onClose={() => { onClose(); setSop(null); }} title={displayName} width={700} footer={<Button onClick={onClose}>关闭</Button>}>
      {loading ? (
        <div className="flex items-center justify-center py-8"><div className="text-gray-400">加载中...</div></div>
      ) : (
        <div className="space-y-5">
          {desc && <div className="text-sm text-gray-300 leading-relaxed">{desc}</div>}

          <div className="grid grid-cols-3 gap-4">
            <div className="p-3 rounded-lg bg-dark-bg border border-dark-border">
              <div className="text-xs text-gray-400 mb-1">ID</div>
              <div className="text-sm text-gray-100 font-mono">{skillId}</div>
            </div>
            <div className="p-3 rounded-lg bg-dark-bg border border-dark-border">
              <div className="text-xs text-gray-400 mb-1">分类</div>
              <div className="text-sm text-gray-100">{detail?.category || meta?.category || '-'}</div>
            </div>
            <div className="p-3 rounded-lg bg-dark-bg border border-dark-border">
              <div className="text-xs text-gray-400 mb-1">状态</div>
              <div className={`text-sm font-medium ${detail?.enabled !== false ? 'text-green-300' : 'text-gray-500'}`}>{detail?.enabled !== false ? '已启用' : '已禁用'}</div>
            </div>
          </div>

          {detail?.input_schema && Object.keys(detail.input_schema).length > 0 && (
            <div>
              <div className="text-sm text-gray-400 mb-1 font-medium">输入参数</div>
              <div className="flex flex-wrap gap-2">
                {Object.entries(detail.input_schema as Record<string, any>).map(([k, v]) => (
                  <span key={k} className="text-xs px-2 py-0.5 rounded bg-dark-bg border border-dark-border">
                    <span className="text-gray-200">{k}</span>
                    <span className="text-gray-500 ml-1">({v.type || 'string'}{v.required ? ', 必填' : ''})</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="text-sm text-gray-400 font-medium">SKILL.md</div>
              {sop === null ? (
                <button onClick={loadSop} disabled={sopLoading} className="text-xs text-blue-400 hover:text-blue-300 disabled:text-gray-600">
                  {sopLoading ? '加载中...' : '查看内容'}
                </button>
              ) : (
                <button onClick={() => setSop(null)} className="text-xs text-gray-500 hover:text-gray-400">收起</button>
              )}
            </div>
            {sop !== null && (
              <pre className="bg-dark-bg border border-dark-border rounded-lg p-3 text-xs text-gray-300 overflow-auto whitespace-pre-wrap" style={{ maxHeight: 400 }}>
                {sop}
              </pre>
            )}
          </div>
        </div>
      )}
    </Modal>
  );
};

export default SkillDetailModal;
