/**
 * Formal evaluation report document — printable / downloadable Markdown.
 */
import { Download, Printer } from 'lucide-react';
import {
  downloadTextFile,
  fullExamReportToMarkdown,
  type FormalExamReport,
} from './fullExamReport';
import { matrixStatusLabel } from './examSuite';

type Props = {
  report: FormalExamReport | null;
  onInspectSet?: (setId: string) => void;
};

function levelClass(level: string): string {
  if (level === '不通过') return 'text-red-700 bg-red-50 border-red-200';
  if (level === '有条件通过') return 'text-amber-800 bg-amber-50 border-amber-200';
  if (level === '通过（有限范围）') return 'text-emerald-800 bg-emerald-50 border-emerald-200';
  return 'text-slate-700 bg-slate-50 border-slate-200';
}

function sevClass(sev: string): string {
  if (sev === '严重') return 'text-red-700';
  if (sev === '一般') return 'text-amber-700';
  return 'text-slate-600';
}

export default function EvalFullReportPanel({ report, onInspectSet }: Props) {
  if (!report) return null;
  const m = report.meta;
  const c = report.conclusion;
  const mdName = `${m.report_id}.md`;

  return (
    <section
      className="rounded-lg border border-slate-300 bg-white text-slate-800 shadow-sm overflow-hidden"
      data-testid="eval-full-report"
      data-report-id={m.report_id}
    >
      <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-2 bg-slate-100 border-b border-slate-200 print:hidden">
        <span className="text-xs text-slate-600">
          正规体例归档 · 默认作问题发现报告（accuracy_claim=false；≠正式发布认证）
        </span>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            data-testid="eval-full-report-download"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded border border-slate-400 text-slate-800 hover:bg-slate-50 text-xs"
            onClick={() => downloadTextFile(mdName, fullExamReportToMarkdown(report))}
          >
            <Download className="w-3.5 h-3.5" />
            下载正式报告（Markdown）
          </button>
          <button
            type="button"
            data-testid="eval-full-report-print"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded border border-slate-400 text-slate-800 hover:bg-slate-50 text-xs"
            onClick={() => window.print()}
          >
            <Printer className="w-3.5 h-3.5" />
            打印 / 另存 PDF
          </button>
        </div>
      </div>

      <article className="px-5 py-5 space-y-5 text-sm leading-relaxed eval-formal-report-print">
        <header className="text-center border-b border-slate-200 pb-4 space-y-2">
          <h2 className="text-xl font-semibold tracking-wide text-slate-900">{m.title}</h2>
          <p className="text-xs text-slate-500">报告编号：{m.report_id} · 版本 {m.version}</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1 text-left text-xs text-slate-700 max-w-2xl mx-auto mt-3">
            <p>
              <span className="text-slate-500">评测对象：</span>
              {m.agent_id}
            </p>
            <p>
              <span className="text-slate-500">评测类型：</span>
              {m.kind_label}
            </p>
            <p>
              <span className="text-slate-500">出具时间：</span>
              {m.generated_at_local}
            </p>
            <p>
              <span className="text-slate-500">运行档位：</span>
              {m.runtime_tier}
            </p>
            <p className="sm:col-span-2">
              <span className="text-slate-500">运行声明理由：</span>
              {m.runtime_claim_reason || '—'}
            </p>
            <p>
              <span className="text-slate-500">准确率声明：</span>
              否
            </p>
            <p>
              <span className="text-slate-500">充分性声明：</span>
              否
            </p>
            <p className="sm:col-span-2">
              <span className="text-slate-500">报告等级：</span>
              {m.problem_discovery_grade
                ? `问题发现归档（≠正式发布评审；${m.version || 'v1.3'}）`
                : '正式评审（需另开流程）'}
            </p>
          </div>
        </header>

        <section>
          <h3 className="text-sm font-semibold text-slate-900 border-l-4 border-slate-800 pl-2 mb-2">
            1. 评测概述
          </h3>
          <p className="text-xs text-slate-600 mb-1">
            <strong>目的：</strong>
            {m.purpose}
          </p>
          <p className="text-xs text-slate-600 mb-1">
            <strong>范围：</strong>
            {m.scope}
          </p>
          <p className="text-xs text-slate-600 mb-1">
            <strong>方法与环境：</strong>
            {m.method}
          </p>
          {m.score_policy ? (
            <p className="text-xs text-slate-600 mb-1">
              <strong>工程得分政策：</strong>
              {m.score_policy.policy}（task 30% / tool 20% / traj 5% / step 15% / recovery 15% /
              safety 10% / cost 5%；A≥90 B≥75 C≥60 D≥40）
            </p>
          ) : null}
          {m.score_ledger ? (
            <div className="text-xs text-slate-600 mb-2 space-y-1">
              <p>
                <strong>分项复算：</strong>
                {m.score_ledger.how_to_read}
              </p>
              <p>
                <strong>分数可信：</strong>
                {m.score_ledger.trust_scores ? '是' : '否（待核对）'} — {m.score_ledger.trust_note}
              </p>
              <ul className="list-disc pl-5 space-y-0.5">
                {(m.score_ledger.papers || []).slice(0, 8).map((row) => (
                  <li key={row.run_key}>
                    <code className="text-[11px]">{row.run_key}</code> recorded=
                    {row.recorded ?? '—'} / recomputed={row.recomputed ?? '—'}
                    {row.filled_keys?.length ? ` · 填充=${row.filled_keys.join(',')}` : ''}
                    {row.note ? ` · ${row.note}` : ''}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {m.reproduction ? (
            <p className="text-xs text-slate-600">
              <strong>复现摘要：</strong>
              独立用例集 {m.reproduction.unique_set_count}；模型 {m.reproduction.model}；判分器{' '}
              {m.reproduction.scorer}
              {(m.reproduction.limits || []).length
                ? `；复现限制：${(m.reproduction.limits || []).join('；')}`
                : ''}
            </p>
          ) : null}
        </section>

        {report.object_contract ? (
          <section data-testid="eval-object-contract-disclosure">
            <h3 className="text-sm font-semibold text-slate-900 border-l-4 border-slate-800 pl-2 mb-2">
              1.1 对象契约 / Plan / MatchReport
            </h3>
            <p className="text-xs text-slate-600 mb-1">
              <strong>plan_id：</strong>
              {(report.object_contract.plan_ids || []).join(', ') || '未采集'}
              {' · '}
              <strong>类型：</strong>
              {(report.object_contract.object_types || []).join(',') || '—'}
              {' · '}
              <strong>版本：</strong>
              {(report.object_contract.object_versions || []).join(',') || '—'}
            </p>
            {(() => {
              const pc = report.object_contract.pack_coverage;
              return (
                <p className="text-xs text-slate-600 mb-2">
                  <strong>三包：</strong>
                  core 入选 {pc.core.selected}/不适用 {pc.core.not_applicable}/未测{' '}
                  {pc.core.untested}；capability {pc.capability.selected}/
                  {pc.capability.not_applicable}/{pc.capability.untested}；special{' '}
                  {pc.special.selected}/{pc.special.not_applicable}/{pc.special.untested}
                </p>
              );
            })()}
            {(report.object_contract.excluded_sets || []).length > 0 ? (
              <ul className="text-xs text-slate-600 list-disc pl-5 mb-2 space-y-0.5">
                {report.object_contract.excluded_sets.slice(0, 8).map((e) => (
                  <li key={`${e.set_id}-${e.status}`}>
                    {e.set_id} · {e.status === 'untested' ? '未测(专项)' : '不适用'} ·{' '}
                    {(e.reasons || []).slice(0, 2).join('; ') || e.pack}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-slate-500 mb-2">无排除卷披露（或旧跑次未挂 MatchReport）。</p>
            )}
            <p className="text-[11px] text-slate-500">{report.object_contract.honesty}</p>
          </section>
        ) : null}

        <section>
          <h3 className="text-sm font-semibold text-slate-900 border-l-4 border-slate-800 pl-2 mb-2">
            2. 综合结论
          </h3>
          <div
            className={`inline-block px-3 py-1 rounded border text-sm font-semibold mb-2 ${levelClass(c.level)}`}
          >
            结论等级：{c.level}
          </div>
          <p className="text-slate-800">{c.statement}</p>
          <ul className="mt-2 text-xs text-slate-600 space-y-1 list-disc pl-5">
            <li>发布讨论意见：{c.publish_discussion}</li>
            <li>
              计数口径：运行完成 {c.papers_run_complete ?? c.papers_done}/
              {c.papers_run_total ?? c.papers_total}
              （执行结束，≠通过）；独立用例集 {c.unique_set_count ?? '—'}；维度未通过 {c.fail_n}
              ；需关注 {c.warn_n}；无法判定 {c.inconclusive_n ?? 0}；未测 {c.untested_n}
              ；工程得分范围 {c.score_range}
              （含缺失值填充；效率无法判定时 cost 仍可能以 0.5 占位进分，≠全维实测）
            </li>
          </ul>
        </section>

        <section>
          <h3 className="text-sm font-semibold text-slate-900 border-l-4 border-slate-800 pl-2 mb-2">
            3. 问题与改进建议
          </h3>
          {!report.findings.length ? (
            <p className="text-xs text-slate-600">
              本轮无「未通过 / 需关注」问题项。未测项见第 6 章，不得视为通过。
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs border-collapse min-w-[640px]">
                <thead>
                  <tr className="bg-slate-100 text-slate-700">
                    <th className="border border-slate-300 px-2 py-1.5 text-left">编号</th>
                    <th className="border border-slate-300 px-2 py-1.5 text-left">严重程度</th>
                    <th className="border border-slate-300 px-2 py-1.5 text-left">问题项</th>
                    <th className="border border-slate-300 px-2 py-1.5 text-left">结果</th>
                    <th className="border border-slate-300 px-2 py-1.5 text-left">相关用例集</th>
                    <th className="border border-slate-300 px-2 py-1.5 text-left print:hidden">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {report.findings.map((f) => (
                    <tr key={f.id} className="align-top">
                      <td className="border border-slate-300 px-2 py-1.5 font-mono">{f.id}</td>
                      <td className={`border border-slate-300 px-2 py-1.5 font-medium ${sevClass(f.severity)}`}>
                        {f.severity}
                      </td>
                      <td className="border border-slate-300 px-2 py-1.5">
                        <div className="font-medium text-slate-900">{f.title}</div>
                        <div className="text-slate-600 mt-0.5">现象：{f.description}</div>
                        {f.related_sets && f.related_sets.length > 1 ? (
                          <div className="text-slate-500 mt-0.5">
                            覆盖卷：{f.related_sets.join('、')}（跳转首选≠唯一失败卷）
                          </div>
                        ) : null}
                        <div className="text-slate-700 mt-0.5">建议：{f.recommendation}</div>
                      </td>
                      <td className="border border-slate-300 px-2 py-1.5">{f.status}</td>
                      <td className="border border-slate-300 px-2 py-1.5 font-mono">
                        {f.related_set || '—'}
                      </td>
                      <td className="border border-slate-300 px-2 py-1.5 print:hidden">
                        {f.related_set && onInspectSet ? (
                          <button
                            type="button"
                            className="text-violet-700 underline"
                            onClick={() => onInspectSet(f.related_set)}
                          >
                            查看明细
                          </button>
                        ) : (
                          '—'
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="mt-4">
              <h4 className="text-xs font-medium text-slate-800 mb-1">
                3.1 report-only 失败项（不计入工程分）
              </h4>
              <p className="text-[11px] text-slate-500 mb-2">
                拒绝校准等信号不参与 legacy_7dim 复合分；凡各卷检出（含未声明探针卷）均须列出，不得忽略。
              </p>
              {!(report.report_only_findings || []).length ? (
                <p className="text-xs text-slate-600">
                  本轮未检出 report-only 失败项。若第 5 章明细仍见 over_refusal，请重跑生成报告。
                </p>
              ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs border-collapse min-w-[640px]">
                  <thead>
                    <tr className="bg-amber-50 text-slate-700">
                      <th className="border border-slate-300 px-2 py-1.5 text-left">编号</th>
                      <th className="border border-slate-300 px-2 py-1.5 text-left">问题项</th>
                      <th className="border border-slate-300 px-2 py-1.5 text-left">结果</th>
                      <th className="border border-slate-300 px-2 py-1.5 text-left">相关用例集</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(report.report_only_findings || []).map((f) => (
                      <tr key={f.id} className="align-top">
                        <td className="border border-slate-300 px-2 py-1.5 font-mono">{f.id}</td>
                        <td className="border border-slate-300 px-2 py-1.5">
                          <div className="font-medium text-slate-900">{f.title}</div>
                          <div className="text-slate-600 mt-0.5">{f.description}</div>
                        </td>
                        <td className="border border-slate-300 px-2 py-1.5">{f.status}</td>
                        <td className="border border-slate-300 px-2 py-1.5 font-mono">
                          {f.related_set || '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              )}
          </div>
        </section>

        <section>
          <h3 className="text-sm font-semibold text-slate-900 border-l-4 border-slate-800 pl-2 mb-2">
            4. 分项评测结果
          </h3>
          {report.dimensions.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-xs border-collapse min-w-[640px]">
                <thead>
                  <tr className="bg-slate-100 text-slate-700">
                    <th className="border border-slate-300 px-2 py-1.5 text-left">评测维度</th>
                    <th className="border border-slate-300 px-2 py-1.5 text-left">结果</th>
                    <th className="border border-slate-300 px-2 py-1.5 text-left">依据摘要</th>
                    <th className="border border-slate-300 px-2 py-1.5 text-left">改进建议</th>
                  </tr>
                </thead>
                <tbody>
                  {report.dimensions.map((d) => (
                    <tr key={d.id} className="align-top">
                      <td className="border border-slate-300 px-2 py-1.5 whitespace-nowrap">
                        {d.title}
                      </td>
                      <td className="border border-slate-300 px-2 py-1.5">
                        {matrixStatusLabel(d.status)}
                      </td>
                      <td className="border border-slate-300 px-2 py-1.5 text-slate-600">
                        {d.meaning}
                      </td>
                      <td className="border border-slate-300 px-2 py-1.5 text-slate-700">
                        {d.next}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-xs text-slate-600">单用例集报告：分项详见第 5 章执行明细。</p>
          )}
        </section>

        <section>
          <h3 className="text-sm font-semibold text-slate-900 border-l-4 border-slate-800 pl-2 mb-2">
            5. 用例集执行明细
          </h3>
          <div className="space-y-3">
            {report.papers.map((p, idx) => (
              <details
                key={p.run_key}
                className="border border-slate-200 rounded px-3 py-2"
                open={idx < 2 || p.safety_veto || p.status === 'error'}
              >
                <summary className="cursor-pointer text-xs font-medium text-slate-900">
                  5.{idx + 1} {p.label}
                  <span className="font-normal text-slate-500 ml-2">
                    {p.purpose} ·{' '}
                    {p.status === 'done'
                      ? `得分 ${p.score ?? '—'}（${p.grade || '—'}）`
                      : p.status}
                    {p.safety_veto ? ' · 安全否决' : ''}
                  </span>
                </summary>
                <div className="mt-2 text-xs text-slate-700 space-y-2">
                  {p.error ? <p className="text-red-700">执行错误：{p.error}</p> : null}
                  {p.items.length ? (
                    <table className="w-full border-collapse">
                      <thead>
                        <tr className="bg-slate-50">
                          <th className="border border-slate-200 px-2 py-1 text-left">检查项</th>
                          <th className="border border-slate-200 px-2 py-1 text-left">结果</th>
                          <th className="border border-slate-200 px-2 py-1 text-left">证据</th>
                        </tr>
                      </thead>
                      <tbody>
                        {p.items.map((it) => (
                          <tr key={it.name}>
                            <td className="border border-slate-200 px-2 py-1">{it.name}</td>
                            <td className="border border-slate-200 px-2 py-1">{it.result}</td>
                            <td className="border border-slate-200 px-2 py-1 text-slate-600">
                              {it.evidence}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : null}
                  {p.failed_cases.length ? (
                    <div>
                      <div className="font-medium mb-1">失败 / 部分通过用例</div>
                      <ul className="list-disc pl-5 space-y-0.5 text-slate-600">
                        {p.failed_cases.map((f, i) => (
                          <li key={`${f.case_id}-${i}`}>
                            <code className="text-slate-800">{f.case_id}</code>
                            {f.level ? `（${f.level}）` : ''}
                            {f.detail ? `：${f.detail}` : ''}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </div>
              </details>
            ))}
          </div>
        </section>

        <section>
          <h3 className="text-sm font-semibold text-slate-900 border-l-4 border-slate-800 pl-2 mb-2">
            6. 未覆盖与限制
          </h3>
          {report.gaps.length ? (
            <>
              <h4 className="text-xs font-medium text-slate-800 mb-1">6.1 本轮未测项</h4>
              <ul className="list-disc pl-5 text-xs text-slate-600 space-y-0.5 mb-3">
                {report.gaps.map((g) => (
                  <li key={g}>{g}</li>
                ))}
              </ul>
            </>
          ) : null}
          <h4 className="text-xs font-medium text-slate-800 mb-1">6.2 报告限制与声明</h4>
          <ol className="list-decimal pl-5 text-xs text-slate-600 space-y-1">
            {report.limitations.map((x) => (
              <li key={x}>{x}</li>
            ))}
          </ol>
        </section>

        <section>
          <h3 className="text-sm font-semibold text-slate-900 border-l-4 border-slate-800 pl-2 mb-2">
            7. 签署（可选）
          </h3>
          <table className="w-full text-xs border-collapse max-w-3xl">
            <thead>
              <tr className="bg-slate-100">
                <th className="border border-slate-300 px-2 py-1.5 text-left">角色</th>
                <th className="border border-slate-300 px-2 py-1.5 text-left">姓名</th>
                <th className="border border-slate-300 px-2 py-1.5 text-left">日期</th>
                <th className="border border-slate-300 px-2 py-1.5 text-left">意见</th>
              </tr>
            </thead>
            <tbody>
              {['评测执行', '技术评审', '产品/业务确认'].map((role) => (
                <tr key={role}>
                  <td className="border border-slate-300 px-2 py-3">{role}</td>
                  <td className="border border-slate-300 px-2 py-3">&nbsp;</td>
                  <td className="border border-slate-300 px-2 py-3">&nbsp;</td>
                  <td className="border border-slate-300 px-2 py-3">&nbsp;</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <footer className="text-[11px] text-slate-500 border-t border-slate-200 pt-3">
          本文件由 aiPlat 评测中心自动生成，报告编号 {m.report_id}。下载 Markdown
          或打印为 PDF 后可归档流转。
        </footer>
      </article>
    </section>
  );
}
