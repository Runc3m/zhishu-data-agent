"""Local Olist warehouse: DuckDB ingestion and SQLGlot-derived table lineage.

Original CSVs are retained as raw tables. Experiment copies never alter the source.
No fault labels/answer keys are exposed to the planner.
"""
import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb
import sqlglot
from sqlglot import exp

from .engines import public_source
from .store import now, uid

ORIGIN = 'https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce'
FILES = {f'olist_{name}_dataset.csv': name for name in (
    'orders', 'order_items', 'order_payments', 'order_reviews', 'customers',
    'products', 'sellers', 'geolocation')}
FILES['product_category_name_translation.csv'] = 'category_translation'
STAGING = '''SELECT order_id, customer_id, order_status,
    TRY_CAST(order_purchase_timestamp AS TIMESTAMP) AS purchased_at,
    TRY_CAST(order_delivered_customer_date AS TIMESTAMP) AS delivered_at,
    TRY_CAST(order_estimated_delivery_date AS TIMESTAMP) AS estimated_at
    FROM raw_orders'''
FACT = '''WITH items AS (
 SELECT order_id, SUM(TRY_CAST(price AS DECIMAL(18,2))) AS item_amount,
 SUM(TRY_CAST(freight_value AS DECIMAL(18,2))) AS freight_amount,
 COUNT(*) AS item_count FROM raw_order_items GROUP BY order_id),
 payments AS (SELECT order_id, SUM(TRY_CAST(payment_value AS DECIMAL(18,2))) AS payment_amount
 FROM raw_order_payments GROUP BY order_id)
 SELECT o.*, COALESCE(i.item_amount,0) AS item_amount,
 COALESCE(i.freight_amount,0) AS freight_amount, COALESCE(i.item_count,0) AS item_count,
 COALESCE(p.payment_amount,0) AS payment_amount,
 DATE_DIFF('day',o.purchased_at,o.delivered_at) AS delivery_days,
 CASE WHEN o.order_status='delivered' AND o.delivered_at IS NOT NULL AND o.estimated_at IS NOT NULL
 THEN CAST(o.delivered_at AS DATE)<=CAST(o.estimated_at AS DATE) END AS on_time
 FROM stg_orders o LEFT JOIN items i USING(order_id) LEFT JOIN payments p USING(order_id)'''
MART = '''SELECT CAST(purchased_at AS DATE) AS purchase_date, COUNT(*) AS delivered_orders,
 SUM(item_amount) AS delivered_gmv, SUM(freight_amount) AS freight_amount,
 SUM(payment_amount) AS payment_amount FROM fct_orders
 WHERE order_status='delivered' GROUP BY 1'''

METRICS = [
    {'id': 'delivered_gmv', 'name': 'Delivered GMV / 已交付商品成交额', 'expression': 'SUM(item_amount)', 'filter': "order_status='delivered'", 'unit': 'BRL', 'grain': 'order', 'table': 'fct_orders', 'date': 'purchased_at', 'excludes': ['freight', 'canceled orders'], 'description': 'Goods value, not platform revenue or profit. 商品金额，不是平台收入或利润。'},
    {'id': 'aov', 'name': 'Average order value / 客单价', 'expression': 'SUM(item_amount)/NULLIF(COUNT(*),0)', 'filter': "order_status='delivered'", 'unit': 'BRL/order', 'grain': 'order', 'table': 'fct_orders', 'date': 'purchased_at'},
    {'id': 'cancellation_rate', 'name': 'Cancellation rate / 取消率', 'expression': "SUM(CASE WHEN order_status='canceled' THEN 1 ELSE 0 END)*1.0/NULLIF(COUNT(*),0)", 'filter': 'all statuses', 'unit': 'fraction', 'grain': 'order', 'table': 'fct_orders', 'date': 'purchased_at'},
    {'id': 'on_time_rate', 'name': 'On-time delivery rate / 准时交付率', 'expression': 'AVG(CAST(on_time AS INTEGER))', 'filter': "order_status='delivered' AND on_time IS NOT NULL", 'unit': 'fraction', 'grain': 'order', 'table': 'fct_orders', 'date': 'purchased_at'},
    {'id': 'delivery_days', 'name': 'Average delivery days / 平均交付天数', 'expression': 'AVG(delivery_days)', 'filter': "order_status='delivered' AND delivery_days>=0", 'unit': 'calendar days', 'grain': 'order', 'table': 'fct_orders', 'date': 'purchased_at'},
]


