import json

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.agent import call_model, parse_plan, similar_examples
from backend.app import create_app
from evals.business import CONTEXT, seed_business


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'storage')) as client:
        yield client


def ask(client, cid, text, language='zh-CN'):
    response = client.post(f'/api/conversations/{cid}/messages', json={'content': text, 'language': language})
    assert response.status_code == 200
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]


def use_model(client, monkeypatch, replies):
    client.put('/api/settings', json={'mode': 'llm', 'provider': 'custom', 'base_url': 'https://example.com', 'model': 'mock'})
    calls, replies = [], iter(replies)
    def model(settings, messages, **kwargs):
        calls.append(json.loads(json.dumps(messages)))
        return next(replies)
    monkeypatch.setattr('backend.agent.call_model', model)
    return calls


def test_similarity_handles_chinese_and_english():
    examples = [{'question': '各地区净收入', 'sql': 'A'}, {'question': 'monthly refund amount', 'sql': 'B'},
                {'question': '取消订单数量', 'sql': 'C'}]
    assert [e['sql'] for e in similar_examples('华东地区的净收入是多少', examples)] == ['A']
    assert [e['sql'] for e in similar_examples('Refund amount by month', examples)] == ['B']
    assert similar_examples('平均客单价', examples) == []


def test_verify_list_retrieve_and_delete(client, monkeypatch):
    cid = client.post('/api/conversations', json={'source_id': 'demo-sales'}).json()['id']
    ask(client, cid, '各地区销售额对比')
    answer = client.get(f'/api/conversations/{cid}/messages').json()[-1]
    url = f"/api/conversations/{cid}/messages/{answer['id']}/verify"
    saved = client.post(url, json={'question': '各地区销售额对比'}).json()
    assert saved['sql'] == answer['result']['sql']
    # Re-verifying the same question replaces rather than duplicates.
    assert client.post(url, json={'question': '各地区销售额对比'}).json()['id'] == saved['id']
    assert client.post(url, json={'question': '  '}).status_code == 422
    user_message = client.get(f'/api/conversations/{cid}/messages').json()[0]
    assert client.post(f"/api/conversations/{cid}/messages/{user_message['id']}/verify", json={'question': 'x'}).status_code == 404
    assert [q['id'] for q in client.get('/api/sources/demo-sales/verified').json()] == [saved['id']]

    calls = use_model(client, monkeypatch, ['{"sql":"SELECT region, SUM(sales) FROM sales GROUP BY 1","chart_type":"bar"}', 'Done.'])
    cid = client.post('/api/conversations', json={'source_id': 'demo-sales'}).json()['id']
    events = ask(client, cid, '华东和华南地区销售额对比')
    assert any(e['type'] == 'step' and e['label'] == '参考已验证查询' for e in events)
    assert 'Verified examples:' in calls[0][0]['content'] and saved['sql'] in calls[0][0]['content']
    result = next(e['result'] for e in events if e['type'] == 'result')
    assert result['verified_examples'] == [{'question': '各地区销售额对比', 'sql': saved['sql']}]

    assert client.delete(f"/api/sources/demo-sales/verified/{saved['id']}").json() == {'ok': True}
    assert client.delete(f"/api/sources/demo-sales/verified/{saved['id']}").status_code == 400
    calls.clear()
    monkeypatch.setattr('backend.agent.call_model', lambda s, m, **k: calls.append(m) or '{"sql":null,"explanation":"?"}')
    ask(client, cid, '华东和华南地区销售额对比')
    assert 'Verified examples:' not in calls[0][0]['content']


def test_unrelated_and_demo_questions_skip_examples(client, monkeypatch):
    store = client.app.state.store
    store.add_verified_query('demo-sales', '各品类利润排名', 'SELECT category, SUM(profit) FROM sales GROUP BY 1')
    cid = client.post('/api/conversations', json={'source_id': 'demo-sales'}).json()['id']
    demo = next(e['result'] for e in ask(client, cid, '各品类利润排名') if e['type'] == 'result')
    assert 'verified_examples' not in demo
    calls = use_model(client, monkeypatch, ['{"sql":null,"explanation":"请说明时间范围。"}'])
    ask(client, cid, '最近一周有多少订单')
    assert 'Verified examples:' not in calls[0][0]['content']


def test_invalid_plan_gets_one_format_retry(client, monkeypatch):
    calls = use_model(client, monkeypatch, ['我来帮你查询。', '计划如下：{"sql":"SELECT COUNT(*) AS n FROM sales","chart_type":"table"}', 'Done.'])
    cid = client.post('/api/conversations', json={'source_id': 'demo-sales'}).json()['id']
    events = ask(client, cid, '有多少订单')
    result = next(e['result'] for e in events if e['type'] == 'result')
    assert result['rows'] == [[720]] and result['chart'] is None
    assert '不是有效的 JSON' in calls[1][-1]['content']
    calls = use_model(client, monkeypatch, ['not json', 'still not json'])
    assert any(e['type'] == 'error' for e in ask(client, cid, '有多少订单'))


def test_parse_plan_extracts_wrapped_json():
    assert parse_plan('Here is the plan:\n```json\n{"sql":"SELECT 1","chart_type":"scatter"}\n```').chart_type == 'bar'
    with pytest.raises(ValueError):
        parse_plan('no plan here')


def test_transient_model_errors_retry(monkeypatch):
    monkeypatch.setattr('backend.agent.RETRY_DELAYS', (0, 0))
    statuses = iter([503, 429, 200])
    seen = []
    def handle(request):
        seen.append(request)
        status = next(statuses)
        return httpx.Response(status, json={'choices': [{'message': {'content': 'OK'}}]} if status == 200 else {})
    real_client = httpx.Client
    monkeypatch.setattr('backend.agent.httpx.Client', lambda **kw: real_client(transport=httpx.MockTransport(handle), **kw))
    assert call_model({'base_url': 'https://example.com', 'model': 'm'}, []) == 'OK'
    assert len(seen) == 3
    statuses, seen[:] = iter([401, 200]), []
    with pytest.raises(ValueError, match='API Key 无效'):
        call_model({'base_url': 'https://example.com', 'model': 'm'}, [])
    assert len(seen) == 1


def test_profile_draft_lists_low_cardinality_values(client):
    zh = client.get('/api/sources/demo-sales/profile').json()['fields']
    assert 'sales.region（VARCHAR）：4 个取值' in zh and '华东' in zh
    assert 'sales.order_date（DATE）：范围 2026-01-01 ~ 2026-08-31' in zh
    assert 'sales.order_id（VARCHAR）：720 个不同值' in zh
    en = client.get('/api/sources/demo-sales/profile', headers={'Accept-Language': 'en-US'}).json()['fields']
    assert 'sales.channel (VARCHAR): 3 values:' in en
    store = client.app.state.store
    business = seed_business(store)
    text = client.get(f"/api/sources/{business['id']}/profile").json()['fields']
    assert 'orders.status（VARCHAR）：3 个取值：paid、cancelled、pending' in text
    # Drafts are never saved implicitly.
    assert store.business_context(business['id'])['fields'] == CONTEXT['fields']


def test_profile_skips_personal_columns(client):
    csv = 'customer_name,phone,city,amount\n张三,13800000000,上海,10\n李四,13900000000,北京,20\n'
    source = client.post('/api/sources/csv', files={'file': ('people.csv', csv.encode(), 'text/csv')}).json()
    text = client.get(f"/api/sources/{source['id']}/profile").json()['fields']
    assert '张三' not in text and '13800000000' not in text
    assert 'data.customer_name' in text and '可能包含个人信息' in text
    assert '上海' in text
