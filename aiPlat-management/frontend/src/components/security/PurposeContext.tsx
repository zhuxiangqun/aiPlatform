/**
 * PurposeContext — 操作目的选择器 (Palantir Security 3D 对齐)
 *
 * 在用户执行敏感操作前，选择数据使用目的:
 *   - general: 通用操作 (默认，无限制)
 *   - diagnosis: 诊断分析 (只读工具)
 *   - deployment: 部署发布 (需审批)
 *   - knowledge_gen: 知识生产 (读写工具)
 *   - audit_review: 审计审查 (只读+高标记访问)
 *   - training: 培训沙盒 (限制标记级别)
 *
 * 选定 Purpose 后自动收敛可用工具集和可访问数据范围.
 */
import React, { useState, useEffect } from 'react';
import { Button, toast } from '../../components/ui';
import {
  Shield, CheckCircle, Brain, Rocket, BookOpen, Eye, GraduationCap, ChevronDown,
} from 'lucide-react';

const API_BASE = '/api/platform/apps/fde';

// ── Types ────────────────────────────────────────────────────────────────

interface PurposeInfo {
  purpose_id: string;
  label: string;
  description: string;
  tool_whitelist: string[];
  action_whitelist: string[];
  max_marking_level: number;
  require_approval: boolean;
  allowed_roles: string[];
}

const PURPOSE_ICONS: Record<string, React.FC<any>> = {
  general: Shield,
  diagnosis: Eye,
  deployment: Rocket,
  knowledge_gen: Brain,
  audit_review: BookOpen,
  training: GraduationCap,
};

const PURPOSE_COLORS: Record<string, string> = {
  general: 'text-gray-400',
  diagnosis: 'text-blue-400',
  deployment: 'text-orange-400',
  knowledge_gen: 'text-green-400',
  audit_review: 'text-purple-400',
  training: 'text-yellow-400',
};

const MARKING_LABELS: Record<number, string> = {
  1: 'PUBLIC',
  2: 'INTERNAL',
  3: 'CONFIDENTIAL',
  4: 'RESTRICTED',
};

// ── Component ─────────────────────────────────────────────────────────────

interface Props {
  currentPurpose?: string;
  onPurposeChange?: (purposeId: string) => void;
}

const PurposeContext: React.FC<Props> = ({ currentPurpose = 'general', onPurposeChange }) => {
  const [purposes, setPurposes] = useState<PurposeInfo[]>([]);
  const [selected, setSelected] = useState(currentPurpose);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    fetch(`${API_BASE}/security/purposes`)
      .then(r => r.json())
      .then(d => setPurposes(d.purposes || []))
      .catch(() => {});
  }, []);

  const handleSelect = (purposeId: string) => {
    setSelected(purposeId);
    setOpen(false);
    onPurposeChange?.(purposeId);
    toast?.info?.(`已切换至: ${purposes.find(p => p.purpose_id === purposeId)?.label || purposeId}`);
  };

  const currentInfo = purposes.find(p => p.purpose_id === selected);

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-[10px] bg-gray-800/50 border border-gray-700 rounded px-2 py-1 text-gray-400 hover:text-gray-200 hover:border-gray-500 transition-colors"
        title={`当前目的: ${currentInfo?.label || selected}`}
      >
        <Shield className="w-3 h-3" />
        <span className={PURPOSE_COLORS[selected] || ''}>
          {currentInfo?.label || selected}
        </span>
        <ChevronDown className="w-3 h-3" />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-full mt-1 w-72 bg-gray-900 border border-gray-700 rounded-lg shadow-xl z-50 p-1">
            <div className="text-[10px] text-gray-600 px-2 py-1">
              选择数据使用目的 (Purpose) — 影响可用工具和数据范围
            </div>
            {purposes.map(p => {
              const Icon = PURPOSE_ICONS[p.purpose_id] || Shield;
              const isActive = selected === p.purpose_id;
              return (
                <button
                  key={p.purpose_id}
                  onClick={() => handleSelect(p.purpose_id)}
                  className={`w-full text-left p-2 rounded transition-colors ${
                    isActive ? 'bg-blue-500/10 border border-blue-500/20' : 'hover:bg-gray-800/50'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <Icon className={`w-3.5 h-3.5 ${PURPOSE_COLORS[p.purpose_id] || ''}`} />
                    <div>
                      <div className="flex items-center gap-1.5">
                        <span className="text-xs text-gray-200 font-medium">{p.label}</span>
                        {isActive && <CheckCircle className="w-3 h-3 text-blue-400" />}
                        {p.require_approval && (
                          <span className="text-[9px] bg-orange-500/10 text-orange-400 px-1 rounded">需审批</span>
                        )}
                      </div>
                      <div className="text-[10px] text-gray-500">{p.description}</div>
                    </div>
                  </div>
                  <div className="flex gap-2 mt-1 ml-5 text-[9px] text-gray-600">
                    <span>工具: {p.tool_whitelist.length > 0 ? p.tool_whitelist.length : '全部'}</span>
                    <span>标记: ≤ {MARKING_LABELS[p.max_marking_level] || p.max_marking_level}</span>
                    {p.allowed_roles.length > 0 && (
                      <span>角色: {p.allowed_roles.join(', ')}</span>
                    )}
                  </div>
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
};

export default PurposeContext;
