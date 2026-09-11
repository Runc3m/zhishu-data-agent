"""A constrained analytical SQL surface; every initial query and retry uses it."""
import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import traverse_scope

MAX_ROWS = 500
TIMEOUT_SECONDS = 8
SAFE_FUNCTIONS = set('''ABS AVG COUNT SUM MIN MAX ROUND FLOOR CEIL CEILING COALESCE NULLIF IFNULL
    UPPER LOWER LENGTH CHAR_LENGTH TRIM LTRIM RTRIM SUBSTRING SUBSTR REPLACE CONCAT CONCAT_WS
    CAST TRY_CAST DATE DATE_TRUNC DATE_PART EXTRACT STRFTIME STRPTIME TRY_STRPTIME DATE_FORMAT
    YEAR MONTH DAY QUARTER WEEK DAYOFMONTH DAYOFWEEK CURRENT_DATE CURRENT_TIMESTAMP NOW
    DATE_ADD DATE_SUB DATEDIFF DATE_DIFF TIMESTAMPDIFF TO_CHAR TO_DATE TO_TIMESTAMP
    ROW_NUMBER RANK DENSE_RANK LAG LEAD FIRST_VALUE LAST_VALUE NTILE PERCENT_RANK CUME_DIST
    STDDEV STDDEV_POP STDDEV_SAMP VARIANCE VAR_POP VAR_SAMP MEDIAN QUANTILE_CONT PERCENTILE_CONT
    GREATEST LEAST POWER POW SQRT LOG LN EXP MOD SIGN IF IIF CASE ARRAY_AGG STRING_AGG GROUP_CONCAT
    BOOL_AND BOOL_OR EVERY ISNULL STARTS_WITH ENDS_WITH REGEXP_REPLACE REGEXP_MATCHES
    TIME_TO_STR TS_OR_DS_TO_DATE TS_OR_DS_TO_DATE_STR TS_OR_DS_TO_TIMESTAMP
    TIMESTAMP_TRUNC TIMESTAMP_DIFF TIME_STR_TO_TIME STR_TO_DATE STR_TO_TIME
    TIME_TO_UNIX UNIX_TO_TIME ADD_MONTHS MONTHS_BETWEEN'''.split())


def validate_sql(sql: str, dialect: str, tables: list[dict]) -> str:
    if len(sql) > 30000:
        raise ValueError('SQL 过长。')
    try:
        parsed = [p for p in sqlglot.parse(sql, read=dialect) if p is not None]
    except sqlglot.errors.ParseError as e:
        raise ValueError('SQL 语法不完整，请调整问题。') from e
    if len(parsed) != 1 or not isinstance(parsed[0], (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        raise ValueError('只允许单条只读 SELECT 查询。')
    tree = parsed[0]
    banned = (exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop, exp.Alter,
              exp.Command, exp.Into, exp.Lock, exp.Copy, exp.Merge)
    for node in tree.walk():
        if isinstance(node, banned):
            raise ValueError('查询包含写入、导出或锁定操作。')
        if isinstance(node, exp.With) and node.args.get('recursive'):
            raise ValueError('暂不支持递归查询。')
        if isinstance(node, exp.Func):
            name = node.name.upper() if isinstance(node, exp.Anonymous) else node.sql_name().upper()
            if name not in SAFE_FUNCTIONS:
                raise ValueError(f'分析查询暂不支持函数 {name}。')
            if isinstance(node.parent, exp.Dot):
                raise ValueError('不允许调用自定义命名空间函数。')
    allowed = {(t.get('schema', ''), t['name']) for t in tables}
    for scope in traverse_scope(tree):
        for source in scope.sources.values():
            if not isinstance(source, exp.Table):
                continue
            if not isinstance(source.this, exp.Identifier) or source.catalog:
                raise ValueError('禁止读取外部文件、跨库数据或表函数。')
            pair = (source.db, source.name)
            if pair not in allowed:
                raise ValueError(f'表 {source.name} 不在当前数据源的授权范围内。')
    # Reject table-valued functions even if an optimizer scope omits them.
    for table in tree.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            raise ValueError('不允许表函数或外部文件查询。')
    # Over-fetch one row to accurately report truncation without a second query.
    normalized = tree.sql(dialect=dialect)
    return f'SELECT * FROM ({normalized}) AS _agent_result LIMIT {MAX_ROWS + 1}'
