"""Known warehouse grain contracts, checked with SQLGlot before BI execution.

This deliberately narrow guard does not certify arbitrary SQL semantics. Diagnostic
tools may inspect broken joins; ordinary BI queries must respect these contracts.
"""
import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import traverse_scope


OLIST_ANALYSIS_GUIDE = '''
Olist analysis grain contract (schema semantics; does not override confirmed metric definitions):
fct_orders has ONE row per order. raw_order_items has ONE row per item, with numeric prices stored as text.
For category/product/seller GMV use SUM(TRY_CAST(i.price AS DECIMAL(18,2))), NOT SUM(f.item_amount).
For units use COUNT(*) at raw_order_items grain, NOT SUM(f.item_count) after the join.
Orders per category = COUNT(DISTINCT i.order_id); category AOV = category item-price sum / distinct category orders.
An order can contain multiple categories: category order counts are NOT additive across categories.
For monthly trends, select the top 5 categories in a separate whole-period aggregate CTE, then query ALL months
for those categories (well below 500 rows). Do not LIMIT the month/category rows to the earliest 300 rows.
If comparing GMV winners with order/unit winners, independently rank by each metric; do not infer the
population's order/unit leader from a list truncated by GMV. GMV is goods value, never platform revenue.
For order-weighted delivery metrics first SELECT DISTINCT category, f.order_id, f.delivery_days, f.on_time
in a CTE, then aggregate the CTE; exclude NULL on_time and invalid delivery_days.
Never SUM/AVG order-level amounts, counts, or delivery measures after joining raw_order_items.
Safe category template:
SELECT COALESCE(t.product_category_name_english,p.product_category_name,'unknown') AS category,
ROUND(SUM(TRY_CAST(i.price AS DECIMAL(18,2))),2) AS delivered_gmv,
COUNT(DISTINCT i.order_id) AS delivered_orders, COUNT(*) AS item_units
FROM raw_order_items i JOIN fct_orders f ON f.order_id=i.order_id
JOIN raw_products p ON p.product_id=i.product_id
LEFT JOIN raw_category_translation t ON t.product_category_name=p.product_category_name
WHERE f.order_status='delivered'
GROUP BY 1 ORDER BY delivered_gmv DESC LIMIT 15
'''


def validate_analysis_grain(source, sql):
    if source.get('dataset') != 'olist':
        return
    tree = sqlglot.parse_one(sql, read=source['dialect'])
    measures = {'item_amount', 'freight_amount', 'payment_amount', 'item_count', 'delivery_days', 'on_time'}
    for scope in traverse_scope(tree):
        tables = {alias.lower(): table.name.lower() for alias, table in scope.sources.items() if isinstance(table, exp.Table)}
        facts = {alias for alias, name in tables.items() if name == 'fct_orders'}
        if not facts or 'raw_order_items' not in tables.values():
            continue
        for aggregate in scope.expression.find_all(exp.AggFunc):
            if aggregate.find_ancestor(exp.Select) is not scope.expression:
                continue
            if isinstance(aggregate, (exp.Sum, exp.Avg)) and any(c.name.lower() in measures and
                    (not c.table or c.table.lower() in facts) for c in aggregate.find_all(exp.Column)):
                raise ValueError('Order-grain measure would be duplicated/weighted by item rows. For category GMV use SUM(TRY_CAST(i.price AS DECIMAL(18,2))); for units COUNT(*); for delivery first deduplicate order/category in a CTE.')
            alias = aggregate.find_ancestor(exp.Alias)
            if isinstance(aggregate, exp.Count) and isinstance(aggregate.this, exp.Star) and alias and ('order' in alias.alias.lower() or '订单' in alias.alias):
                raise ValueError('COUNT(*) counts item rows after this join. Use COUNT(DISTINCT f.order_id) for orders.')