def lineage(sql):
    tree = sqlglot.parse_one(sql, read='duckdb')
    aliases = {c.alias for c in tree.find_all(exp.CTE)}
    return sorted({t.name for t in tree.find_all(exp.Table) if t.name not in aliases})


def materialize(db, name, sql, version=1, input_version=1):
    db.execute(f'CREATE OR REPLACE TABLE "{name}" AS {sql}')
    count = db.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
    db.execute('INSERT INTO etl_runs VALUES (?,?,?,?,?,?)',
               [name, version, input_version, now(), count, 'success'])
    return {'table': name, 'sql': sql, 'upstream': lineage(sql), 'version': version}


def tables(db):
    return [{'name': name, 'schema': '', 'columns': [{'name': c[0], 'type': c[1]}
            for c in db.execute(f'DESCRIBE "{name}"').fetchall()],
            'rows': db.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]}
            for (name,) in db.execute('SHOW TABLES').fetchall()]


def import_package(store, archive, name='Olist · Brazilian E-Commerce'):
    """Bounded ZIP ingestion, no extraction of paths supplied by the archive."""
    sid = uid()
    path = store.root / f'{sid}.duckdb'
    with zipfile.ZipFile(archive) as z:
        entries = [x for x in z.infolist() if not x.is_dir()]
        if not entries or len(entries) > 20 or sum(x.file_size for x in entries) > 512*1024*1024:
            raise ValueError('ZIP must contain 1–20 CSV files, at most 512 MB uncompressed.')
        if any(not x.filename.lower().endswith('.csv') for x in entries):
            raise ValueError('Only CSV files are accepted inside a data package.')
        basenames = [Path(x.filename).name for x in entries]
        if len(set(basenames)) != len(basenames):
            raise ValueError('Duplicate CSV filenames are not allowed.')
        olist = set(basenames) == set(FILES)
        used, pipeline = set(), []
        try:
            with TemporaryDirectory(dir=store.root) as temp, duckdb.connect(str(path)) as db:
                db.execute("SET memory_limit='512MB'")
                db.execute("SET threads=2")
                for n, entry in enumerate(entries):
                    base = Path(entry.filename).name
                    table = 'raw_' + FILES[base] if olist else re.sub('[^a-zA-Z0-9_]', '_', Path(base).stem)[:60]
                    if not table or table.lower() in used:
                        raise ValueError('CSV filenames must produce distinct table names.')
                    used.add(table.lower())
                    local = Path(temp) / f'{n}.csv'
                    with z.open(entry) as src, local.open('wb') as dst:
                        shutil.copyfileobj(src, dst)
                    # DuckDB's CSV parser, not a custom parser. Preserve source values.
                    db.execute(f'CREATE TABLE "{table}" AS SELECT * FROM read_csv(?, header=true, all_varchar=true)', [str(local)])
                    if len(db.execute(f'DESCRIBE "{table}"').fetchall()) > 120:
                        raise ValueError('Each CSV may contain at most 120 columns.')
                if olist:
                    db.execute('CREATE TABLE etl_runs(model VARCHAR, version INTEGER, input_version INTEGER, loaded_at VARCHAR, row_count BIGINT, status VARCHAR)')
                    for table, sql in [('stg_orders', STAGING), ('fct_orders', FACT), ('mart_daily_sales', MART)]:
                        pipeline.append(materialize(db, table, sql))
                metadata = tables(db)
        except Exception:
            path.unlink(missing_ok=True)
            raise
    with open(archive, 'rb') as archive_file:
        archive_hash = hashlib.file_digest(archive_file, 'sha256').hexdigest()
    source = {'id': sid, 'name': name[:100], 'kind': 'warehouse' if olist else 'package',
              'dialect': 'duckdb', 'path': str(path), 'tables': metadata, 'created_at': now(),
              'description': 'Olist: anonymized historical Brazilian commerce, 2016–2018, BRL. No cost/refund data. Historical coverage is not a complete current operational feed.' if olist else 'Multi-table CSV package; field meanings require confirmation.',
              'pipeline': pipeline, 'dataset': 'olist' if olist else None, 'experiment': False,
              'metrics': METRICS if olist else [],
              'metrics_context_version': 1,
              'provenance': {'url': ORIGIN, 'license': 'CC BY-NC-SA 4.0'} if olist else {},
              'archive_sha256': archive_hash}
    store.save_source(source)
    if olist:
        store.save_business_context(sid, {
            'notes': 'Historical Olist snapshot, BRL, 2016–2018. No reliable refunds, cost or ad spend: net revenue, profit and ROI cannot be computed. 历史匿名电商快照；没有可靠退款、成本、投放数据，不能计算净收入、利润或ROI。 Boundary months may be partial; min/max timestamps do not prove completeness.',
            'fields': 'fct_orders: one row per order. purchased_at is purchase time; delivered_at is actual delivery. raw amounts are strings; use TRY_CAST(... AS DECIMAL(18,2)). customer_unique_id identifies returning buyers; customer_id identifies order-specific customer records. 原始金额为文本，先转DECIMAL；复购用customer_unique_id。',
            'metrics': 'Delivered GMV / 已交付商品成交额 = SUM(fct_orders.item_amount) WHERE order_status=delivered, excluding freight, grouped by purchase date. AOV / 客单价 = delivered GMV / delivered order count. Cancellation rate / 取消率 = canceled orders / all orders by purchase date. On-time rate / 准时交付率 = on_time true / delivered orders with non-null on_time. Delivery days / 交付天数 = purchase-to-delivery calendar day difference, only delivered orders with valid timestamps. GMV is not platform revenue or profit. Unqualified revenue/net revenue requires clarification.',
            'relationships': 'raw_orders.order_id and fct_orders.order_id must be unique. raw_order_items grain=(order_id,order_item_id); payments may have multiple rows per order; reviews and geolocation can repeat join keys. Aggregate children BEFORE joining. raw_customers.customer_id joins orders.customer_id; raw_products.product_id joins items.product_id; raw_sellers.seller_id joins items.seller_id. 多对多关联会放大金额，支付和明细必须各自按订单预聚合。'})
    return public_source(source)


