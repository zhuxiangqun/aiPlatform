import React from 'react';
import { Link } from 'react-router-dom';

type AssetKind = 'agent' | 'skill' | 'mcp';

const APPROVAL_QS: Record<AssetKind, string> = {
  agent: 'type=agent&status=ready',
  skill: 'type=skill&status=ready',
  mcp: 'type=mcp&status=ready',
};

/** Always-visible 上架 / 治理 legend for workspace asset lists. */
export const AssetStatusLegend: React.FC<{
  kind: AssetKind;
  /** Skill 等有 autosmoke「评测中」轨；Agent/MCP 列表目前主要是签名轨 */
  showSmokeTrack?: boolean;
  /** Agent 行内操作文案等 */
  howToSubmit?: string;
  extraNote?: string;
}> = ({
  kind,
  showSmokeTrack = false,
  howToSubmit = '更多 → 提交审批',
  extraNote,
}) => {
  const qs = APPROVAL_QS[kind];
  return (
    <div className="rounded-xl border border-dark-border bg-dark-card px-4 py-3 text-xs space-y-2">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="text-gray-200 font-medium shrink-0">上架状态</span>
        <span className="text-gray-500">有顺序（生命周期，与本机执行无关）：</span>
        <span className="text-gray-400">草稿</span>
        <span className="text-gray-600">→</span>
        <span className="text-amber-400">待审核</span>
        <span className="text-gray-600">→</span>
        <span className="text-blue-400">已发布</span>
        <span className="text-gray-600">→</span>
        <span className="text-green-400">已上架</span>
        <span className="text-gray-600">·</span>
        <span className="text-gray-500">「已启用」≈可用旧状态，可先自测</span>
      </div>

      <div className="space-y-1">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <span className="text-gray-200 font-medium shrink-0">治理</span>
          <span className="text-gray-500">
            {showSmokeTrack
              ? '没有统一顺序 — 两条平行线，徽章只显示优先级高的一条：'
              : '主要是签名轨（≠上架审核）：'}
          </span>
        </div>
        <div className="text-gray-500 space-y-0.5">
          <div>
            <span className="text-gray-300">① 签名</span>
            <span className="ml-2">
              <span className="text-gray-400">未签名</span>
              <span className="text-gray-600"> → </span>
              <span className="text-blue-400">已签名</span>
              <span className="text-gray-500">（私钥签名）</span>
              <span className="text-gray-600"> → </span>
              <span className="text-green-400">已验签</span>
              <span className="text-gray-500">（公钥自动校验）</span>
            </span>
          </div>
          {showSmokeTrack ? (
            <>
              <div>
                <span className="text-gray-300">② 冒烟</span>
                <span className="ml-2">
                  创建/更新后
                  <span className="text-amber-400"> 评测中</span>
                  <span className="text-gray-600"> → </span>
                  <span className="text-green-400">已通过</span>
                  <span className="text-gray-600"> / </span>
                  <span className="text-red-400">未通过</span>
                  <span className="text-gray-500">（autosmoke；卡住多半是任务未跑完）</span>
                </span>
              </div>
              <div className="text-gray-600">
                显示优先级：已验签 &gt; 已签名 &gt; 冒烟结果 &gt; 未签名。签了名后「评测中」可能被盖住。
              </div>
            </>
          ) : (
            <div className="text-gray-600">本地执行一般不强制签名；生产启用可能要求已验签。</div>
          )}
        </div>
      </div>

      <div className="text-gray-500">
        要改上架：{howToSubmit} →
        <Link className="text-amber-300 underline mx-1" to={`/approval?${qs}`}>
          资产审批
        </Link>
        通过 → 已发布；再点上架 → 已上架。治理 ≠ 上架。
        {extraNote ? <span className="ml-1">{extraNote}</span> : null}
      </div>
    </div>
  );
};

export default AssetStatusLegend;
