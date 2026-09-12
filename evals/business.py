from pathlib import Path

import duckdb

from backend.store import now

CONTEXT = {
    'notes': '合成零售订单，日期范围 2026 年。业务收入仅统计 status=paid 且 is_test=false 的订单。取消量可显式统计 cancelled。测试订单始终排除。退款归属原订单日期，不按退款日期过滤。Synthetic retail orders in 2026. Revenue uses paid, non-test orders only. Explicit cancellation questions may count cancelled orders. Always exclude test orders. Attribute refunds to the original order date.',
    'fields': 'orders.order_id 唯一订单号 / unique order ID; order_date 订单日期 / order date; region 地区 / region; amount_cents 订单原始金额（分）/ gross amount in cents; status: paid/cancelled/pending; is_test 测试标记 / test flag. refunds.refund_id 唯一退款号 / unique refund ID; amount_cents 退款金额（分）/ refund amount in cents; status: completed/pending/failed. items.quantity 件数 / units. 数据无成本字段 / No cost field is available.',
    'metrics': '净收入 / Net revenue = (有效订单 amount_cents 合计 - 对应 completed 退款 amount_cents 合计)/100，单位 CNY。毛收入 / Gross revenue = 有效订单 amount_cents 合计/100，单位 CNY。退款金额 / Completed refunds = 仅有效订单的 completed 退款合计/100。有效订单数 / Eligible orders = paid 且非测试订单数量。平均客单价 / Average order value = 毛收入/有效订单数，保留两位小数。已退款订单数 / Refunded order count = 有 completed 退款的有效订单去重数。All monetary output is CNY rounded to two decimals unless explicitly requested in cents. Dates include the start and exclude the next period start. Profit cannot be computed without costs.',
    'relationships': 'orders.order_id = refunds.order_id 是一对多；orders.order_id = items.order_id 是一对多。One order can have multiple refund and item rows. Aggregate completed refunds per order before joining. Joining item details must not multiply order amounts. Every item belongs to an order.',
}

FIXTURE_SQL = '''
CREATE TABLE orders (order_id INTEGER, order_date DATE, region VARCHAR, amount_cents INTEGER, status VARCHAR, is_test BOOLEAN);
INSERT INTO orders VALUES
(1,'2026-01-01','east',10000,'paid',false),
(2,'2026-01-31','west',20000,'paid',false),
(3,'2026-02-01','east',30000,'cancelled',false),
(4,'2026-03-31','east',40000,'paid',false),
(5,'2026-04-01','west',50000,'paid',false),
(6,'2026-06-30','east',60000,'paid',false),
(7,'2026-07-01','west',70000,'paid',false),
(8,'2026-12-31','east',80000,'paid',true),
(9,'2026-01-15','west',90000,'pending',false);
CREATE TABLE refunds (refund_id INTEGER, order_id INTEGER, amount_cents INTEGER, status VARCHAR);
INSERT INTO refunds VALUES
(1,1,2000,'completed'),(2,1,1000,'completed'),(3,2,5000,'pending'),
(4,4,10000,'completed'),(5,5,5000,'completed'),(6,6,10000,'completed'),(7,6,5000,'failed');
CREATE TABLE items (item_id INTEGER, order_id INTEGER, quantity INTEGER);
INSERT INTO items VALUES (1,1,1),(2,1,2),(3,2,4),(4,4,2),(5,5,5),(6,6,6),(7,7,7),(8,3,3),(9,8,8);
'''

ELIGIBLE = "o.status='paid' AND o.is_test=false"
REFUNDS = "LEFT JOIN (SELECT order_id, SUM(amount_cents) AS refund_cents FROM refunds WHERE status='completed' GROUP BY order_id) r ON o.order_id=r.order_id"
NET = 'ROUND(SUM(o.amount_cents-COALESCE(r.refund_cents,0))/100.0,2)'


def net_sql(extra=''):
    return f'SELECT {NET} AS net_revenue FROM orders o {REFUNDS} WHERE {ELIGIBLE}' + extra


def case(identifier, zh, en, sql, rows, override=None):
    return {'id': identifier, 'zh-CN': zh, 'en-US': en, 'sql': sql, 'rows': rows, 'context_override': override}


