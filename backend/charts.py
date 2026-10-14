"""Data-shape checked chart specifications; no executable model output."""
import math

CHART_TYPES = ('auto', 'bar', 'horizontal_bar', 'line', 'area', 'stacked_bar',
               'pie', 'donut', 'scatter', 'heatmap', 'treemap', 'histogram', 'kpi', 'none')


def chart_spec(result, preferred='auto'):
    columns, rows = result['columns'], result['rows']
    if preferred == 'none' or not rows or not columns:
        return None
    numeric = [i for i in range(len(columns)) if any(isinstance(r[i], (int, float)) and
               not isinstance(r[i], bool) and math.isfinite(r[i]) for r in rows)
               and all(v is None or (isinstance(v, (int, float)) and not isinstance(v, bool)
                       and math.isfinite(v)) for v in (r[i] for r in rows))]
    if not numeric:
        return None
    dimensions = [i for i in range(len(columns)) if i not in numeric]
    x = dimensions[0] if dimensions else numeric[0]
    ys = numeric if dimensions else numeric[1:]
    available = []
    if len(rows) == 1:
        available.append('kpi')
    if dimensions:
        # Duplicate categories require explicit aggregation or a second dimension.
        unique = len({str(r[x]) for r in rows}) == len(rows)
        if unique:
            available += ['bar', 'horizontal_bar', 'line', 'area']
            if len(numeric) > 1:
                available.append('stacked_bar')
            if all(r[numeric[0]] is not None and r[numeric[0]] >= 0 for r in rows) and any(r[numeric[0]] > 0 for r in rows):
                available += ['pie', 'donut', 'treemap']
        if len(dimensions) >= 2 and len({(str(r[dimensions[0]]), str(r[dimensions[1]])) for r in rows}) == len(rows):
            available.append('heatmap')
            if not unique and len({str(r[dimensions[1]]) for r in rows}) <= 20:
                available += ['bar', 'horizontal_bar', 'line', 'area', 'stacked_bar']
    if len(numeric) >= 2:
        available.append('scatter')
    available.append('histogram')
    kind = preferred if preferred in available else available[0]
    if kind in ('histogram', 'kpi'):
        ys = numeric
    elif kind == 'scatter':
        x, ys = numeric[0], numeric[1:]
    return {'type': kind, 'x': columns[x], 'y': [columns[i] for i in ys],
            'dimensions': [columns[i] for i in dimensions], 'numeric': [columns[i] for i in numeric],
            'available': available, 'limit': 500}
