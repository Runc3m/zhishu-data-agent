"""Behavior regressions for conversational BI; live-model tests remain opt-in."""
import json

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.agent import parse_plan
from backend.analyst import is_explanation
from backend.charts import chart_spec


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'storage')) as c:
        c.app.state.store.save_settings({'mode': 'llm', 'provider': 'custom', 'base_url': 'https://example.com', 'model': 'mock'})
        yield c


def ask(client, cid, question):
    response = client.post(f'/api/conversations/{cid}/messages', json={'content': question})
    events = [json.loads(s[6:]) for s in response.text.splitlines() if s.startswith('data: ')]
    assert not any(e['type'] == 'error' for e in events), events
    return next(e['result'] for e in events if e['type'] == 'result')


def model_replies(monkeypatch, replies):
    calls = []
    iterator = iter(replies)
    def model(settings, messages, **kwargs):
        calls.append(messages)
        return next(iterator)
    monkeypatch.setattr('backend.agent.call_model', model)
    return calls


REPORT = json.dumps({'conclusion': '按销售额比较，范围为已返回数据。', 'findings': ['见查询 [1]。'],
    'actions': ['先小规模验证选品策略，追踪销售额与毛利。'], 'limitations': ['缺少库存。'], 'followups': ['按月拆分呢？']}, ensure_ascii=False)


def test_broad_question_runs_complementary_queries_and_retains_evidence(client, monkeypatch):
    cid = client.post('/api/conversations', json={'source_id': 'demo-sales'}).json()['id']
    plan = {'action': 'analysis', 'explanation': '先按品类销售额比较，再看月度趋势。', 'queries': [
        {'sql': 'SELECT category, SUM(sales) AS revenue FROM sales GROUP BY 1 ORDER BY 2 DESC', 'chart_type': 'horizontal_bar'},
        {'sql': "SELECT strftime(order_date, '%Y-%m') AS month, SUM(sales) AS revenue FROM sales GROUP BY 1 ORDER BY 1", 'chart_type': 'area'}]}
    calls = model_replies(monkeypatch, [json.dumps(plan), REPORT, REPORT, REPORT])
    result = ask(client, cid, '哪个卖的最好')
    assert len(result['panels']) == 2
    assert len(result['panels'][0]['rows']) == 4
    assert len(result['panels'][1]['rows']) == 8
    assert result['panels'][1]['chart']['type'] == 'area'
    assert result['report']['actions']
    explanation = ask(client, cid, '看不懂，解释一下')
    assert explanation['response_kind'] == 'explain' and not explanation.get('sql')
    assert 'SELECT category' in calls[-1][-1]['content']
    assert explanation['based_on_message_id']
    ask(client, cid, '讲简单点')
    assert 'SELECT category' in calls[-1][-1]['content']


def test_explain_without_history_is_helpful_and_needs_no_model(client, monkeypatch):
    monkeypatch.setattr('backend.agent.call_model', lambda *a, **kw: pytest.fail('No model needed'))
    cid = client.post('/api/conversations', json={'source_id': 'demo-sales'}).json()['id']
    assert ask(client, cid, '看不懂，解释一下')['response_kind'] == 'clarify'


def test_single_query_explanation_uses_actual_rows(client, monkeypatch):
    cid = client.post('/api/conversations', json={'source_id': 'demo-sales'}).json()['id']
    calls = model_replies(monkeypatch, ['{"sql":"SELECT COUNT(*) AS orders FROM sales","chart_type":"kpi"}', 'There are 720 orders.', REPORT])
    first = ask(client, cid, '共有多少订单')
    assert first['chart']['type'] == 'kpi'
    ask(client, cid, 'Explain this')
    payload = json.loads(calls[-1][-1]['content'])
    assert payload['previous_result']['query']['rows'] == [[720]]


def test_invalid_plan_is_repaired_and_never_executes_prose(client, monkeypatch):
    cid = client.post('/api/conversations', json={'source_id': 'demo-sales'}).json()['id']
    calls = model_replies(monkeypatch, ['自然语言', 'still not JSON'])
    result = ask(client, cid, '哪个卖的最好')
    assert not result.get('error') and not result.get('sql')
    assert '销售额' in result['answer'] and len(calls) == 2