def create_experiment(store, source_id, fault):
    if fault not in ('control', 'fanout', 'missing_partition', 'status_filter', 'stale_mart'):
        raise ValueError('Unknown experiment.')
    original = store.source(source_id)
    if original.get('dataset') != 'olist' or original.get('experiment'):
        raise ValueError('Create experiments from the original Olist warehouse.')
    sid = uid()
    path = store.root / f'{sid}.duckdb'
    shutil.copy2(original['path'], path)
    source = {**original, 'id': sid, 'path': str(path), 'name': 'Olist · 实验副本 / Experiment',
              'experiment': True, 'created_at': now(), 'pipeline': [dict(p) for p in original['pipeline']]}
    with duckdb.connect(str(path)) as db:
        if fault == 'missing_partition':
            day = db.execute('SELECT CAST(purchased_at AS DATE) FROM stg_orders GROUP BY 1 ORDER BY COUNT(*) DESC,1 LIMIT 1').fetchone()[0]
            source['pipeline'][0] = materialize(db, 'stg_orders', STAGING + f" WHERE CAST(order_purchase_timestamp AS DATE) <> DATE '{day}'", 2)
            source['pipeline'][1] = materialize(db, 'fct_orders', FACT, 2, 2)
            source['pipeline'][2] = materialize(db, 'mart_daily_sales', MART, 2, 2)
        elif fault == 'fanout':
            broken = FACT.replace('FROM raw_order_items GROUP BY order_id', 'FROM raw_order_items JOIN raw_order_payments USING(order_id) GROUP BY order_id')
            source['pipeline'][1] = materialize(db, 'fct_orders', broken, 2)
            source['pipeline'][2] = materialize(db, 'mart_daily_sales', MART, 2, 2)
        elif fault == 'status_filter':
            source['pipeline'][2] = materialize(db, 'mart_daily_sales', MART.replace("WHERE order_status='delivered'", ''), 2)
        elif fault == 'stale_mart':
            target = db.execute("SELECT order_id FROM fct_orders WHERE order_status='delivered' AND item_amount>0 ORDER BY order_id LIMIT 1").fetchone()[0]
            db.execute('UPDATE raw_order_items SET price=CAST(TRY_CAST(price AS DECIMAL(18,2))+100 AS VARCHAR) WHERE order_id=?', [target])
            source['pipeline'][1] = materialize(db, 'fct_orders', FACT, 2)
        source['tables'] = tables(db)
    store.save_source(source)
    store.save_business_context(sid, store.business_context(source_id))
    # Only the evaluation harness knows the requested fault; it is not persisted in source context.
    return public_source(source)


