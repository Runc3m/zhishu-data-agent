import json

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.store import Store
from evals.business import CASES, CONTEXT, seed_business
from evals.run import matches


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'storage')) as client:
        yield client


def test_context_save_revision_and_reopen(client):
    url = '/api/sources/demo-sales/context'
    assert client.get(url).json()['version'] == 0
    first = client.put(url, json=CONTEXT).json()
    assert first['version'] == 1
    assert client.put(url, json=CONTEXT).json() == first
    second = client.put(url, json={**CONTEXT, 'notes': '业务口径已修订'}).json()
    assert second['version'] == 2
    store = Store(client.app.state.store.root)
    assert store.business_context('demo-sales') == second
    assert client.get('/api/sources/not-found/context').status_code == 400
    assert client.put(url, json={'notes': 'a' * 8001}).status_code == 422


def test_snapshot_repair_and_history(client, monkeypatch):
    store = client.app.state.store
    client.put('/api/sources/demo-sales/context', json={'metrics': 'sum_sales = sum(sales) in CNY'})
    store.save_settings({'mode': 'llm', 'provider': 'custom', 'base_url': 'https://example.com', 'model': 'test'})
    cid = store.create_conversation('demo-sales')['id']
    calls = []
    replies = iter(['{"sql":"SELECT SUM(missing) FROM sales"}', '{"sql":"SELECT SUM(sales) FROM sales"}', 'See query results.'])
    def model(settings, messages, **kwargs):
        calls.append(json.loads(json.dumps(messages)))
        return next(replies)
    monkeypatch.setattr('backend.agent.call_model', model)
    stream = client.app.state.agent.run(cid, 'sum_sales?', 'en-US')
    next(stream)
    client.put('/api/sources/demo-sales/context', json={'metrics': 'a different definition'})
    result = next(event['result'] for event in stream if event['type'] == 'result')
    stream.close()
    assert result['context_version'] == 1
    assert result['business_context']['metrics'] == 'sum_sales = sum(sales) in CNY'
    assert len(calls) == 3
    assert 'never draw ASCII, Unicode or text charts' in calls[2][0]['content']
    for messages in calls[:2]:
        assert 'sum_sales = sum(sales)' in messages[0]['content']
        assert 'a different definition' not in messages[0]['content']
        assert 'conflicting definitions' in messages[0]['content']
    report = client.get(f'/api/conversations/{cid}/export?language=en-US').text
    assert 'Business context version: 1' in report and 'sum_sales = sum(sales)' in report
    assert store.messages(cid)[-1]['result']['context_version'] == 1


def test_demo_does_not_claim_context_is_applied(client):
    store = client.app.state.store
    store.save_business_context('demo-sales', {'metrics': 'sales must be divided by 100'})
    cid = store.create_conversation('demo-sales')['id']
    result = next(e['result'] for e in client.app.state.agent.run(cid, '销售概览') if e['type'] == 'result')
    assert 'context_version' not in result
    assert result['rows'][0][0] == pytest.approx(1190033.7)


def test_golden_comparison_rejects_wrong_totals_and_errors():
    assert not matches({'rows': [[2500]], 'sql': 'SELECT 2500'}, CASES[0])
    assert not matches({'answer': 'failed', 'error': 'failed'}, CASES[-1])
    assert not matches({'answer': 'guessed', 'sql': 'SELECT 1', 'rows': [[1]]}, CASES[-1])


def test_boolean_filters_remain_read_only(client):
    source = client.app.state.store.source('demo-sales')
    result = client.app.state.engines.query(source, "SELECT COUNT(*) FROM sales WHERE sales>0 AND (region='华北' OR NOT region='华北')")
    assert result['rows'] == [[720]]


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['id'])
@pytest.mark.parametrize('language', ['zh-CN', 'en-US'])
def test_golden_business_results(client, monkeypatch, case, language):
    """Pipeline regression, not a measurement of a real model's accuracy."""
    store = client.app.state.store
    source = seed_business(store)
    if case['context_override']:
        store.save_business_context(source['id'], {**CONTEXT, **case['context_override']})
    store.save_settings({'mode': 'llm', 'provider': 'custom', 'base_url': 'https://example.com', 'model': 'mock'})
    def model(settings, messages, **kwargs):
        if 'Output plain text.' in messages[0]['content']:
            return 'See query results.'
        assert 'Confirmed business context:' in messages[0]['content']
        assert messages[-1]['content'] == case[language]
        return json.dumps({'sql': case['sql'], 'explanation': '请澄清指标定义。' if language == 'zh-CN' else 'Please clarify the metric definition.', 'chart_type': 'none'})
    monkeypatch.setattr('backend.agent.call_model', model)
    cid = store.create_conversation(source['id'])['id']
    events = list(client.app.state.agent.run(cid, case[language], language))
    assert not any(e['type'] == 'error' for e in events), [e for e in events if e['type'] == 'error']
    result = next(e['result'] for e in events if e['type'] == 'result')
    assert result['context_version'] == (2 if case['context_override'] else 1)
    if case['sql'] is None:
        assert not result.get('sql') and result['answer']
    else:
        assert result['rows'] == case['rows']
        assert result['row_count'] == len(case['rows'])
