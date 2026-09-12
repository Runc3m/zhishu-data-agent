import {t, getLanguage, useLanguage, setLanguage, type Language} from './i18n';
import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ArrowDownToLine, ArrowRight, ArrowUp, BarChart3, Check, CheckCircle2, ChevronDown, ChevronLeft, ChevronRight, Code2, Copy, Database, FileSpreadsheet, FolderOpen, History, Layers3, LineChart, Loader2, Menu, MessageSquare, Plus, Send, Settings2, ShieldCheck, Sparkles, Table2, UploadCloud, X, Zap, AlertCircle, PlugZap, CircleHelp } from 'lucide-react';
import * as echarts from 'echarts/core';
import { BarChart, LineChart as ELineChart, PieChart } from 'echarts/charts';
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import './style.css';
echarts.use([BarChart, ELineChart, PieChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer]);
type Source = {
    id: string;
    name: string;
    kind: string;
    dialect: string;
    description: string;
    tables: {
        name: string;
        schema: string;
        rows?: number;
        columns: {
            name: string;
            type: string;
        }[];
    }[];
};
type Settings = {
    mode: 'demo' | 'llm';
    provider: 'deepseek' | 'custom';
    base_url: string;
    model: string;
    has_api_key: boolean;
};
type Conversation = {
    id: string;
    title: string;
    source_id: string;
    updated_at: string;
};
type Result = {
    answer: string;
    sql?: string;
    executed_sql?: string;
    columns: string[];
    rows: (string | number | null)[][];
    row_count: number;
    truncated?: boolean;
    duration_ms?: number;
    mode?: string;
    notice?: string;
    error?: string;
    chart?: {
        type: string;
        x: string;
        y: string[];
        limit: number;
    };
};
type Message = {
    id: string;
    role: string;
    content: string;
    result?: Result;
};
type Step = {
    label: string;
    detail: string;
};
type StreamEvent = {
    type: string;
    label?: string;
    detail?: string;
    text?: string;
    sql?: string;
    message?: string;
    result?: Result;
    message_id?: string;
};
async function api<T>(path: string, options?: RequestInit): Promise<T> {
    const response = await fetch('/api' + path, {...options, headers: {...options?.headers, 'Accept-Language': getLanguage()}});
    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: t("服务没有响应，请确认后端已启动。") }));
        const detail = Array.isArray(error.detail) ? error.detail.map((x: {
            msg: string;
        }) => x.msg).join('；') : error.detail;
        throw new Error(detail || t("请求失败 ({0})", response.status));
    }
    return response.json();
}
const jsonBody = (data: unknown, method = 'POST'): RequestInit => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
const formatValue = (value: unknown) => typeof value === 'number' ? value.toLocaleString(getLanguage(), { maximumFractionDigits: 2 }) : value == null ? '—' : String(value);
function DataTable({ result }: {
    result: Result;
}) {
    const [page, setPage] = useState(0);
    const [sort, setSort] = useState<{
        index: number;
        direction: number;
    } | null>(null);
    const rows = sort ? [...result.rows].sort((a, b) => {
        const x = a[sort.index], y = b[sort.index];
        return (typeof x === 'number' && typeof y === 'number' ? x - y : String(x ?? '').localeCompare(String(y ?? ''), getLanguage())) * sort.direction;
    }) : result.rows;
    const pages = Math.max(1, Math.ceil(rows.length / 10));
    return <><div className="table-scroll"><table><thead><tr><th className="row-index">#</th>{result.columns.map((c, i) => <th key={i}><button onClick={() => { setSort({ index: i, direction: sort?.index === i ? -sort.direction : 1 }); setPage(0); }}>{c}<ChevronDown size={12}/></button></th>)}</tr></thead><tbody>{rows.slice(page * 10, page * 10 + 10).map((row, i) => <tr key={i}><td className="row-index">{page * 10 + i + 1}</td>{row.map((v, j) => <td key={j} className={typeof v === 'number' ? 'numeric' : ''} title={String(v ?? '')}>{formatValue(v)}</td>)}</tr>)}</tbody></table>{!rows.length && <div className="empty-small">{t("没有符合条件的数据")}</div>}</div><div className="table-footer"><span>{rows.length}{t("行")}{result.truncated && t("· 已截断至 500 行")}</span><div><button className="icon-button" aria-label={t("上一页")} disabled={page === 0} onClick={() => setPage(page - 1)}><ChevronLeft size={16}/></button><span>{page + 1} / {pages}</span><button className="icon-button" aria-label={t("下一页")} disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}><ChevronRight size={16}/></button></div></div></>;
}
function Chart({ result, type }: {
    result: Result;
    type: string;
}) {
    const language = useLanguage();
    const ref = useRef<HTMLDivElement>(null);
    useEffect(() => {
        if (!ref.current || !result.chart)
            return;
        const instance = echarts.init(ref.current);
        const spec = result.chart;
        const x = result.columns.indexOf(spec.x);
        const ys = spec.y.map(y => result.columns.indexOf(y));
        const rows = result.rows.slice(0, spec.limit);
        const colors = ['#168773', '#7aaac1', '#dbab5b'];
        const base = { color: colors, textStyle: { fontFamily: 'Inter, "Microsoft YaHei", sans-serif' },
            tooltip: { trigger: type === 'pie' ? 'item' : 'axis', renderMode: 'richText', backgroundColor: '#fff', borderColor: '#e5e9e9' },
            legend: { bottom: 0, icon: 'circle', itemWidth: 8, itemHeight: 8, textStyle: { color: '#728080' } } };
        instance.setOption(type === 'pie' ? { ...base, series: [{ type: 'pie', radius: ['43%', '67%'], center: ['50%', '45%'], avoidLabelOverlap: true, label: { formatter: '{b}: {d}%', color: '#526565' }, data: rows.map(r => ({ name: String(r[x]), value: r[ys[0]] ?? 0 })) }] } : {
            ...base, grid: { left: 18, right: 20, top: 24, bottom: 42, containLabel: true },
            xAxis: { type: 'category', data: rows.map(r => String(r[x])), axisLine: { lineStyle: { color: '#e5ebeb' } }, axisTick: { show: false }, axisLabel: { color: '#728080', hideOverlap: true } },
            yAxis: { type: 'value', splitLine: { lineStyle: { color: '#eff2f2', type: 'dashed' } }, axisLabel: { color: '#728080', formatter: (v: number) => new Intl.NumberFormat(language, {notation: 'compact', maximumFractionDigits: 1}).format(v) } },
            series: ys.map((y, i) => ({ name: spec.y[i], type, data: rows.map(r => r[y]), barMaxWidth: 48, symbolSize: 6, smooth: false,
                itemStyle: { borderRadius: type === 'bar' ? [5, 5, 0, 0] : 0 }, ...(type === 'line' ? { areaStyle: { opacity: .06 } } : {}) })),
        });
        const observer = new ResizeObserver(() => instance.resize());
        observer.observe(ref.current);
        return () => { observer.disconnect(); instance.dispose(); };
    }, [result, type, language]);
    return <div className="chart" ref={ref} role="img" aria-label={t("{0}与{1}的{2}", result.chart?.x, result.chart?.y.join('、'), type === 'line' ? t("折线图") : type === 'pie' ? t("饼图") : t("柱状图"))}/>;
}
function ResultCard({ message, cid, notify }: {
    message: Message;
    cid: string;
    notify: (s: string) => void;
}) {
    const result = message.result!;
    const [tab, setTab] = useState(result.chart ? 'chart' : 'data');
    const [type, setType] = useState(result.chart?.type || 'bar');
    async function copy() {
        try {
            await navigator.clipboard.writeText(result.executed_sql || result.sql || '');
            notify(t("SQL 已复制"));
        }
        catch {
            notify(t("浏览器未允许复制，请在 SQL 视图中手动选择。"));
        }
    }
    if (!result.sql)
        return null;
    return <div className="result-card"><div className="result-toolbar"><div className="tabs" role="tablist" aria-label={t("分析结果视图")}>
    {result.chart && <button role="tab" aria-selected={tab === 'chart'} className={tab === 'chart' ? 'active' : ''} onClick={() => setTab('chart')}><BarChart3 size={15}/>{t("图表")}</button>}
    <button role="tab" aria-selected={tab === 'data'} className={tab === 'data' ? 'active' : ''} onClick={() => setTab('data')}><Table2 size={15}/>{t("数据")}<span className="count">{result.row_count}</span></button>
    <button role="tab" aria-selected={tab === 'sql'} className={tab === 'sql' ? 'active' : ''} onClick={() => setTab('sql')}><Code2 size={15}/>SQL</button></div>
    <a className="icon-button" title={t("下载 CSV")} aria-label={t("下载查询结果 CSV")} href={`/api/conversations/${cid}/messages/${message.id}/csv`}><ArrowDownToLine size={16}/></a></div>
    {tab === 'chart' && <><div className="chart-heading"><span>{result.chart?.y.join(' / ')}<small>{t("按")}{result.chart?.x}</small></span><select aria-label={t("图表类型")} value={type} onChange={e => setType(e.target.value)}><option value="bar">{t("柱状图")}</option><option value="line">{t("折线图")}</option><option value="pie">{t("饼图")}</option></select></div><Chart result={result} type={type}/><div className="chart-note">{result.rows.length > 50 ? t("图表显示前 50 组，完整结果见数据视图") : t("图表基于本次实际查询结果")}</div></>}
    {tab === 'data' && <DataTable result={result}/>}
    {tab === 'sql' && <div className="sql-panel"><div><span>{result.mode === 'demo' ? t("规则生成") : t("AI 生成")}{t("· 实际执行 SQL（含返回行数限制）")}</span><button className="text-button" onClick={copy}><Copy size={14}/>{t("复制")}</button></div><pre><code>{result.executed_sql || result.sql}</code></pre></div>}
    <div className="result-footer"><ShieldCheck size={13}/><span>{t("只读查询")}</span><span className="dot"/><span>{result.duration_ms} ms</span>{result.truncated && <span className="warning-text">{t("最多展示 500 行")}</span>}</div></div>;
}
function Modal({ title, subtitle, onClose, children }: {
    title: string;
    subtitle?: string;
    onClose: () => void;
    children: React.ReactNode;
}) {
    const ref = useRef<HTMLDialogElement>(null);
    useEffect(() => { ref.current?.showModal(); const d = ref.current; return () => d?.close(); }, []);
    return <dialog ref={ref} className="modal" onCancel={onClose} onClick={e => { if (e.target === e.currentTarget)
        onClose(); }}><div className="modal-head"><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div><button className="icon-button" aria-label={t("关闭")} onClick={onClose}><X size={20}/></button></div>{children}</dialog>;
}
function SettingsModal({ settings, close, saved, notify }: {
    settings: Settings;
    close: () => void;
    saved: (s: Settings) => void;
    notify: (s: string) => void;
}) {
    const [form, setForm] = useState({ ...settings, api_key: '' });
    const [working, setWorking] = useState('');
    const [error, setError] = useState('');
    const [clearKey, setClearKey] = useState(false);
    const changedProvider = form.provider !== settings.provider || (form.provider === 'custom' && form.base_url !== settings.base_url);
    async function submit(test: boolean) {
        setWorking(test ? 'test' : 'save');
        setError('');
        const body = { ...form, api_key: clearKey ? '' : form.api_key.trim() || (changedProvider ? '' : null) };
        try {
            if (test || form.mode === 'llm')
                await api('/settings/test', jsonBody(body));
            if (test)
                notify(t("模型连接成功，可以启用 AI 分析"));
            else {
                saved(await api<Settings>('/settings', jsonBody(body, 'PUT')));
                notify(form.mode === 'llm' ? t("连接成功，AI 分析已启用") : t("已切换到规则演示"));
                close();
            }
        }
        catch (e) {
            setError((e as Error).message);
        }
        finally {
            setWorking('');
        }
    }
    return <Modal title={t("模型设置")} subtitle={t("DeepSeek 只需填写 Key，其余由知数配置。")} onClose={() => { if (!working)
        close(); }}><form onSubmit={e => { e.preventDefault(); void submit(false); }}><fieldset disabled={!!working} style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
    <div className="mode-choices">{(['demo', 'llm'] as const).map(mode => <label className={form.mode === mode ? 'mode selected' : 'mode'} key={mode}><input type="radio" name="mode" value={mode} checked={form.mode === mode} onChange={() => setForm({ ...form, mode })}/><div>{mode === 'demo' ? <Zap size={18}/> : <Sparkles size={18}/>}<strong>{mode === 'demo' ? t("规则演示") : t("AI 分析")}</strong><small>{mode === 'demo' ? t("无需密钥 · 有限问题") : t("连接模型 · 自由提问")}</small></div></label>)}</div>
    {form.mode === 'llm' && <><label className="field">{t("模型服务")}<select value={form.provider} onChange={e => setForm({ ...form, provider: e.target.value as Settings['provider'], api_key: '' })}><option value="deepseek">{t("DeepSeek（推荐 · 只填 Key）")}</option><option value="custom">{t("其他兼容服务 / 本地模型")}</option></select></label>
    {form.provider === 'deepseek' ? <p className="subtle">{t("已自动配置 DeepSeek 官方接口与 V4 Flash 模型，无需填写网址和模型名。")}</p> : <><label className="field">{t("API 根地址")}<input required type="url" value={form.base_url} onChange={e => setForm({ ...form, base_url: e.target.value })} placeholder={t("服务商提供的 HTTPS 地址")}/><small>{t("兼容 Chat Completions；本地 Ollama 可填 http://localhost:11434/v1")}</small></label><label className="field">{t("模型名称")}<input required value={form.model} onChange={e => setForm({ ...form, model: e.target.value })}/></label></>}
    <label className="field">{form.provider === 'deepseek' ? 'DeepSeek API Key' : 'API Key'}<input type="password" autoComplete="new-password" value={form.api_key} onChange={e => { setClearKey(false); setForm({ ...form, api_key: e.target.value }); }} placeholder={settings.has_api_key && !changedProvider ? t("已保存，留空继续使用") : form.provider === 'deepseek' ? t("粘贴你的 DeepSeek API Key") : t("本地模型无密钥时可留空")}/><small>{changedProvider ? t("更换服务后请重新填写对应的 Key，旧 Key 不会发送到新地址。") : t("只需填写一次，之后启动会自动记住。")}</small></label>
    <div className="info-note"><ShieldCheck size={18}/><span>{t("密钥加密保存在本机。AI 分析会将问题、表结构、最近对话和最多 30 行结果发送给模型服务，并产生该服务的 API 用量费用。")}</span></div></>}
    {form.mode === 'demo' && settings.has_api_key && <label className="checkbox-label"><input type="checkbox" checked={clearKey} onChange={e => setClearKey(e.target.checked)}/>{t("同时清除已保存的密钥（不勾选则保留）")}</label>}
    {error && <div className="form-error" role="alert">{error}</div>}
    <div className="modal-actions">{form.mode === 'llm' && <button type="button" className="secondary-button" disabled={!!working} onClick={() => void submit(true)}>{working === 'test' ? <Loader2 className="spin" size={16}/> : <PlugZap size={16}/>}{t("仅测试连接")}</button>}<button className="primary-button" disabled={!!working}>{working === 'save' && <Loader2 className="spin" size={16}/>} {working === 'save' ? t("正在验证…") : form.mode === 'llm' ? t("验证并启用") : t("使用规则演示")}</button></div></fieldset>
  </form></Modal>;
}
function SourceModal({ close, added }: {
    close: () => void;
    added: (s: Source) => void;
}) {
    const [tab, setTab] = useState('csv');
    const [file, setFile] = useState<File | null>(null);
    const [working, setWorking] = useState(false);
    const [error, setError] = useState('');
    const [form, setForm] = useState({ name: '', dialect: 'postgres', host: 'localhost', port: 5432, database: '', username: '', password: '', schema_name: 'public', sslmode: 'prefer' });
    const field = (key: keyof typeof form, value: string | number) => setForm({ ...form, [key]: value });
    async function submit(e: React.FormEvent) {
        e.preventDefault();
        setWorking(true);
        setError('');
        try {
            let source: Source;
            if (tab === 'csv') {
                if (!file)
                    throw new Error(t("请先选择一个 CSV 文件。"));
                const data = new FormData();
                data.append('file', file);
                source = await api<Source>('/sources/csv', { method: 'POST', body: data });
            }
            else
                source = await api<Source>('/sources/database', jsonBody(form));
            added(source);
            close();
        }
        catch (e) {
            setError((e as Error).message);
        }
        finally {
            setWorking(false);
        }
    }
    return <Modal title={t("添加数据源")} subtitle={t("从文件开始，或连接你的业务数据库。")} onClose={close}><div className="source-tabs"><button className={tab === 'csv' ? 'active' : ''} onClick={() => setTab('csv')} disabled={working}><FileSpreadsheet size={17}/>{t("导入 CSV")}</button><button className={tab === 'database' ? 'active' : ''} onClick={() => setTab('database')} disabled={working}><Database size={17}/>{t("连接数据库")}</button></div>
    <form onSubmit={submit}>{tab === 'csv' ? <><label className="upload-zone" onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); if (e.dataTransfer.files[0])
        setFile(e.dataTransfer.files[0]); }}><UploadCloud size={32}/><strong>{file ? file.name : t("选择文件，或将 CSV 拖到这里")}</strong><span>{file ? `${(file.size / 1024).toFixed(1)} KB` : t("UTF-8 / GB18030 · 最大 20 MB · 10 万行")}</span><input type="file" accept=".csv,text/csv" onChange={e => setFile(e.target.files?.[0] || null)}/></label><p className="subtle">{t("首行作为字段名称。导入后可预览结构、提问并生成图表。")}</p></> : <div className="form-grid"><label className="field full">{t("显示名称")}<input required value={form.name} onChange={e => field('name', e.target.value)} placeholder={t("例如：业务数据仓库")}/></label><label className="field">{t("数据库类型")}<select value={form.dialect} onChange={e => setForm({ ...form, dialect: e.target.value, port: e.target.value === 'postgres' ? 5432 : 3306, schema_name: e.target.value === 'postgres' ? 'public' : '' })}><option value="postgres">PostgreSQL</option><option value="mysql">MySQL</option></select></label><label className="field">{t("端口")}<input type="number" min="1" max="65535" required value={form.port} onChange={e => field('port', Number(e.target.value))}/></label><label className="field full">{t("主机地址")}<input required value={form.host} onChange={e => field('host', e.target.value)}/></label><label className="field">{t("数据库名称")}<input required value={form.database} onChange={e => field('database', e.target.value)}/></label><label className="field">Schema<input value={form.schema_name} onChange={e => field('schema_name', e.target.value)} placeholder={t("默认 Schema")}/></label><label className="field">{t("用户名")}<input required value={form.username} onChange={e => field('username', e.target.value)} autoComplete="off"/></label><label className="field">{t("密码")}<input type="password" value={form.password} onChange={e => field('password', e.target.value)} autoComplete="new-password"/></label><label className="field full">{t("传输加密")}<select value={form.sslmode} onChange={e => field('sslmode', e.target.value)}><option value="prefer">{t("默认（PostgreSQL 优先 TLS）")}</option><option value="require">{t("要求 TLS")}</option></select></label><div className="info-note full"><ShieldCheck size={18}/><span>{t("请使用只读数据库账号。连接后读取指定 Schema 的前 30 张表结构，凭据加密保存在本机。")}</span></div></div>}
    {error && <div className="form-error" role="alert">{error}</div>}<div className="modal-actions"><button type="button" className="secondary-button" onClick={close} disabled={working}>{t("取消")}</button><button className="primary-button" disabled={working}>{working ? <Loader2 className="spin" size={16}/> : <Plus size={16}/>} {working ? t("正在处理…") : tab === 'csv' ? t("导入数据") : t("测试并连接")}</button></div></form>
  </Modal>;
}
function App() {
    const language = useLanguage();
    const [languageSaving, setLanguageSaving] = useState(false);
    async function changeLanguage(value: Language) {
        setLanguageSaving(true);
        try {await api('/preferences', jsonBody({language: value}, 'PUT')); setLanguage(value);}
        catch {notify(t('语言保存失败'));}
        finally {setLanguageSaving(false);}
    }
    const [sources, setSources] = useState<Source[]>([]), [sourceId, setSourceId] = useState('demo-sales');
    const [settings, setSettings] = useState<Settings | null>(null), [conversations, setConversations] = useState<Conversation[]>([]);
    const [cid, setCid] = useState(''), [messages, setMessages] = useState<Message[]>([]), [view, setView] = useState('chat');
    const [modal, setModal] = useState(''), [input, setInput] = useState(''), [busy, setBusy] = useState(false);
    const [steps, setSteps] = useState<Step[]>([]), [plan, setPlan] = useState(''), [liveSql, setLiveSql] = useState('');
    const [toast, setToast] = useState(''), [fatal, setFatal] = useState(''), [initializing, setInitializing] = useState(true);
    const [showSchema, setShowSchema] = useState(true), [mobileMenu, setMobileMenu] = useState(false);
    const [preview, setPreview] = useState<Result | null>(null), [previewError, setPreviewError] = useState(''), [selectedTable, setSelectedTable] = useState('');
    const bottom = useRef<HTMLDivElement>(null), textarea = useRef<HTMLTextAreaElement>(null), chatGuard = useRef(false), loadSequence = useRef(0);
    const displaySources = sources.map(s => s.id === "demo-sales" ? {...s, name: t("销售演示数据"), description: t("模拟数据 · 2026 年 1–8 月 · 非真实经营数据")} : {...s, description: s.kind === 'csv' ? t("CSV 导入 · 表名 data") : t("数据库只读连接")});
    const source = displaySources.find(s => s.id === sourceId);
    const notify = (text: string) => setToast(text);
    const suggestions = sourceId === 'demo-sales' ? [
        { icon: BarChart3, label: t("销售表现"), question: t("各地区销售额对比") }, { icon: LineChart, label: t("发现趋势"), question: t("每月销售趋势") },
        { icon: Layers3, label: t("品类分析"), question: t("各品类利润排名") }, { icon: Table2, label: t("关键指标"), question: t("销售概览") },
    ] : [{ icon: Table2, label: t("先看数据"), question: t("预览前 20 行") }, { icon: BarChart3, label: t("数据规模"), question: t("共有多少行") }];
    async function load() {
        setFatal('');
        setInitializing(true);
        try {
            const [s, c, m, preferences] = await Promise.all([api<Source[]>('/sources'), api<Conversation[]>('/conversations'), api<Settings>('/settings'), api<{language: Language}>('/preferences')]);
            setLanguage(preferences.language);
            setSources(s);
            setConversations(c);
            setSettings(m);
            if (s.length && !s.some(x => x.id === sourceId))
                setSourceId(s[0].id);
        }
        catch (e) {
            setFatal((e as Error).message);
        }
        finally {
            setInitializing(false);
        }
    }
    useEffect(() => { void load(); }, []);
    useEffect(() => { if (toast) {
        const timer = setTimeout(() => setToast(''), 4500);
        return () => clearTimeout(timer);
    } }, [toast]);
    useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }); }, [messages, steps, plan]);
    useEffect(() => { setSelectedTable(source?.tables[0]?.name || ''); }, [sourceId, sources]);
    useEffect(() => {
        if (view !== 'data' || !sourceId || !selectedTable)
            return;
        let current = true;
        setPreview(null);
        setPreviewError('');
        api<Result>(`/sources/${sourceId}/preview?table=${encodeURIComponent(selectedTable)}`).then(r => { if (current)
            setPreview(r); }).catch(e => { if (current)
            setPreviewError(e.message); });
        return () => { current = false; };
    }, [view, sourceId, selectedTable]);
    function reset(next = sourceId) { loadSequence.current++; setCid(''); setMessages([]); setSourceId(next); setSteps([]); setInput(''); setView('chat'); setMobileMenu(false); textarea.current?.focus(); }
    async function openConversation(c: Conversation) {
        if (chatGuard.current || busy)
            return;
        const sequence = ++loadSequence.current;
        try {
            const msgs = await api<Message[]>(`/conversations/${c.id}/messages`);
            if (sequence !== loadSequence.current)
                return;
            setCid(c.id);
            setSourceId(c.source_id);
            setMessages(msgs);
            setView('chat');
            setMobileMenu(false);
        }
        catch (e) {
            notify((e as Error).message);
        }
    }
    async function send(question = input) {
        const text = question.trim();
        if (!text || busy || chatGuard.current || !source)
            return;
        chatGuard.current = true;
        loadSequence.current++;
        setBusy(true);
        setInput('');
        setSteps([]);
        setPlan('');
        setLiveSql('');
        setView('chat');
        let target = cid;
        try {
            if (!target) {
                const conv = await api<Conversation>('/conversations', jsonBody({ source_id: sourceId }));
                target = conv.id;
                setCid(target);
            }
            setMessages(prev => [...prev, { id: 'pending-user', role: 'user', content: text }]);
            const response = await fetch(`/api/conversations/${target}/messages`, jsonBody({ content: text, language }));
            if (!response.ok) {
                const e = await response.json();
                throw new Error(e.detail || t("分析请求失败"));
            }
            if (!response.body)
                throw new Error(t("浏览器不支持流式响应。"));
            const reader = response.body.getReader(), decoder = new TextDecoder();
            let buffer = '', done = false;
            function event(event: StreamEvent) {
                if (event.type === 'step')
                    setSteps(prev => [...prev, { label: event.label!, detail: event.detail! }]);
                if (event.type === 'plan')
                    setPlan(event.text || '');
                if (event.type === 'sql')
                    setLiveSql(event.sql || '');
                if (event.type === 'result')
                    setMessages(prev => [...prev, { id: event.message_id!, role: 'assistant', content: event.result!.answer, result: event.result }]);
                if (event.type === 'error')
                    notify(event.message || t("分析失败"));
                if (event.type === 'done')
                    done = true;
            }
            while (true) {
                const chunk = await reader.read();
                buffer += decoder.decode(chunk.value, { stream: !chunk.done });
                let idx;
                while ((idx = buffer.indexOf('\n\n')) >= 0) {
                    const block = buffer.slice(0, idx);
                    buffer = buffer.slice(idx + 2);
                    for (const line of block.split('\n')) {
                        if (line.startsWith('data: '))
                            event(JSON.parse(line.slice(6)));
                    }
                }
                if (chunk.done)
                    break;
            }
            if (!done)
                throw new Error(t("连接中断，请从历史对话查看结果或重试。"));
        }
        catch (e) {
            notify((e as Error).message);
            setInput(text);
        }
        finally {
            try {
                if (target)
                    setMessages(await api<Message[]>(`/conversations/${target}/messages`));
                setConversations(await api<Conversation[]>('/conversations'));
            }
            catch { /* Keep the result already received over SSE. */ }
            setBusy(false);
            chatGuard.current = false;
            setSteps([]);
            setPlan('');
            setLiveSql('');
        }
    }
    const addSource = (s: Source) => { setSources(prev => [...prev, s]); reset(s.id); notify(t("数据源已添加")); };
    if (initializing || fatal)
        return <div className="boot"><div className="brand-mark"><BarChart3 size={28}/></div><h1>{t("知数")}</h1>{fatal ? <><p role="alert">{fatal}</p><button className="primary-button" onClick={() => void load()}>{t("重新连接")}</button></> : <p><Loader2 className="spin" size={16}/>{t("正在连接数据工作台…")}</p>}</div>;
    return <div className="app-shell">{mobileMenu && <div className="mobile-backdrop" onClick={() => setMobileMenu(false)}/>}
    <aside className={'sidebar ' + (mobileMenu ? 'open' : '')}><div className="brand"><div className="brand-mark"><BarChart3 size={22}/></div><div><strong>{t("知数")}</strong><span>DATA AGENT</span></div><span className="version">{__APP_VERSION__}</span></div>
      <button className="new-analysis" disabled={busy} onClick={() => reset()}><Plus size={18}/>{t("新建分析")}<span>＋</span></button>
      <div className="nav-section-label">{t("工作空间")}</div><nav><button className={view === 'chat' ? 'nav-item active' : 'nav-item'} disabled={busy} onClick={() => { setView('chat'); setMobileMenu(false); }}><MessageSquare size={18}/>{t("对话分析")}</button><button className={view === 'data' ? 'nav-item active' : 'nav-item'} disabled={busy} onClick={() => { setView('data'); setMobileMenu(false); }}><Database size={18}/>{t("数据源")}<span className="nav-count">{sources.length}</span></button></nav>
      <div className="nav-section-label history-label">{t("最近分析")}<History size={13}/></div><div className="history-list">{conversations.length ? conversations.map(c => <button title={c.title} key={c.id} className={cid === c.id ? 'history-item selected' : 'history-item'} disabled={busy} onClick={() => void openConversation(c)}><MessageSquare size={14}/><span>{c.title}</span></button>) : <p className="history-empty">{t("你的分析会自动保存在这里")}</p>}</div>
      <div className="sidebar-bottom"><div className="local-status"><span className="status-led"/><div>{t("本地工作空间")}<small>{t("文件与对话保存在本机")}</small></div></div><button className="nav-item settings-nav" disabled={busy} onClick={() => setModal('settings')}><Settings2 size={18}/>{t("模型设置")}<ChevronRight size={15}/></button><div className="profile"><div className="avatar">{t("我")}</div><div>{t("我的工作台")}<small>{t("个人空间")}</small></div><ShieldCheck size={16}/></div></div>
    </aside>
    <div className="main-shell"><header className="topbar"><div className="breadcrumb"><button className="icon-button menu-toggle" aria-label={t("打开导航")} onClick={() => setMobileMenu(true)}><Menu size={20}/></button><FolderOpen size={17}/><span>{t("工作空间")}</span><span className="slash">/</span><strong>{view === 'chat' ? t("对话分析") : t("数据源")}</strong></div><div className="top-actions"><select className="language-select" aria-label="Language / 语言" value={language} disabled={languageSaving} onChange={e => void changeLanguage(e.target.value as Language)}><option value="zh-CN">简体中文</option><option value="en-US">English</option></select><button className={'mode-badge ' + (settings?.mode === 'llm' ? 'ai' : '')} disabled={busy} onClick={() => setModal('settings')}><span className="status-led"/>{settings?.mode === 'llm' ? t("AI 分析模式") : t("规则演示模式")}</button><button className="icon-button" title={t("使用说明")} aria-label={t("使用说明")} onClick={() => setModal('help')}><CircleHelp size={19}/></button></div></header>
    {view === 'chat' ? <><div className="analysis-bar"><div><span className="eyebrow">ANALYSIS</span><h1>{cid ? conversations.find(c => c.id === cid)?.title || t("进行中的分析") : t("新的分析")}</h1></div><div className="analysis-actions"><div className="source-select"><Database size={15}/><select aria-label={t("选择数据源")} value={sourceId} disabled={busy} onChange={e => reset(e.target.value)}>{displaySources.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></div><button className={'icon-button schema-toggle ' + (showSchema ? 'selected' : '')} title={t("查看表结构")} aria-label={t("切换表结构面板")} onClick={() => setShowSchema(!showSchema)}><Table2 size={18}/></button></div></div>
    <div className="analysis-layout"><main className="chat-column"><div className="chat-scroll">
      {!messages.length ? <div className="welcome"><div className="welcome-symbol"><Sparkles size={28}/></div><div className="welcome-kicker">{t("从一个好问题开始")}</div><h2>{t("让数据，回答你的问题。")}</h2><p>{t("选择数据源，直接提问。结论、图表和查询过程都在这里。")}</p><div className="current-data"><div className="data-icon"><Database size={20}/></div><div><strong>{source?.name}</strong><span>{source?.tables.length}{t("张表")}{source?.tables[0]?.rows != null ? t(" · {0} 条记录", source.tables[0].rows.toLocaleString(getLanguage())) : ''}</span></div><span className="tag">{source?.kind === 'demo' ? t("模拟数据") : source?.kind === 'csv' ? 'CSV' : t("只读连接")}</span></div><div className="suggestions">{suggestions.map(s => <button key={s.question} disabled={busy} onClick={() => void send(s.question)}><span className="suggestion-top"><s.icon size={17}/>{s.label}</span><span>{s.question}<ArrowRight size={16}/></span></button>)}</div><div className="welcome-foot"><ShieldCheck size={14}/>{t("每一条结论，都可以查看背后的 SQL")}</div></div> : <div className="message-list">{messages.map(m => <div key={m.id} className={'message ' + m.role}><div className={'message-avatar ' + (m.role === 'user' ? 'person' : '')}>{m.role === 'user' ? t("我") : <Sparkles size={18}/>}</div><div className="message-body"><div className="message-name">{m.role === 'user' ? t("你") : t("知数")}{m.role === 'assistant' && <span>{m.result?.mode === 'demo' ? t("规则演示") : t("分析助手")}</span>}</div><div className={'message-text ' + (m.result?.error ? 'error-text' : '')}>{m.content}</div>{m.result?.notice && <div className="result-notice">{m.result.notice}</div>}{m.result?.sql && <ResultCard message={m} cid={cid} notify={notify}/>}</div></div>)}
      {busy && <div className="message assistant pending"><div className="message-avatar"><Sparkles size={18}/></div><div className="message-body"><div className="message-name">{t("知数")}<span>{t("正在分析")}</span></div><div className="steps">{steps.map((s, i) => <div className="step" key={i}>{i === steps.length - 1 ? <Loader2 size={15} className="spin"/> : <CheckCircle2 size={15}/>}<div>{s.label}<small>{s.detail}</small></div></div>)}</div>{plan && <p className="plan-text">{plan}</p>}{liveSql && <details className="live-sql"><summary>{t("查看当前 SQL")}</summary><pre>{liveSql}</pre></details>}</div></div>}
      {!busy && messages.some(m => m.result?.sql) && <div className="followups"><span>{t("继续探索")}</span>{[t("改成折线图"), t("只看第二季度")].map(q => <button key={q} onClick={() => void send(q)}>{q}<ArrowRight size={13}/></button>)}</div>}<div ref={bottom}/></div>}
    </div><div className="composer-wrap"><form className={'composer ' + (busy ? 'processing' : '')} onSubmit={e => { e.preventDefault(); void send(); }}><textarea ref={textarea} aria-label={t("输入数据分析问题")} value={input} maxLength={4000} disabled={busy} placeholder={busy ? t("正在分析，请稍候…") : t("问问你的数据，例如：哪些地区的销售表现最好？")} onChange={e => setInput(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            void send();
        } }}/><div className="composer-bottom"><button type="button" className="composer-source" disabled={busy} onClick={() => setModal('source')}><Plus size={16}/>{t("添加数据")}</button><span className="composer-shortcut">{t("Enter 发送 · Shift + Enter 换行")}</span><button className="send-button" aria-label={t("发送问题")} disabled={busy || !input.trim() || !source}>{busy ? <Loader2 className="spin" size={19}/> : <ArrowUp size={20}/>}</button></div></form><div className="composer-disclaimer">{settings?.mode === 'demo' ? t("演示模式使用有限规则，不调用大模型。可在模型设置中启用 AI。") : t("AI 分析可能有误，请结合 SQL 和原始数据核对业务结论。")}{cid && <a href={`/api/conversations/${cid}/export?language=${getLanguage()}`}>{t("导出分析")}<ArrowDownToLine size={12}/></a>}</div></div></main>
    {showSchema && source && <aside className="schema-panel"><div className="schema-title"><span>{t("数据上下文")}</span><Layers3 size={16}/></div><div className="schema-source"><div className="data-icon"><Database size={20}/></div><strong>{source.name}</strong><span className="tag">{source.dialect === 'duckdb' ? 'DuckDB' : source.dialect === 'postgres' ? 'PostgreSQL' : 'MySQL'}</span></div><p className="schema-description">{source.description}</p><div className="schema-table-label">{t("数据表")}<span>{source.tables.length}</span></div><div className="schema-tables">{source.tables.map(t => <details open={source.tables.length === 1} key={t.name}><summary><Table2 size={15}/>{t.name}<span>{t.columns.length}</span></summary><div className="schema-fields">{t.columns.map(c => <div key={c.name}><span className="field-type">{/INT|DOUBLE|DECIMAL|FLOAT/i.test(c.type) ? '#' : /DATE|TIME/i.test(c.type) ? '◷' : 'Aa'}</span><span title={c.name}>{c.name}</span><small>{c.type.replace(/\(.*/, '')}</small></div>)}</div></details>)}</div><div className="schema-bottom"><ShieldCheck size={17}/><div>{t("可追溯的分析")}<small>{t("SQL 校验后执行，结果来自当前数据源。")}</small></div></div><button className="secondary-button preview-button" disabled={busy} onClick={() => setView('data')}><Table2 size={15}/>{t("预览数据")}</button></aside>}
    </div></> : <main className="data-page"><div className="page-heading"><div><span className="eyebrow">DATA SOURCES</span><h1>{t("你的数据，准备就绪。")}</h1><p>{t("管理分析的数据来源，查看真实字段与数据预览。")}</p></div><button className="primary-button" onClick={() => setModal('source')}><Plus size={17}/>{t("添加数据源")}</button></div><div className="source-grid">{displaySources.map(s => <button key={s.id} className={'source-card ' + (sourceId === s.id ? 'selected' : '')} onClick={() => { setSourceId(s.id); setCid(''); setMessages([]); }}><div className="source-card-top"><div className="data-icon">{s.kind === 'csv' ? <FileSpreadsheet size={22}/> : <Database size={22}/>}</div>{sourceId === s.id ? <CheckCircle2 size={19}/> : <span className="status-led"/>}</div><strong>{s.name}</strong><p>{s.description}</p><div className="source-card-footer"><span>{s.tables.length}{t("张表")}</span><span>{s.kind === 'demo' ? t("模拟数据") : s.dialect.toUpperCase()}</span></div></button>)}</div><section className="preview-section"><div className="preview-heading"><div><h2>{t("数据预览")}</h2><span>{t("最多显示前 20 行")}</span></div><select aria-label={t("选择要预览的数据表")} value={selectedTable} onChange={e => setSelectedTable(e.target.value)}>{source?.tables.map(t => <option key={t.name} value={t.name}>{t.schema ? `${t.schema}.` : ''}{t.name}</option>)}</select><button className="text-button" onClick={() => reset()}>{t("分析这个数据源")}<ArrowRight size={16}/></button></div>{preview ? <DataTable result={preview}/> : <div className="empty-small">{previewError ? <span role="alert">{previewError}</span> : <><Loader2 size={18} className="spin"/>{t("正在读取数据…")}</>}</div>}</section></main>}
    </div>
    {modal === 'settings' && settings && <SettingsModal settings={settings} close={() => setModal('')} saved={setSettings} notify={notify}/>}
    {modal === 'source' && <SourceModal close={() => setModal('')} added={addSource}/>}
    {modal === 'help' && <Modal title={t("开始你的第一次分析")} onClose={() => setModal('')}><div className="help-content"><p>{t("1. 选择演示数据，或添加 CSV / 数据库连接。")}</p><p>{t("2. 点击建议问题，查看实际查询生成的图表、数据和 SQL。")}</p><p>{t("3. 在模型设置中选择 AI 分析，保持 DeepSeek，只填 API Key，再点“验证并启用”。无需填写网址和模型名。")}</p><p>{t("4. 在同一对话中继续追问；历史对话会自动保存，也可以导出 Markdown 或 CSV。")}</p><p>{t("5. 下次双击知数即可自动打开网页，无需打开 CMD。启动中心可以最小化，用完点击“退出知数”。")}</p><div className="info-note"><ShieldCheck size={20}/><span>{t("当前是本机单用户工作台。给别人用请分享免安装 ZIP，对方填写自己的 Key；127.0.0.1 不是公网网址。")}</span></div></div><div className="modal-actions"><button className="primary-button" onClick={() => setModal('')}>{t("开始分析")}<ArrowRight size={16}/></button></div></Modal>}
    {toast && <div className="toast" role="status"><AlertCircle size={17}/>{toast}<button aria-label={t("关闭提示")} onClick={() => setToast('')}><X size={15}/></button></div>}
  </div>;
}
createRoot(document.getElementById('root')!).render(<App />);
