import {t} from './i18n';

type QueryEvidence = {step?: number; label?: string; table?: string; status?: string; observation?: unknown; candidate_key?: string; column_map?: Record<string, string>; executed_sql?: string; sql?: string; columns?: string[]; rows?: (string | number | null)[][]; truncated?: boolean; duration_ms?: number};
export type EvidencePayload = {
  knowledge_sources?: {id: string; section: string; version: number; text: string; score: number}[];
  investigation?: QueryEvidence[];
  quality?: {checks: QueryEvidence[]; tables_checked: number; tables_total: number};
  reconciliation?: {passed: boolean; total_change: number; category_change_sum: number};
  stop_reason?: string;
  usage?: {model_calls: number; repair_attempts: number; duration_ms: number};
  retrieval?: {mode: string; model?: string};
  citation_audit?: {cited: string[]; unknown: string[]};
  pipeline_checks?: {passed: boolean; checks: QueryEvidence[]};
};

function Query({item}: {item: QueryEvidence}) {
  return <details className="evidence-query"><summary>{item.step ? `[${item.step}] ` : ''}{item.label || item.table} {item.duration_ms != null && <small>· {item.duration_ms} ms</small>}</summary>
    {item.status === 'unavailable' && <p>{t("检查未完成，不能判定数据质量。")}</p>}
    {item.candidate_key && <p>{t("候选主键（待确认）：{0}", item.candidate_key)}</p>}
    {item.column_map && <p>{Object.entries(item.column_map).map(([index, name]) => `${index}: ${name}`).join(' · ')}</p>}
    <pre><code>{item.executed_sql || item.sql}</code></pre>
    {item.observation != null && <pre><code>{JSON.stringify(item.observation, null, 2)}</code></pre>}
    {item.columns && <div className="table-scroll"><table><thead><tr>{item.columns.map((c, i) => <th key={i}>{c}</th>)}</tr></thead><tbody>{item.rows?.map((r, i) => <tr key={i}>{r.map((v, j) => <td key={j}>{v ?? '—'}</td>)}</tr>)}</tbody></table></div>}
    {item.truncated && <p className="warning-text">{t("结果已截断，不能代表全部数据。")}</p>}
  </details>;
}

export function EvidencePanel({result}: {result: EvidencePayload}) {
  const reasons: Record<string, string> = {
    complete: t("示例调查完成"), planner_stopped: t("规划器停止，请查看结论或澄清问题"),
    step_limit: t("已达到 5 步查询上限"), time_limit: t("已达到调查时间预算"),
    repeated_query: t("检测到重复查询，已停止"), query_error: t("查询修复未成功，证据已保留"),
    model_error: t("模型规划失败，证据已保留"),
  };
  return <div className="evidence-panel">
    {result.knowledge_sources && <details className="context-reference"><summary>{t("检索到的业务依据（{0}）", result.knowledge_sources.length)}</summary>
      <p>{t("按问题检索知识，并保留必要的口径约束。引用只校验出处存在，仍需核对证据是否支持结论。")}</p>
      {result.retrieval && <p>{result.retrieval.mode === 'hybrid' ? t("双语混合检索已启用") : t("当前使用关键词检索，语义检索不可用")}</p>}
      {!result.knowledge_sources.length && <p>{t("未命中相关片段，不会编造来源。")}</p>}
      {result.knowledge_sources.map(s => <section key={s.id}><h4>{s.id}</h4><p>{s.text}</p></section>)}
    </details>}
    {!!result.citation_audit?.unknown.length && <p className="warning-text">{t("存在无法匹配的引用，请核对结论：{0}", result.citation_audit.unknown.join(', '))}</p>}
    {result.pipeline_checks && <details className="context-reference"><summary>{result.pipeline_checks.passed ? t("处理链路核验通过") : t("处理链路存在异常或未完成的检查")}</summary><p>{t("核验仅覆盖当前快照，不能证明源系统数据完整。")}</p>{result.pipeline_checks.checks.map((c,i)=><div key={i}><strong>{c.status === 'pass' ? '✓' : '!' } {c.table}</strong><Query item={c}/></div>)}</details>}
    {result.quality && <details className="context-reference"><summary>{t("数据质量观察：{0}/{1} 张表", result.quality.tables_checked, result.quality.tables_total)}</summary><p>{t("每表最多检查 8 个数值或日期字段；日期起止不能证明导入完整，关联粒度和状态需进一步检查。")}</p>{result.quality.checks.map((item, i) => <Query key={i} item={item}/>)}</details>}
    {result.investigation && <section className="investigation-evidence"><h4>{t("调查证据")}</h4>{result.stop_reason && <p className="evidence-status">{reasons[result.stop_reason] || result.stop_reason}</p>}{result.investigation.map((item, i) => <Query key={i} item={item}/>)}
      {result.reconciliation && <p>{result.reconciliation.passed ? t("品类变化之和与总体变化一致") : t("分项与总体不一致，请核查")} · {result.reconciliation.category_change_sum.toLocaleString()} / {result.reconciliation.total_change.toLocaleString()} CNY</p>}
      {result.usage && <small>{t("模型调用 {0} 次 · 修复 {1} 次 · 耗时 {2} 秒", result.usage.model_calls, result.usage.repair_attempts, (result.usage.duration_ms / 1000).toFixed(1))}</small>}
    </section>}
  </div>;
}
