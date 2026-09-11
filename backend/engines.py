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
