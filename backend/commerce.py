"""Reproducible commerce investigation: synthetic data, executed SQL, no model."""
from datetime import date, timedelta

import duckdb

from .store import now
from .knowledge import retrieve

QUESTION_ZH = '分析 2026 年 8 月相较 7 月的净销售额变化，找出贡献最大的品类，并检查退款变化。'
QUESTION_EN = 'Analyze the change in net sales from July to August 2026, identify the largest category contribution, and check refunds.'
CONTEXT = {
    'notes': '合成教学数据，非真实经营数据。每日每品类一笔 paid 订单，完整覆盖 2026-07-01 至 2026-08-31；9 月尚未导入。Synthetic teaching data, not real business data. One paid order per category per day; July and August 2026 are fully loaded. September is not loaded.',
    'fields': 'orders: order_id 唯一订单号 / unique ID, order_date 订单日期 / order date, category 品类 / category, amount_cents 金额（分）/ amount in cents, status paid/cancelled. refunds: refund_id 唯一退款号 / unique refund ID, order_id, amount_cents, status completed/pending.',
    'metrics': '净销售额 / net sales = (paid 订单金额 - 对应 completed 退款金额)/100，单位 CNY。毛销售额 / gross sales = paid 订单金额/100。退款归属于原订单月份。Refunds belong to the original order month. 退款率 / refund rate 尚未定义：须澄清退款金额占比还是退款订单占比。Refund rate is undefined: clarify amount share versus order share. 不提供成本或外部因果数据 / No cost or external causal data.',
    'relationships': 'orders.order_id = refunds.order_id，一对多 / one-to-many. 先按订单聚合 completed 退款再关联 / Aggregate completed refunds per order before joining to avoid multiplying order amounts.',
}


def seed_commerce(store):
    if any(s['id'] == 'demo-commerce' for s in store.sources()):
        return
    path = store.root / 'demo-commerce.duckdb'
    orders, refunds = [], []
    for day in range(62):
        when = date(2026, 7, 1) + timedelta(days=day)
        for index, category in enumerate(('Electronics', 'Home', 'Sports')):
            oid = len(orders) + 1
            amount = (10000, 6000, 4000)[index]
            if when.month == 8:
                amount += (-3000, 1000, 0)[index]
            orders.append((oid, when, category, amount, 'paid'))
            if index == 0:
                # Two completed refunds on the same order exercise join grain.
                for value in ((500, 500) if when.month == 7 else (1000, 1000)):
                    refunds.append((len(refunds) + 1, oid, value, 'completed'))
            refunds.append((len(refunds) + 1, oid, 50, 'pending'))
    orders.append((999, date(2026, 8, 15), 'Electronics', 999999, 'cancelled'))
    with duckdb.connect(str(path)) as db:
        db.execute('CREATE OR REPLACE TABLE orders (order_id INTEGER, order_date DATE, category VARCHAR, amount_cents INTEGER, status VARCHAR)')
        db.execute('CREATE OR REPLACE TABLE refunds (refund_id INTEGER, order_id INTEGER, amount_cents INTEGER, status VARCHAR)')
        db.executemany('INSERT INTO orders VALUES (?,?,?,?,?)', orders)
        db.executemany('INSERT INTO refunds VALUES (?,?,?,?)', refunds)
        tables = [{'name': name, 'schema': '', 'columns': [{'name': c[0], 'type': c[1]} for c in db.execute(f'DESCRIBE {name}').fetchall()]} for name in ('orders', 'refunds')]
    store.save_source({'id': 'demo-commerce', 'name': '电商调查演示', 'kind': 'demo', 'dialect': 'duckdb',
                       'path': str(path), 'tables': tables, 'description': 'Synthetic commerce · July–August 2026', 'created_at': now()})
    store.save_business_context('demo-commerce', CONTEXT)


