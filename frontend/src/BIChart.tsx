import {useEffect, useRef, useState} from 'react';
import * as echarts from 'echarts/core';
import {BarChart, LineChart, PieChart, ScatterChart, HeatmapChart, TreemapChart} from 'echarts/charts';
import {GridComponent, TooltipComponent, LegendComponent, VisualMapComponent, DataZoomComponent, ToolboxComponent} from 'echarts/components';
import {CanvasRenderer} from 'echarts/renderers';
import {t, useLanguage} from './i18n';

echarts.use([BarChart, LineChart, PieChart, ScatterChart, HeatmapChart, TreemapChart,
  GridComponent, TooltipComponent, LegendComponent, VisualMapComponent, DataZoomComponent, ToolboxComponent, CanvasRenderer]);

export type ChartData = {columns: string[]; rows: (string | number | null)[][]; chart?: {
  type: string; x: string; y: string[]; limit: number; numeric?: string[]; dimensions?: string[]; available?: string[];
} | null};

export function chartLabels(): Record<string, string> {
  return {bar: t("柱状图"), horizontal_bar: t("条形排名图"), line: t("折线图"), area: t("面积图"),
    stacked_bar: t("堆叠柱状图"), pie: t("饼图"), donut: t("环形图"), scatter: t("散点图"),
    heatmap: t("热力图"), treemap: t("矩形树图"), histogram: t("直方图"), kpi: t("指标卡")};
}

export function chartOptions(data: ChartData) {
  const numeric = data.columns.filter((_, i) => data.rows.some(r => typeof r[i] === 'number' && Number.isFinite(r[i])) &&
    data.rows.every(r => r[i] == null || (typeof r[i] === 'number' && Number.isFinite(r[i]))));
  const dimensions = data.columns.filter(c => !numeric.includes(c));
  const unique = dimensions.length && new Set(data.rows.map(r => String(r[data.columns.indexOf(dimensions[0])]))).size === data.rows.length;
  const types: string[] = data.rows.length === 1 && numeric.length ? ['kpi'] : [];
  if (unique && numeric.length) {
    types.push('bar', 'horizontal_bar', 'line', 'area');
    if (numeric.length > 1) types.push('stacked_bar');
    // Individual metric selection is checked again at render time.
    if (numeric.some(c => { const i = data.columns.indexOf(c); return data.rows.every(r => typeof r[i] === 'number' && Number(r[i]) >= 0) && data.rows.some(r => Number(r[i]) > 0); })) types.push('pie', 'donut', 'treemap');
  }
  if (numeric.length > 1) types.push('scatter');
  if (dimensions.length > 1 && numeric.length && new Set(data.rows.map(r => JSON.stringify(dimensions.slice(0, 2).map(c => r[data.columns.indexOf(c)])))).size === data.rows.length) {
    types.push('heatmap');
    if (!unique && new Set(data.rows.map(r => r[data.columns.indexOf(dimensions[1])])).size <= 20) types.push('bar', 'horizontal_bar', 'line', 'area', 'stacked_bar');
  }
  if (numeric.length) types.push('histogram');
  return {numeric, dimensions, types};
}