def test_analysis_cannot_write_and_partial_results_are_visible(client, monkeypatch):
    cid = client.post('/api/conversations', json={'source_id': 'demo-sales'}).json()['id']
    plan = {'action': 'analysis', 'queries': [{'sql': 'DELETE FROM sales', 'explanation': 'bad'}, {'sql': 'SELECT COUNT(*) AS n FROM sales'}]}
    model_replies(monkeypatch, [json.dumps(plan), '{"sql":"DELETE FROM sales"}', REPORT])
    result = ask(client, cid, '综合分析')
    assert result['incomplete'] and result['panels'][0]['rows'] == [[720]]


@pytest.mark.parametrize('q', ['看不懂，解释一下', '解释一下', 'Explain this', "I don’t understand", '解释一下。'])
def test_context_only_intents(q):
    assert is_explanation(q)


def test_explanation_with_new_filter_must_plan():
    assert not is_explanation('解释一下 2018 年与 2017 年的销售差异')


def test_plan_accepts_wrapped_json_and_unknown_chart_falls_back():
    plan = parse_plan('Here is the plan:\n```json\n{"sql":null,"explanation":"Which metric?","chart_type":"radar"}\n```')
    assert chart_spec({'columns': ['category', 'value'], 'rows': [['A', 10], ['B', 20]]}, plan.chart_type)['type'] == 'bar'


def test_chart_shapes_and_negative_shares():
    assert chart_spec({'columns': ['value'], 'rows': [[7]]})['type'] == 'kpi'
    assert chart_spec({'columns': ['x', 'y'], 'rows': [[1, 2], [3, 4]]}, 'scatter')['type'] == 'scatter'
    heat = chart_spec({'columns': ['month', 'region', 'sales'], 'rows': [['Jan', 'A', 1], ['Jan', 'B', 2]]}, 'heatmap')
    assert heat['type'] == 'heatmap' and 'line' in heat['available']
    neg = chart_spec({'columns': ['category', 'value'], 'rows': [['A', -2], ['B', 3]]}, 'pie')
    assert neg['type'] == 'bar' and 'pie' not in neg['available']
    assert chart_spec({'columns': ['value'], 'rows': [[1], [2], [3]]})['type'] == 'histogram'


@pytest.mark.parametrize('measure', ['SUM(f.item_amount)', 'SUM(f.item_count)', 'AVG(f.delivery_days)', 'SUM(item_amount)'])
def test_order_measures_cannot_fan_out_on_item_join(measure):
    from backend.grain import validate_analysis_grain
    with pytest.raises(ValueError, match='duplicated/weighted'):
        validate_analysis_grain({'dataset': 'olist', 'dialect': 'duckdb'},
            f'SELECT {measure} FROM fct_orders f JOIN raw_order_items i ON f.order_id=i.order_id')


def test_item_grain_and_deduplicated_order_metrics_are_allowed():
    from backend.grain import validate_analysis_grain
    source = {'dataset': 'olist', 'dialect': 'duckdb'}
    validate_analysis_grain(source, 'SELECT SUM(CAST(i.price AS DOUBLE)), COUNT(DISTINCT f.order_id) FROM fct_orders f JOIN raw_order_items i ON f.order_id=i.order_id')
    validate_analysis_grain(source, 'WITH d AS (SELECT DISTINCT f.order_id, f.delivery_days FROM fct_orders f JOIN raw_order_items i ON f.order_id=i.order_id) SELECT AVG(delivery_days) FROM d')


def test_report_object_cannot_silently_become_empty_plan():
    with pytest.raises(ValueError):
        parse_plan(REPORT)
    with pytest.raises(ValueError):
        parse_plan('{}')


def test_malformed_report_never_leaks_json_into_chat():
    from backend.analyst import make_report
    malformed = '{"conclusion":"Money and units have different leaders.","findings":["Money: A","Units: B","Extra"]},"actions":["Unneeded"]}'
    answer, report = make_report(lambda *a, **kw: malformed, {}, 'Explain this simply', [], {}, 'en-US')
    assert report['conclusion'] == 'Money and units have different leaders.'
    assert len(report['findings']) == 2 and report['actions'] == []
    assert '"conclusion"' not in answer and 'Unneeded' not in answer
    answer, report = make_report(lambda *a, **kw: '{"conclusion":"A is highest.","findings": [', {}, 'Explain this', [], {}, 'en-US')
    assert answer == 'A is highest.'