def investigate(engines, source, question, business, language):
    en = language == 'en-US'
    say = lambda zh, english: english if en else zh
    empty = {'columns': [], 'rows': [], 'row_count': 0, 'chart': None, 'mode': 'demo', 'language': language}
    q = question.strip().lower().rstrip('.。?!？')
    if q not in (QUESTION_ZH.rstrip('。'), QUESTION_EN.lower().rstrip('.')):
        answer = say('规则调查仅支持建议卡中的 2026 年 7–8 月净销售额比较。其他调查请启用 AI。',
                     'Rule investigation supports the suggested July–August 2026 net-sales comparison. Enable AI for other investigations.')
        if q in ('退款率是多少', 'what is the refund rate'):
            answer = say('请明确退款率指退款金额占毛销售额，还是退款订单数占有效订单数？', 'Do you mean refunded amount divided by gross sales, or refunded orders divided by eligible orders?')
        if q in ('分析 2026 年 9 月的净销售额变化', 'analyze the net sales change in september 2026'):
            answer = say('演示数据仅覆盖 2026 年 7–8 月，9 月尚未导入，无法分析；不能把缺失月份当作零销售额。', 'Demo data covers July–August 2026 only. September is not loaded, so it cannot be analyzed or treated as zero sales.')
        yield {'type': 'investigation_result', 'result': {**empty, 'answer': answer}}
        return
    # Never imply edited business definitions were executed by fixed rules.
    if any(business.get(k) != v for k, v in CONTEXT.items()):
        yield {'type': 'investigation_result', 'result': {**empty, 'answer': say('演示业务定义已修改，请启用 AI 按新定义调查。', 'Demo definitions have changed. Enable AI to investigate using the new definitions.')}}
        return
    trace = []
    def step(label, sql):
        result = engines.query(source, sql)
        trace.append({'step': len(trace) + 1, 'label': label, **result})
        return result
    yield {'type': 'step', 'label': say('检查数据覆盖与质量', 'Check coverage and quality'), 'detail': say('按月检查缺失、重复和状态', 'Check missing values, duplicates and status by month')}
    coverage = step(say('日期覆盖与订单质量', 'Date coverage and order quality'), "SELECT strftime(order_date, '%Y-%m') AS month, COUNT(DISTINCT order_date) AS observed_days, (SELECT COUNT(*)-COUNT(DISTINCT order_id) FROM orders) AS duplicate_ids, SUM(CASE WHEN amount_cents IS NULL OR order_id IS NULL OR category IS NULL OR status IS NULL OR order_date IS NULL THEN 1 ELSE 0 END) AS missing_values, SUM(CASE WHEN status NOT IN ('paid','cancelled') THEN 1 ELSE 0 END) AS unknown_status FROM orders GROUP BY 1 ORDER BY 1")
    refund_quality = step(say('退款质量与关联', 'Refund quality and relationships'), "SELECT COUNT(*)-COUNT(DISTINCT refund_id) AS duplicate_ids, SUM(CASE WHEN refund_id IS NULL OR amount_cents IS NULL OR order_id IS NULL OR status IS NULL THEN 1 ELSE 0 END) AS missing_values, SUM(CASE WHEN status NOT IN ('completed','pending') THEN 1 ELSE 0 END) AS unknown_status, SUM(CASE WHEN order_id NOT IN (SELECT order_id FROM orders) THEN 1 ELSE 0 END) AS orphan_refunds FROM refunds")
    valid = coverage['rows'] == [['2026-07',31,0,0,0],['2026-08',31,0,0,0]] and refund_quality['rows'] == [[0,0,0,0]]
    if not valid:
        yield {'type': 'investigation_result', 'result': {**empty, 'investigation': trace, 'answer': say('数据覆盖或质量检查未通过，停止比较，请先核查明细。', 'Coverage or quality checks failed. Comparison stopped; inspect the evidence first.')}}
        return
    base = "FROM orders o LEFT JOIN (SELECT order_id, SUM(amount_cents) AS refund FROM refunds WHERE status='completed' GROUP BY order_id) r ON o.order_id=r.order_id WHERE o.status='paid' AND o.order_date>='2026-07-01' AND o.order_date<'2026-09-01'"
    net = 'o.amount_cents-COALESCE(r.refund,0)'
    yield {'type': 'step', 'label': say('比较净销售额与退款', 'Compare net sales and refunds'), 'detail': say('退款先按订单聚合，再按订单月统计', 'Aggregate refunds per order, then by order month')}
    total = step(say('总体变化', 'Overall change'), f"SELECT strftime(o.order_date, '%Y-%m') AS month, ROUND(SUM(o.amount_cents)/100.0,2) AS gross_sales, ROUND(SUM(COALESCE(r.refund,0))/100.0,2) AS refunds, ROUND(SUM({net})/100.0,2) AS net_sales {base} GROUP BY 1 ORDER BY 1")
    if [r[0] for r in total['rows']] != ['2026-07', '2026-08']:
        yield {'type': 'investigation_result', 'result': {**empty, 'investigation': trace, 'answer': say('比较月份缺少有效订单，无法完成该示例，请核查订单状态与口径。', 'A comparison month has no eligible orders. Review order status and definitions before completing this example.')}}
        return
    categories = step(say('品类变化贡献', 'Category contributions'), f"SELECT o.category, ROUND(SUM(CASE WHEN EXTRACT(MONTH FROM o.order_date)=7 THEN {net} ELSE 0 END)/100.0,2) AS july_net, ROUND(SUM(CASE WHEN EXTRACT(MONTH FROM o.order_date)=8 THEN {net} ELSE 0 END)/100.0,2) AS august_net {base} GROUP BY 1 ORDER BY 1")
    delta = round(total['rows'][1][3] - total['rows'][0][3], 2)
    changes = [[r[0], r[1], r[2], round(r[2]-r[1],2)] for r in categories['rows']]
    biggest = max(changes, key=lambda r: abs(r[3]))[0]
    # This literal is from executed data, escaped before interpolation.
    literal = biggest.replace("'", "''")
    yield {'type': 'step', 'label': say('追查主要变化品类', 'Investigate the largest contributor'), 'detail': biggest}
    detail = step(say('主要品类的订单和退款', 'Orders and refunds of the leading category'), f"SELECT strftime(o.order_date, '%Y-%m') AS month, COUNT(*) AS paid_orders, ROUND(SUM(o.amount_cents)/100.0,2) AS gross_sales, ROUND(SUM(COALESCE(r.refund,0))/100.0,2) AS refunds {base} AND o.category='{literal}' GROUP BY 1 ORDER BY 1")
    reconciled = abs(sum(r[3] for r in changes) - delta) < .005
    percent = delta / total['rows'][0][3] * 100 if total['rows'][0][3] else None
    percent_text = f'{percent:+.2f}%' if percent is not None else say('基期为零，变化率未定义', 'baseline is zero; percentage undefined')
    amount = total['rows'][1][2] - total['rows'][0][2]
    answer = say(
        f'7 月净销售额 {total["rows"][0][3]:,.2f} 元，8 月 {total["rows"][1][3]:,.2f} 元，变化 {delta:+,.2f} 元（{percent_text}）。[3]\n主要变化来自 {biggest}，变化 {next(r[3] for r in changes if r[0]==biggest):+,.2f} 元。[4] 总退款变化 {amount:+,.2f} 元。[3] 已进一步核查该品类订单数和退款。[5]\n品类贡献与总体变化核对：{"一致" if reconciled else "不一致，请核查"}。这是金额变化分解；促销、竞争等业务原因仍需额外证据。数据为合成演示数据。',
        f'Net sales: July CNY {total["rows"][0][3]:,.2f}; August CNY {total["rows"][1][3]:,.2f}; change {delta:+,.2f} ({percent_text}). [3]\nLargest contribution: {biggest}, {next(r[3] for r in changes if r[0]==biggest):+,.2f}. [4] Total refunds changed by CNY {amount:+,.2f}. [3] Its order counts and refunds were investigated. [5]\nCategory changes {"reconcile" if reconciled else "DO NOT reconcile"} to the total. This is a numerical decomposition, not proof of business causes. Promotions or competition require additional evidence. Data is synthetic.')
    result = {**categories, 'answer': answer, 'mode': 'demo', 'language': language,
              'chart': {'type': 'bar', 'x': 'category', 'y': ['july_net', 'august_net'], 'limit': 50},
              'investigation': trace, 'reconciliation': {'passed': reconciled, 'total_change': delta, 'category_change_sum': round(sum(r[3] for r in changes), 2)},
              'context_version': business['version'], 'business_context': business,
              'knowledge_sources': retrieve(business, question), 'stop_reason': 'complete',
              'notice': say('规则调查：5 次只读查询真实执行；支持固定示例，不调用模型。', 'Rule investigation: five executed read-only queries for this fixed example; no model calls.')}
    yield {'type': 'investigation_result', 'result': result}
