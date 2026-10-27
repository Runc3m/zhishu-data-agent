import {useEffect, useState} from 'react';
import {Trash2} from 'lucide-react';
import {getLanguage, t} from './i18n';

export type VerifiedQuery = {id: string; question: string; sql: string; created_at: string};
export type VerifiedExample = {question: string; sql: string};

export async function loadVerifiedQueries(sourceId: string): Promise<VerifiedQuery[]> {
  const response = await fetch(`/api/sources/${encodeURIComponent(sourceId)}/verified`, {headers: {'Accept-Language': getLanguage()}});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : t('已验证查询读取失败。'));
  return data;
}

export function ExampleReference({examples}: {examples?: VerifiedExample[]}) {
  if (!examples?.length) return null;
  return <details className="context-reference"><summary>{t('本次参考 {0} 条已验证查询', examples.length)}</summary>
    {examples.map((example, i) => <section key={i}><h4>{example.question}</h4><pre className="verified-sql">{example.sql}</pre></section>)}
  </details>;
}

export function VerifiedQueryList({sourceId, onChanged}: {sourceId: string; onChanged: () => void}) {
  const [items, setItems] = useState<VerifiedQuery[] | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    setItems(null); setError('');
    loadVerifiedQueries(sourceId).then(data => {if (active) setItems(data);}).catch(e => {if (active) setError(e.message);});
    return () => {active = false;};
  }, [sourceId]);
  async function remove(id: string) {
    setError('');
    const response = await fetch(`/api/sources/${encodeURIComponent(sourceId)}/verified/${id}`, {method: 'DELETE', headers: {'Accept-Language': getLanguage()}});
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      setError(typeof data.detail === 'string' ? data.detail : t('删除失败，请重试。'));
      return;
    }
    setItems(prev => prev?.filter(item => item.id !== id) ?? null);
    onChanged();
  }
  return <section className="verified-list">
    <h3>{t('已验证查询')}</h3>
    <p className="subtle">{t('在分析结果上点击“标记为正确”即可添加。启用 AI 后，相似问题会把最多 3 条问题与 SQL 作为参考示例发送给模型。')}</p>
    {error && <p className="form-error" role="alert">{error}</p>}
    {items === null ? !error && <p className="subtle">{t('正在读取…')}</p> : !items.length ? <p className="subtle">{t('还没有已验证查询。')}</p> :
      <ul>{items.map(item => <li key={item.id}><details><summary>{item.question}</summary><pre className="verified-sql">{item.sql}</pre></details>
        <button type="button" className="icon-button" title={t('删除')} aria-label={t('删除已验证查询：{0}', item.question)} onClick={() => void remove(item.id)}><Trash2 size={15}/></button></li>)}</ul>}
  </section>;
}
