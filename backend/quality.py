"""Bounded, read-only source diagnostics with explicit coverage limitations."""


def inspect_source(engines, source):
    checks = []
    quote = '`' if source['dialect'] == 'mysql' else '"'
    identifier = lambda value: quote + value.replace(quote, quote * 2) + quote
    for table in source['tables'][:3]:
        name = '.'.join(identifier(p) for p in (table.get('schema'), table['name']) if p)
        expressions = ['COUNT(*) AS row_count']
        # Only infer candidate keys, not declared PK constraints.
        key = next((c['name'] for c in table['columns'] if c['name'] in ('id', 'order_id', 'refund_id', 'item_id')), None)
        if key:
            q = identifier(key)
            expressions += [f'COUNT({q}) - COUNT(DISTINCT {q}) AS candidate_key_duplicates',
                            f'COUNT(*) - COUNT({q}) AS candidate_key_nulls']
        selected = [c for c in table['columns'] if any(k in c['type'].upper() for k in ('DATE', 'TIME', 'INT', 'DECIMAL', 'DOUBLE', 'FLOAT'))][:8]
        for index, col in enumerate(selected):
            q = identifier(col['name'])
            expressions.append(f'COUNT(*) - COUNT({q}) AS nulls_{index}')
            if any(k in col['type'].upper() for k in ('DATE', 'TIME')):
                expressions.extend([f'MIN({q}) AS earliest_{index}', f'MAX({q}) AS latest_{index}'])
        sql = f'SELECT {", ".join(expressions)} FROM {name}'
        try:
            result = engines.query(source, sql)
            checks.append({'table': table['name'], 'status': 'observed', 'candidate_key': key,
                           'column_map': {str(i): c['name'] for i, c in enumerate(selected)}, **result})
        except Exception:
            checks.append({'table': table['name'], 'status': 'unavailable', 'sql': sql})
    return {'checks': checks, 'tables_checked': len(checks), 'tables_total': len(source['tables']),
            'scope': 'At most 3 tables and 8 typed columns per table. Candidate keys are inferred, not constraints. '
                     'Date min/max do not prove import completeness. Confirm ingestion coverage and period comparability. '
                     'String dates, status validity and join cardinality need targeted investigation queries.'}
