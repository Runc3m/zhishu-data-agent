import csv
import io
import json
import math
import random
import re
import threading
import time
from datetime import date, timedelta
from decimal import Decimal

import duckdb
import pandas as pd
from sqlalchemy import URL, create_engine, inspect
from sqlalchemy.pool import NullPool

from .safety import MAX_ROWS, TIMEOUT_SECONDS, validate_sql
from .store import Store, now, uid


def scalar(v):
    if v is None:
        return None
    if isinstance(v, float) and not math.isfinite(v):
        return None
    if isinstance(v, Decimal):
        return scalar(float(v))
    if isinstance(v, (str, int, float, bool)):
        return v[:10000] if isinstance(v, str) else v
    return str(v)[:10000]


SENSITIVE = re.compile(r'^name$|(?:customer|user|contact|full|first|last|real|nick)_?name|phone|mobile|e?mail|address|id_?card|passport|ssn|password|token|姓名|电话|手机|邮箱|地址|身份证|密码', re.I)


def column_kind(type_name):
    t = type_name.upper()
    if any(k in t for k in ('JSON', 'ARRAY', '[]', 'BLOB', 'BYTEA', 'BINARY', 'STRUCT', 'MAP', 'UNION', 'GEOM')):
        return None
    if 'BOOL' in t:
        return 'boolean'
    if any(k in t for k in ('DATE', 'TIME')):
        return 'time'
    if any(k in t for k in ('INT', 'DEC', 'NUM', 'FLOAT', 'DOUBLE', 'REAL', 'MONEY')):
        return 'number'
    if any(k in t for k in ('CHAR', 'TEXT', 'STRING', 'ENUM')):
        return 'text'
    return None


def public_source(source):
    return {k: v for k, v in source.items() if k not in ('credentials', 'path')}