CASES = [
    case('net_revenue', '全年的净收入是多少？', 'What is total net revenue for the year?', net_sql(), [[2220.0]]),
    case('gross_revenue', '全年的毛收入是多少元？', 'What is total gross revenue in CNY for the year?', f'SELECT ROUND(SUM(o.amount_cents)/100.0,2) FROM orders o WHERE {ELIGIBLE}', [[2500.0]]),
    case('completed_refunds', '有效订单已完成退款共多少元？', 'What is the completed refund amount for eligible orders in CNY?', f"SELECT ROUND(SUM(r.amount_cents)/100.0,2) FROM refunds r JOIN orders o ON r.order_id=o.order_id WHERE {ELIGIBLE} AND r.status='completed'", [[280.0]]),
    case('eligible_count', '有效订单一共有多少笔？', 'How many eligible orders are there?', f'SELECT COUNT(*) FROM orders o WHERE {ELIGIBLE}', [[6]]),
    case('average_value', '平均客单价是多少元，保留两位小数？', 'What is average order value in CNY rounded to two decimals?', f'SELECT ROUND(AVG(o.amount_cents)/100.0,2) FROM orders o WHERE {ELIGIBLE}', [[416.67]]),
    case('q1_gross', '第一季度毛收入是多少元？', 'What is Q1 gross revenue in CNY?', f"SELECT ROUND(SUM(o.amount_cents)/100.0,2) FROM orders o WHERE {ELIGIBLE} AND order_date>='2026-01-01' AND order_date<'2026-04-01'", [[700.0]]),
    case('q1_net', '第一季度净收入是多少元？', 'What is Q1 net revenue in CNY?', net_sql(" AND order_date>='2026-01-01' AND order_date<'2026-04-01'"), [[570.0]]),
    case('q2_net', '第二季度净收入是多少元？', 'What is Q2 net revenue in CNY?', net_sql(" AND order_date>='2026-04-01' AND order_date<'2026-07-01'"), [[950.0]]),
    case('july_boundary', '7 月 1 日当天净收入是多少元？', 'What is net revenue in CNY on July 1?', net_sql(" AND order_date='2026-07-01'"), [[700.0]]),
    case('regional_net', '按地区字母顺序列出各地区净收入（元）。', 'Show net revenue in CNY by region, ordered alphabetically by region.', f'SELECT o.region, {NET} FROM orders o {REFUNDS} WHERE {ELIGIBLE} GROUP BY o.region ORDER BY o.region', [['east',870.0],['west',1350.0]]),
    case('refunded_orders', '有已完成退款的有效订单有多少笔？不要重复计算订单。', 'How many eligible orders have completed refunds? Count each order once.', f"SELECT COUNT(DISTINCT o.order_id) FROM orders o JOIN refunds r ON o.order_id=r.order_id WHERE {ELIGIBLE} AND r.status='completed'", [[4]]),
    case('join_double_count', '有商品明细的有效订单毛收入是多少元？不要因为多条明细重复计金额。', 'What is gross revenue in CNY for eligible orders with item details? Do not duplicate amounts for multiple items.', f'SELECT ROUND(SUM(o.amount_cents)/100.0,2) FROM orders o JOIN (SELECT DISTINCT order_id FROM items) i ON o.order_id=i.order_id WHERE {ELIGIBLE}', [[2500.0]]),
    case('quantity', '有效订单共售出多少件商品？', 'How many units were sold in eligible orders?', f'SELECT SUM(i.quantity) FROM orders o JOIN items i ON o.order_id=i.order_id WHERE {ELIGIBLE}', [[27]]),
    case('cancelled_count', '非测试的取消订单有多少笔？', 'How many non-test cancelled orders are there?', "SELECT COUNT(*) FROM orders WHERE status='cancelled' AND is_test=false", [[1]]),
    case('test_exclusion', '12 月有效订单的毛收入是多少元？无订单返回 0。', 'What is December gross revenue for eligible orders in CNY? Return zero if there are no orders.', f"SELECT COALESCE(ROUND(SUM(o.amount_cents)/100.0,2),0) FROM orders o WHERE {ELIGIBLE} AND order_date>='2026-12-01' AND order_date<'2027-01-01'", [[0.0]]),
    case('january_dates', '1 月有效订单毛收入是多少元？包括 1 月 1 日和 1 月 31 日。', 'What is eligible January gross revenue in CNY, including January 1 and January 31?', f"SELECT ROUND(SUM(o.amount_cents)/100.0,2) FROM orders o WHERE {ELIGIBLE} AND order_date>='2026-01-01' AND order_date<'2026-02-01'", [[300.0]]),
    case('pending_refund', '订单 2 的净收入是多少元？', 'What is net revenue for order 2 in CNY?', net_sql(' AND o.order_id=2'), [[200.0]]),
    case('cents_unit', '有效订单的原始金额合计是多少分？这次不要换算成元。', 'What is the sum of eligible order gross amounts in cents? Do not convert to CNY this time.', f'SELECT SUM(o.amount_cents) FROM orders o WHERE {ELIGIBLE}', [[250000]]),
    case('missing_cost', '全年的利润是多少？', 'What is annual profit?', None, None),
    case('conflicting_metric', '按业务说明计算营业额。', 'Calculate turnover using the business definitions.', None, None,
         {'metrics': '营业额 / turnover 定义 A：全部有效订单的毛收入。定义 B：全部有效订单的净收入。两种定义并存，尚未确定采用哪个。Turnover has two conflicting definitions: gross revenue and net revenue. Neither is preferred.'}),
]


def seed_business(store):
    path = Path(store.root) / 'business-evaluation.duckdb'
    if path.exists():
        raise ValueError('Evaluation fixture requires a fresh data directory.')
    with duckdb.connect(str(path)) as db:
        db.execute(FIXTURE_SQL)
        tables = [{'name': name, 'schema': '', 'columns': [{'name': c[0], 'type': c[1]} for c in db.execute(f'DESCRIBE {name}').fetchall()]} for name in ('orders','refunds','items')]
    source = {'id': 'business-evaluation', 'name': 'Business evaluation / 业务评测', 'kind': 'database', 'dialect': 'duckdb',
              'path': str(path), 'tables': tables, 'description': 'Synthetic retail evaluation fixture', 'created_at': now()}
    store.save_source(source)
    store.save_business_context(source['id'], CONTEXT)
    return source
