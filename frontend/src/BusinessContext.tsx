import {useEffect, useState} from 'react';
import {getLanguage, t} from './i18n';

export type BusinessContext = {version: number; updated_at: string | null; notes: string; fields: string; metrics: string; relationships: string};
const sections = [
  {key: 'notes', label: '业务说明', hint: '说明数据覆盖范围、使用约定和需要排除的记录。'},
  {key: 'fields', label: '字段解释', hint: '每行说明一个字段：表名.字段、显示名称、含义、单位和常见取值。'},
  {key: 'metrics', label: '指标定义', hint: '写明指标名称、计算公式、筛选条件和时间口径；不要只写简称。'},
  {key: 'relationships', label: '关联关系', hint: '说明当前数据源内的关联字段，以及一对一或一对多关系，避免重复计数。'},
] as const;

async function request(sourceId: string, value?: BusinessContext): Promise<BusinessContext> {
  const response = await fetch(`/api/sources/${encodeURIComponent(sourceId)}/context`, {
    method: value ? 'PUT' : 'GET',
    headers: {'Content-Type': 'application/json', 'Accept-Language': getLanguage()},
    ...(value ? {body: JSON.stringify(value)} : {}),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : t('业务说明读写失败，请检查内容后重试。'));
  return data;
}

export function BusinessContextEditor({sourceId, onSaved}: {sourceId: string; onSaved: () => void}) {
  const [context, setContext] = useState<BusinessContext | null>(null);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    let active = true;
    setContext(null); setError('');
    request(sourceId).then(data => {if (active) setContext(data);}).catch(e => {if (active) setError(e.message);});
    return () => {active = false;};
  }, [sourceId]);
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!context) return;
    setSaving(true); setError('');
    try {setContext(await request(sourceId, context)); onSaved();}
    catch (e) {setError((e as Error).message);}
    finally {setSaving(false);}
  }
  return <form onSubmit={save} className="business-context-form">
    <p className="subtle">{t('这些说明由你确认后保存，AI 规划和修正查询时会引用。规则演示不使用业务说明；已有分析保留原版本。')}</p>
    {error && <p className="form-error" role="alert">{error}</p>}
    {context ? <>
      <p className="context-version">{context.version ? t('当前版本：{0}', context.version) : t('尚未配置')}{context.updated_at && ' · ' + new Date(context.updated_at).toLocaleString(getLanguage())}</p>
      <fieldset disabled={saving}>
        {sections.map(section => <label className="field" key={section.key}>{t(section.label)}
          <textarea maxLength={8000} rows={3} value={context[section.key]} onChange={e => setContext({...context, [section.key]: e.target.value})} placeholder={t(section.hint)}/>
        </label>)}
        <div className="modal-actions"><button className="primary-button" disabled={saving}>{saving ? t('正在保存…') : t('保存业务说明')}</button></div>
      </fieldset>
    </> : !error && <p>{t('正在读取业务说明…')}</p>}
  </form>;
}

export function ContextReference({context}: {context?: BusinessContext}) {
  if (!context) return null;
  return <details className="context-reference"><summary>{t('本次使用业务上下文 v{0}', context.version)}</summary>
    {sections.filter(section => context[section.key]).map(section => <section key={section.key}><h4>{t(section.label)}</h4><p>{context[section.key]}</p></section>)}
  </details>;
}