// Pure option builder, also exercised with Node regression tests.
export function buildOption(data: ChartData, kind: string, xName: string, metrics: string[], language: string): echarts.EChartsCoreOption | null {
  const rows = data.rows.slice(0, 500), x = data.columns.indexOf(xName), ys = metrics.map(c => data.columns.indexOf(c));
  const validNumber = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
  if (!rows.length || !ys.length || ys.some(i => i < 0)) return null;
  const base = {color: ['#168773', '#668fc1', '#dfaf59', '#ba779a', '#79a07d'],
    textStyle: {fontFamily: 'Inter, "Microsoft YaHei", sans-serif'},
    tooltip: {trigger: 'item', renderMode: 'richText'},
    toolbox: {right: 10, feature: {saveAsImage: {title: language === 'en-US' ? 'Save image' : '保存图片'}, restore: {title: language === 'en-US' ? 'Reset' : '重置'}}},
    legend: {bottom: 0, type: 'scroll'},
    grid: {left: 20, right: 35, top: 45, bottom: 85, containLabel: true}};
  if (['pie', 'donut', 'treemap'].includes(kind)) {
    if (x < 0 || rows.some(r => !validNumber(r[ys[0]]) || Number(r[ys[0]]) < 0) || !rows.some(r => Number(r[ys[0]]) > 0)) return null;
    const values = rows.map(r => ({name: String(r[x] ?? '—'), value: r[ys[0]]}));
    return {...base, series: [{type: kind === 'treemap' ? 'treemap' : 'pie', name: metrics[0],
      ...(kind === 'treemap' ? {breadcrumb: {show: false}, roam: false} : {radius: kind === 'pie' ? '65%' : ['42%', '65%'], label: {formatter: '{b}: {d}%'}}), data: values}]};
  }
  if (kind === 'scatter') {
    if (x < 0 || x === ys[0]) return null;
    return {...base, xAxis: {type: 'value', name: xName, scale: true}, yAxis: {type: 'value', name: metrics[0], scale: true},
      dataZoom: [{type: 'inside', xAxisIndex: 0}, {type: 'slider', xAxisIndex: 0, bottom: 30}],
      series: [{type: 'scatter', name: metrics[0], symbolSize: 10, data: rows.filter(r => validNumber(r[x]) && validNumber(r[ys[0]])).map(r => [r[x], r[ys[0]]])}]};
  }
  if (kind === 'heatmap') {
    const dims = chartOptions(data).dimensions;
    if (dims.length < 2) return null;
    const a = data.columns.indexOf(dims[0]), b = data.columns.indexOf(dims[1]);
    const xs = [...new Set(rows.map(r => String(r[a] ?? '—')))], cats = [...new Set(rows.map(r => String(r[b] ?? '—')))];
    const values = rows.filter(r => validNumber(r[ys[0]])).map(r => [xs.indexOf(String(r[a] ?? '—')), cats.indexOf(String(r[b] ?? '—')), Number(r[ys[0]])]);
    if (!values.length) return null;
    return {...base, xAxis: {type: 'category', name: dims[0], data: xs}, yAxis: {type: 'category', name: dims[1], data: cats},
      visualMap: {min: Math.min(...values.map(v => v[2])), max: Math.max(...values.map(v => v[2])), calculable: true, orient: 'horizontal', bottom: 5, left: 'center', inRange: {color: ['#e3f1ee', '#168773', '#153e52']}},
      series: [{type: 'heatmap', name: metrics[0], data: values}]};
  }
  if (kind === 'histogram') {
    const values = rows.map(r => r[ys[0]]).filter(validNumber);
    if (!values.length) return null;
    const min = Math.min(...values), max = Math.max(...values), n = min === max ? 1 : Math.min(20, Math.ceil(Math.sqrt(values.length)));
    const width = n === 1 ? 1 : (max - min) / n, counts = Array(n).fill(0) as number[];
    values.forEach(v => counts[Math.min(n - 1, Math.floor((v - min) / width))]++);
    const fmt = (v: number) => v.toLocaleString(language, {maximumSignificantDigits: 4});
    return {...base, xAxis: {type: 'category', name: metrics[0], data: counts.map((_, i) => min === max ? fmt(min) : `${fmt(min + i * width)}–${fmt(min + (i + 1) * width)}`)},
      yAxis: {type: 'value', name: language === 'en-US' ? 'Returned rows' : '返回行数', minInterval: 1}, series: [{type: 'bar', name: metrics[0], barCategoryGap: '2%', data: counts}]};
  }
  if (x < 0) return null;
  const horizontal = kind === 'horizontal_bar';
  const dimensions = chartOptions(data).dimensions;
  const grouped = dimensions.length >= 2 && new Set(rows.map(r => String(r[x]))).size < rows.length;
  const groupIndex = grouped ? data.columns.indexOf(dimensions[1]) : -1;
  const categories = [...new Set(rows.map(r => String(r[x] ?? '—')))];
  const groups = grouped ? [...new Set(rows.map(r => String(r[groupIndex] ?? '—')))] : [''];
  const category = {type: 'category', data: categories, axisLabel: {hideOverlap: true}};
  const value = {type: 'value', axisLabel: {formatter: (v: number) => new Intl.NumberFormat(language, {notation: 'compact'}).format(v)}};
  return {...base, tooltip: {...base.tooltip, trigger: 'axis'}, xAxis: horizontal ? value : category, yAxis: horizontal ? {...category, inverse: true} : value,
    dataZoom: [{type: 'inside', ...(horizontal ? {yAxisIndex: 0} : {xAxisIndex: 0})}, {type: 'slider', ...(horizontal ? {yAxisIndex: 0, right: 0} : {xAxisIndex: 0, bottom: 30}), end: rows.length > 30 ? 30 / rows.length * 100 : 100}],
    series: ys.flatMap((y, i) => groups.map(group => ({name: grouped ? `${group} · ${metrics[i]}` : metrics[i], type: ['line', 'area'].includes(kind) ? 'line' : 'bar',
      ...(kind === 'area' ? {areaStyle: {opacity: .16}} : {}), ...(kind === 'stacked_bar' ? {stack: 'components'} : {}),
      connectNulls: false, barMaxWidth: 48, data: categories.map(c => rows.find(r => String(r[x] ?? '—') === c && (!grouped || String(r[groupIndex] ?? '—') === group))?.[y] ?? null)})))};
}