class Engines:
    def __init__(self, store: Store):
        self.store = store

    def seed(self):
        if any(s['id'] == 'demo-sales' for s in self.store.sources()):
            return
        rng = random.Random(2026)
        records = []
        for i in range(720):
            d = date(2026, 1, 1) + timedelta(days=rng.randrange(243))
            amount = round(rng.uniform(80, 3200), 2)
            records.append({'order_id': f'ORD-{i + 1:05d}', 'order_date': d,
                'region': rng.choice(['华东', '华南', '华北', '西南']),
                'category': rng.choice(['数码配件', '办公用品', '家居生活', '运动户外']),
                'channel': rng.choice(['线上商城', '线下门店', '合作渠道']),
                'sales': amount, 'profit': round(amount * rng.uniform(.12, .38), 2),
                'quantity': rng.randint(1, 12)})
        self._import_df(pd.DataFrame(records), '销售演示数据', 'demo-sales', 'sales', 'demo', '模拟数据 · 2026 年 1–8 月 · 非真实经营数据')

    def _import_df(self, df, name, sid, table, kind, description=''):
        if df.empty:
            raise ValueError('数据文件没有记录。')
        if len(df) > 100000 or len(df.columns) > 120:
            raise ValueError('单个数据源最多 100,000 行、120 列。')
        path = self.store.root / f'{sid}.duckdb'
        con = duckdb.connect(str(path))
        try:
            con.register('_uploaded', df)
            con.execute(f'CREATE OR REPLACE TABLE "{table}" AS SELECT * FROM _uploaded')
            columns = [{'name': r[0], 'type': r[1]} for r in con.execute(f'DESCRIBE "{table}"').fetchall()]
        finally:
            con.close()
        source = {'id': sid, 'name': name, 'kind': kind, 'dialect': 'duckdb', 'path': str(path),
            'tables': [{'name': table, 'schema': '', 'columns': columns, 'rows': len(df)}],
            'description': description, 'created_at': now()}
        self.store.save_source(source)
        return public_source(source)

    def import_csv(self, content, filename):
        if not filename.lower().endswith('.csv'):
            raise ValueError('请上传 CSV 文件。')
        try:
            text = content.decode('utf-8-sig')
        except UnicodeDecodeError:
            try:
                text = content.decode('gb18030')
            except UnicodeDecodeError as e:
                raise ValueError('文件编码无法识别，请另存为 UTF-8 CSV。') from e
        if '\x00' in text:
            raise ValueError('文件包含无效二进制内容。')
        try:
            df = pd.read_csv(io.StringIO(text), nrows=100001)
        except (pd.errors.ParserError, pd.errors.EmptyDataError) as e:
            raise ValueError('CSV 格式不正确，请检查表头、分隔符和引号。') from e
        names, used = [], set()
        for index, col in enumerate(df.columns):
            base = re.sub(r'[^\w]', '_', str(col).strip())[:64] or f'column_{index + 1}'
            candidate, suffix = base, 2
            while candidate in used:
                candidate = f'{base}_{suffix}'
                suffix += 1
            used.add(candidate)
            names.append(candidate)
        df.columns = names
        return self._import_df(df, filename[:100], uid(), 'data', 'csv', 'CSV 导入 · 表名 data')

    def _external_engine(self, source):
        creds = json.loads(self.store.decrypt(source['credentials']))
        dialect = source['dialect']
        url = URL.create('postgresql+psycopg' if dialect == 'postgres' else 'mysql+pymysql',
            username=creds['username'], password=creds['password'], host=creds['host'],
            port=creds['port'], database=creds['database'])
        args = {'connect_timeout': 8}
        if dialect == 'postgres':
            args.update(options='-c default_transaction_read_only=on -c statement_timeout=8000', sslmode=creds.get('sslmode', 'prefer'))
        else:
            args.update(read_timeout=10, write_timeout=10,
                        init_command='SET SESSION TRANSACTION READ ONLY')
            if creds.get('sslmode') == 'require':
                args['ssl'] = {'check_hostname': True}
        return create_engine(url, connect_args=args, poolclass=NullPool, hide_parameters=True)

    def connect_database(self, config):
        source = {'id': uid(), 'name': config['name'], 'kind': 'database', 'dialect': config['dialect'],
            'credentials': self.store.encrypt(json.dumps(config)), 'created_at': now(), 'description': '数据库只读连接'}
        engine = self._external_engine(source)
        try:
            with engine.connect() as conn:
                inspector = inspect(conn)
                schema = config.get('schema_name') or ('public' if config['dialect'] == 'postgres' else config['database'])
                names = inspector.get_table_names(schema=schema)[:30]
                if not names:
                    raise ValueError('指定 Schema 中没有可访问的数据表。')
                source['tables'] = [{'name': name, 'schema': schema, 'columns': [
                    {'name': c['name'], 'type': str(c['type'])} for c in inspector.get_columns(name, schema=schema)
                ]} for name in names]
        except ValueError:
            raise
        except Exception as e:
            raise ValueError('连接失败，请检查地址、端口、凭据、Schema 和网络。') from e
        finally:
            engine.dispose()
        self.store.save_source(source)
        return public_source(source)

    def query(self, source, sql):
        executed = validate_sql(sql, source['dialect'], source['tables'])
        start = time.monotonic()
        if source['dialect'] == 'duckdb':
            con = duckdb.connect(source['path'], read_only=True, config={
                'enable_external_access': 'false', 'memory_limit': '256MB', 'threads': '2',
                'allow_unsigned_extensions': 'false', 'autoinstall_known_extensions': 'false',
                'autoload_known_extensions': 'false',
            })
            timer = threading.Timer(TIMEOUT_SECONDS, con.interrupt)
            timer.daemon = True
            try:
                timer.start()
                cur = con.execute(executed)
                columns = [c[0] for c in cur.description]
                rows = cur.fetchmany(MAX_ROWS + 1)
            finally:
                timer.cancel()
                timer.join()
                con.close()
        else:
            engine = self._external_engine(source)
            try:
                with engine.connect() as con:
                    if source['dialect'] == 'mysql':
                        con.exec_driver_sql('SET SESSION MAX_EXECUTION_TIME=8000')
                    cur = con.exec_driver_sql(executed)
                    columns = list(cur.keys())
                    rows = cur.fetchmany(MAX_ROWS + 1)
                    con.rollback()
            finally:
                engine.dispose()
        return {'sql': sql, 'executed_sql': executed, 'columns': columns,
            'rows': [[scalar(v) for v in r] for r in rows[:MAX_ROWS]],
            'row_count': min(len(rows), MAX_ROWS), 'truncated': len(rows) > MAX_ROWS,
            'duration_ms': round((time.monotonic() - start) * 1000)}

    def profile(self, source, language='zh-CN'):
        """Draft field notes from real values; nothing is saved or sent to a model until the user saves it."""
        quote = '`' if source['dialect'] == 'mysql' else '"'
        q = lambda name: quote + name.replace(quote, quote * 2) + quote
        en = language == 'en-US'
        lines = []
        for table in source['tables']:
            full = '.'.join(q(part) for part in (table.get('schema'), table['name']) if part)
            columns = [(c, kind) for c in table['columns'][:60] if (kind := column_kind(c['type']))]
            if not columns:
                continue
            aggregates = [f'COUNT(DISTINCT {q(c["name"])})' + ('' if kind == 'boolean' else f', MIN({q(c["name"])}), MAX({q(c["name"])})') for c, kind in columns]
            try:
                stats = iter(self.query(source, f"SELECT {', '.join(aggregates)} FROM {full}")['rows'][0])
            except Exception:
                lines.append(f"{table['name']}: " + ('statistics unavailable' if en else '无法读取统计信息'))
                continue
            for column, kind in columns:
                distinct = next(stats)
                low, high = (None, None) if kind == 'boolean' else (next(stats), next(stats))
                label = f"{table['name']}.{column['name']} ({column['type']})" if en else f"{table['name']}.{column['name']}（{column['type']}）"
                sep = ': ' if en else '：'
                if SENSITIVE.search(column['name']):
                    lines.append(label + sep + ('may contain personal data; values skipped' if en else '可能包含个人信息，未提取取值'))
                elif not distinct:
                    lines.append(label + sep + ('no values' if en else '没有取值'))
                elif kind == 'text' and distinct <= 12:
                    try:
                        values = [r[0] for r in self.query(source, f'SELECT {q(column["name"])} FROM {full} WHERE {q(column["name"])} IS NOT NULL GROUP BY 1 ORDER BY COUNT(*) DESC, 1')['rows']]
                    except Exception:
                        values = []
                    if values and all(len(str(v)) <= 40 for v in values):
                        lines.append(label + sep + (f'{distinct} values: ' + ', '.join(map(str, values)) if en else f'{distinct} 个取值：' + '、'.join(map(str, values))))
                    else:
                        lines.append(label + sep + (f'{distinct} distinct values' if en else f'{distinct} 个不同值'))
                elif kind in ('number', 'time') and low is not None:
                    fmt = lambda v: str(round(v, 2)) if isinstance(v, float) else str(v)
                    lines.append(label + sep + (f'range {fmt(low)} to {fmt(high)}' if en else f'范围 {fmt(low)} ~ {fmt(high)}'))
                else:
                    lines.append(label + sep + (f'{distinct} distinct values' if en else f'{distinct} 个不同值'))
        text, size = [], 0
        for line in lines:
            size += len(line) + 1
            if size > 6000:
                break
            text.append(line)
        return '\n'.join(text)

    def schema_context(self, source):
        # Values are intentionally excluded; the model initially sees only schema.
        return {'dialect': source['dialect'], 'description': source.get('description', ''), 'tables': source['tables']}


def csv_bytes(result):
    out = io.StringIO(newline='')
    writer = csv.writer(out)
    def safe(v):
        if isinstance(v, str) and v.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')):
            return "'" + v
        return v
    writer.writerow([safe(c) for c in result['columns']])
    writer.writerows([[safe(v) for v in row] for row in result['rows']])
    return ('\ufeff' + out.getvalue()).encode('utf-8')
