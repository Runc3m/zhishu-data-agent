import {useEffect, useState} from 'react';
import {getLanguage, t} from './i18n';

type Step = {table:string; upstream:string[]; sql:string; version:number};
export function PipelinePanel({sourceId, experiment, added}: {sourceId:string; experiment?:boolean; added:(source:any)=>void}) {
  const [steps,setSteps] = useState<Step[]>([]);
  const [fault,setFault] = useState('control');
  const [working,setWorking] = useState(false);
  const [error,setError] = useState('');
  useEffect(()=>{let current=true; setSteps([]); setError(''); fetch(`/api/sources/${sourceId}/pipeline`).then(r=>{if(!r.ok)throw new Error(t("读取处理链路失败"));return r.json();}).then(x=>{if(current)setSteps(x.steps);}).catch(e=>{if(current)setError(e.message);});return()=>{current=false;};},[sourceId]);
  async function create() {
    setWorking(true);setError('');
    try {
      const response=await fetch(`/api/sources/${sourceId}/experiments`,{method:'POST',headers:{'Content-Type':'application/json','Accept-Language':getLanguage()},body:JSON.stringify({fault})});
      const data=await response.json();if(!response.ok)throw new Error(data.detail || t("创建实验失败"));added(data);
    }catch(e){setError((e as Error).message);}finally{setWorking(false);}
  }
  return <section className="pipeline-panel"><h2>{t("数据处理链路")}</h2><p>{t("原始数据 → 清洗订单 → 订单事实 → 每日报表。展开可查看实际执行的 SQL。")}</p>
    {steps.map(s=><details key={s.table}><summary>{s.upstream.join(' + ')} → <strong>{s.table}</strong> · v{s.version}</summary><pre><code>{s.sql}</code></pre></details>)}
    {!experiment && <div className="experiment-controls"><label>{t("独立故障实验")} <select value={fault} disabled={working} onChange={e=>setFault(e.target.value)}><option value="control">{t("正常对照")}</option><option value="fanout">{t("关联导致金额重复")}</option><option value="missing_partition">{t("清洗层遗漏日期")}</option><option value="status_filter">{t("报表包含取消订单")}</option><option value="stale_mart">{t("报表未随上游刷新")}</option></select></label><button className="secondary-button" disabled={working} onClick={create}>{working?t("正在处理…"):t("创建独立实验副本")}</button><p>{t("原始数据库保持不变。实验类型不会提供给 AI，模型需根据数据、SQL 和运行记录调查。")}</p></div>}
    {experiment && <p className="warning-text">{t("这是故障实验副本，不能作为真实经营结论。")}</p>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