export function BIChart({result}: {result: ChartData}) {
  const language = useLanguage(), ref = useRef<HTMLDivElement>(null), labels = chartLabels();
  const {numeric, dimensions, types} = chartOptions(result);
  const initial = result.chart?.type || 'bar';
  const [kind, setKind] = useState(types.includes(initial) ? initial : types[0]);
  const [metric, setMetric] = useState(numeric[0] || '');
  const [scatterX, setScatterX] = useState(numeric[0] || '');
  const [scatterY, setScatterY] = useState(numeric[1] || '');
  const [selected, setSelected] = useState<string[]>(numeric.slice(0, 1));
  const [valid, setValid] = useState(true);
  const multi = ['bar', 'horizontal_bar', 'line', 'area', 'stacked_bar'].includes(kind);
  const metrics = multi ? selected : [kind === 'scatter' ? scatterY : metric];
  useEffect(() => {
    if (!ref.current || kind === 'kpi') return;
    const option = buildOption(result, kind, kind === 'scatter' ? scatterX : dimensions[0], metrics, language);
    setValid(!!option);
    if (!option) return;
    const instance = echarts.init(ref.current);
    instance.setOption(option);
    const observer = new ResizeObserver(() => instance.resize()); observer.observe(ref.current);
    return () => {observer.disconnect(); instance.dispose();};
  }, [result, kind, scatterX, scatterY, metric, selected, language]);
  if (!types.length) return null;
  return <section className="bi-chart"><div className="bi-chart-controls">
    <label>{t("图表类型")}<select aria-label={t("图表类型")} value={kind} onChange={e => setKind(e.target.value)}>{types.map(type => <option key={type} value={type}>{labels[type]}</option>)}</select></label>
    {kind !== 'kpi' && (multi ? <fieldset><legend>{t("显示指标")}</legend>{numeric.map(c => <label key={c}><input type="checkbox" checked={selected.includes(c)} onChange={e => setSelected(e.target.checked ? [...selected, c] : selected.filter(v => v !== c))}/>{c}</label>)}</fieldset> : <label>{t("指标")}<select aria-label={t("指标")} value={kind === 'scatter' ? scatterY : metric} onChange={e => kind === 'scatter' ? setScatterY(e.target.value) : setMetric(e.target.value)}>{numeric.map(c => <option key={c}>{c}</option>)}</select></label>)}
    {kind === 'scatter' && <label>{t("横轴指标")}<select aria-label={t("横轴指标")} value={scatterX} onChange={e => setScatterX(e.target.value)}>{numeric.map(c => <option key={c}>{c}</option>)}</select></label>}
  </div>
  {kind === 'kpi' ? <div className="kpi-grid">{numeric.map(c => <article key={c}><span>{c}</span><strong>{Number(result.rows[0][result.columns.indexOf(c)]).toLocaleString(language, {maximumFractionDigits: 2})}</strong></article>)}</div> : <><div className="chart" ref={ref} role="img" aria-label={`${labels[kind]}: ${metrics.join(', ')}`}/>{!valid && <p className="warning-text">{t("这些字段不适合此图，请选择其他指标或图形。")}</p>}</>}
  {kind === 'stacked_bar' && <p className="chart-note">{t("仅堆叠同单位且可以相加的构成项；销售额、订单量和比率不能相加。")}</p>}
  {kind === 'histogram' && <p className="chart-note">{t("直方图展示返回行的分布；聚合结果的分布不等于原始订单分布。")}</p>}
  {['pie', 'donut', 'treemap'].includes(kind) && <p className="chart-note">{t("占比仅针对本次返回的数据，Top N 或截断结果不代表整体占比。")}</p>}
  <p className="chart-note">{t("支持图例筛选、缩放和图片下载；数据范围以实际查询为准。")}</p>
  </section>;
}