CHECKS = [
    ('order_grain', 'stg_orders', 'Order keys must be unique', 'SELECT COUNT(*)-COUNT(DISTINCT order_id) FROM stg_orders'),
    ('raw_coverage', 'stg_orders', 'Raw orders missing from staging', 'SELECT COUNT(*) FROM raw_orders r LEFT JOIN stg_orders s USING(order_id) WHERE s.order_id IS NULL'),
    ('fact_amount', 'fct_orders', 'Orders whose item amount differs from independent raw item aggregation', '''WITH expected AS (SELECT order_id,SUM(TRY_CAST(price AS DECIMAL(18,2))) amount FROM raw_order_items GROUP BY order_id) SELECT COUNT(*) FROM fct_orders f LEFT JOIN expected e USING(order_id) WHERE ABS(f.item_amount-COALESCE(e.amount,0))>0.005'''),
    ('mart_reconcile', 'mart_daily_sales', 'Daily report differs from delivered-order fact totals', '''WITH expected AS (SELECT CAST(purchased_at AS DATE) purchase_date,COUNT(*) n,SUM(item_amount) g FROM fct_orders WHERE order_status='delivered' GROUP BY 1) SELECT COUNT(*) FROM expected e FULL OUTER JOIN mart_daily_sales m USING(purchase_date) WHERE COALESCE(e.n,0)<>COALESCE(m.delivered_orders,0) OR ABS(COALESCE(e.g,0)-COALESCE(m.delivered_gmv,0))>0.005'''),
    ('freshness', 'mart_daily_sales', 'Mart input version must match current fact version', '''SELECT CASE WHEN (SELECT input_version FROM etl_runs WHERE model='mart_daily_sales' ORDER BY version DESC LIMIT 1)=(SELECT MAX(version) FROM etl_runs WHERE model='fct_orders') THEN 0 ELSE 1 END'''),
]


def run_checks(engines, source):
    checks = []
    for cid, table, label, sql in CHECKS:
        try:
            result = engines.query(source, sql)
            passed = result['rows'] == [[0]]
            checks.append({'id': cid, 'table': table, 'label': label, 'status': 'pass' if passed else 'fail', **result})
        except Exception:
            checks.append({'id': cid, 'table': table, 'label': label, 'status': 'unavailable'})
    return {'checks': checks, 'scope': 'Checks compare this local snapshot and its SQL pipeline; they cannot prove source-system completeness.',
            'passed': all(c['status'] == 'pass' for c in checks)}
