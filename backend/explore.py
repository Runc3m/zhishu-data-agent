"""Schema-driven starting questions and a no-model rule planner for user data.

Both work from column names and types only, so rule mode can answer simple
grouping, trend and summary questions about any imported table without a key.
"""
import re

from .engines import SENSITIVE, column_kind

ID_LIKE = re.compile(r'(?:^|_)(?:id|uuid|key|code|no)$|^id_|编号$', re.I)
DATE_NAME = re.compile(r'date|time|day|month|year|_at$|_dt$|日期|时间|月份|年份', re.I)
TREND = re.compile(r'趋势|每月|按月|月度|逐月|monthly|trend|by month|over time', re.I)
AVERAGE = re.compile(r'平均|均值|average|avg|mean', re.I)
COUNT = re.compile(r'记录数|条数|数量|多少条|计数|count|number of records', re.I)
RATE = re.compile(r'rate|ratio|pct|percent|share|score|率|占比|比例|评分', re.I)
SUMMARY = re.compile(r'概况|概览|统计|分布|范围|summary|overview|stats|statistics|range', re.I)


def quote(source, name):
    q = '`' if source['dialect'] == 'mysql' else '"'
    return q + name.replace(q, q * 2) + q


def table_name(source, table):
    return '.'.join(quote(source, part) for part in (table.get('schema'), table['name']) if part)


def classify(table):
    """Split columns into metrics, dimensions and dates by type and name."""
    metrics, dims, dates = [], [], []
    for column in table['columns']:
        name, kind = column['name'], column_kind(column['type'])
        if not kind or SENSITIVE.search(name):
            continue
        if kind == 'time' or (kind == 'text' and DATE_NAME.search(name)):
            dates.append(name)
        elif kind == 'number' and not ID_LIKE.search(name):
            metrics.append(name)
        elif kind in ('text', 'boolean') and not ID_LIKE.search(name):
            dims.append(name)
    # Additive amounts make better first suggestions than rates, which cannot be summed.
    metrics.sort(key=lambda name: bool(RATE.search(name)))
    return metrics, dims, dates


def month_bucket(source, column):
    col = quote(source, column)
    if source['dialect'] == 'mysql':
        return f"DATE_FORMAT({col}, '%Y-%m')", f'{col} IS NOT NULL'
    if source['dialect'] == 'postgres':
        return f"TO_CHAR(CAST({col} AS DATE), 'YYYY-MM')", f'{col} IS NOT NULL'
    # Imported CSV dates may be text; TRY_CAST skips values that are not dates.
    return f"STRFTIME(TRY_CAST({col} AS DATE), '%Y-%m')", f'TRY_CAST({col} AS DATE) IS NOT NULL'


def suggestions(engines, source, language='zh-CN'):
    table = source['tables'][0]
    metrics, dims, dates = classify(table)
    if dims and engines:
        # Prefer readable groupings: few distinct values first, skip near-unique text.
        try:
            counts = engines.query(source, 'SELECT ' + ', '.join(f'COUNT(DISTINCT {quote(source, d)})' for d in dims[:12]) + f' FROM {table_name(source, table)}')['rows'][0]
            ranked = sorted((n, d) for n, d in zip(counts, dims) if 1 < (n or 0) <= 50)
            dims = [d for _, d in ranked] or dims
        except Exception:
            pass
    en = language == 'en-US'
    items = []
    if dims and metrics:
        items.append({'kind': 'compare', 'question': f'Total {metrics[0]} by {dims[0]}' if en else f'按 {dims[0]} 汇总 {metrics[0]}'})
    if dates and metrics:
        items.append({'kind': 'trend', 'question': f'Monthly {metrics[0]} trend' if en else f'按月查看 {metrics[0]} 趋势'})
    if metrics:
        items.append({'kind': 'summary', 'question': f'{metrics[-1] if len(metrics) > 1 else metrics[0]} summary' if en else f'{metrics[-1] if len(metrics) > 1 else metrics[0]} 的整体概况'})
    if dims:
        dim = dims[1] if len(dims) > 1 else dims[0]
        items.append({'kind': 'count', 'question': f'Record count by {dim}' if en else f'各 {dim} 的记录数'})
    items.append({'kind': 'preview', 'question': 'Preview the first 20 rows' if en else '预览前 20 行'})
    return items[:5]


def mentioned(question, names):
    """Columns named in the question, longest names first so `amount_cents` beats `amount`."""
    text, found = question.lower(), []
    for name in sorted(names, key=len, reverse=True):
        low = name.lower()
        pattern = re.escape(low) if not low.isascii() else r'(?<![a-z0-9_])' + re.escape(low) + r'(?![a-z0-9_])'
        match = re.search(pattern, text)
        if match:
            found.append((match.start(), name))
            text = text[:match.start()] + ' ' * len(low) + text[match.end():]
    return [name for _, name in sorted(found)]


def rule_plan(question, source):
    """Return (sql, explanation, chart_type), or None when no column is named."""
    best = max(source['tables'], key=lambda t: len(mentioned(question, [c['name'] for c in t['columns']])))
    metrics, dims, dates = classify(best)
    named = mentioned(question, [c['name'] for c in best['columns']])
    if not named:
        return None
    metric = next((c for c in named if c in metrics), None)
    dim = next((c for c in named if c in dims), None)
    date = next((c for c in named if c in dates), None) or (dates[0] if dates else None)
    full = table_name(source, best)
    func = 'AVG' if AVERAGE.search(question) or (metric and RATE.search(metric)) else 'SUM'
    label = '平均' if func == 'AVG' else '合计'
    if metric and date and TREND.search(question):
        bucket, valid = month_bucket(source, date)
        sql = f'SELECT {bucket} AS month, ROUND({func}({quote(source, metric)}), 2) AS {quote(source, metric + "_" + func.lower())} FROM {full} WHERE {valid} GROUP BY 1 ORDER BY 1'
        return sql, f'按 {date} 的月份汇总 {metric}（{label}）。', 'line'
    if dim and metric:
        sql = f'SELECT {quote(source, dim)}, ROUND({func}({quote(source, metric)}), 2) AS {quote(source, metric + "_" + func.lower())} FROM {full} GROUP BY 1 ORDER BY 2 DESC LIMIT 50'
        return sql, f'按 {dim} 汇总 {metric}（{label}），从高到低排序，最多 50 组。', 'bar'
    if dim:
        sql = f'SELECT {quote(source, dim)}, COUNT(*) AS record_count FROM {full} GROUP BY 1 ORDER BY 2 DESC LIMIT 50'
        return sql, f'统计各 {dim} 的记录数，最多 50 组。', 'bar'
    if metric and (SUMMARY.search(question) or COUNT.search(question) or func == 'AVG' or len(named) == 1):
        col = quote(source, metric)
        sql = f'SELECT COUNT({col}) AS value_count, ROUND(SUM({col}), 2) AS total, ROUND(AVG({col}), 2) AS average, MIN({col}) AS minimum, MAX({col}) AS maximum FROM {full}'
        return sql, f'计算 {metric} 的数量、合计、平均值、最小值和最大值。', 'none'
    return None


def rule_help(source, language='zh-CN'):
    """Concrete example questions built from this table's own columns."""
    return [item['question'] for item in suggestions(None, source, language) if item['kind'] != 'preview'][:3]
