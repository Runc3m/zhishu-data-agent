import {t} from './i18n';

export type Report = {conclusion: string; findings: string[]; actions: string[]; limitations: string[]; followups: string[]};

export function AnalysisReport({report, busy, ask}: {report: Report; busy: boolean; ask: (question: string) => void}) {
  return <section className="decision-report">
    <p className="report-conclusion">{report.conclusion}</p>
    {report.findings.length > 0 && <section><h4>{t("关键发现")}</h4><ul>{report.findings.map((s, i) => <li key={i}>{s}</li>)}</ul></section>}
    {report.actions.length > 0 && <section className="report-actions"><h4>{t("建议行动 · 待验证")}</h4><ul>{report.actions.map((s, i) => <li key={i}>{s}</li>)}</ul></section>}
    {report.limitations.length > 0 && <section><h4>{t("口径与局限")}</h4><ul>{report.limitations.map((s, i) => <li key={i}>{s}</li>)}</ul></section>}
    {report.followups.length > 0 && <section><h4>{t("继续探索")}</h4><div className="report-followups">{report.followups.map((s, i) => <button key={i} disabled={busy} onClick={() => ask(s)}>{s}</button>)}</div></section>}
  </section>;
}
