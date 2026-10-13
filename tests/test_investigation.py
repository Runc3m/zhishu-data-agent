"""Executed-data acceptance tests; mocked planner tests are not live LLM accuracy."""
import json
import re

import duckdb
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.commerce import QUESTION_EN, QUESTION_ZH
from backend.knowledge import evidence, retrieve
from backend.quality import inspect_source


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'storage')) as c:
        yield c


def ask(client, question, language='en-US', mode='auto', source='demo-commerce'):
    cid = client.post('/api/conversations', json={'source_id': source}).json()['id']
    response = client.post(f'/api/conversations/{cid}/messages', json={'content': question, 'language': language, 'analysis_mode': mode})
    events = [json.loads(s[6:]) for s in response.text.splitlines() if s.startswith('data: ')]
    assert not any(e['type'] == 'error' for e in events), events
    return next(e['result'] for e in events if e['type'] == 'result'), cid


@pytest.mark.parametrize('language,question', [('zh-CN', QUESTION_ZH), ('en-US', QUESTION_EN)])
def test_executed_commerce_investigation(client, language, question):
    result, cid = ask(client, question, language)
    # Independent hand calculation: 31*(90+60+40) vs 31*(50+70+40).
    assert result['investigation'][2]['rows'] == [['2026-07',6200,310,5890],['2026-08',5580,620,4960]]
    assert result['rows'] == [['Electronics',2790,1550],['Home',1860,2170],['Sports',1240,1240]]
    assert result['reconciliation'] == {'passed': True, 'total_change': -930, 'category_change_sum': -930}
    assert len(result['investigation']) == 5
    assert "o.category='Electronics'" in result['investigation'][-1]['sql']
    assert result['knowledge_sources'] and result['context_version'] == 1
    if language == 'en-US':
        assert not re.search('[\u4e00-\u9fff]', result['answer'] + result['notice'])
    saved = client.get(f'/api/conversations/{cid}/messages').json()[-1]['result']
    assert saved['investigation'] == result['investigation']
    report = client.get(f'/api/conversations/{cid}/export?language={language}').text
    assert '5890' in report and '[5]' in report and 'reconciliation' in report


@pytest.mark.parametrize('q,expected', [('What is the refund rate?', 'Do you mean'), ('Analyze the net sales change in September 2026', 'not loaded'), ('Predict next year sales', 'Enable AI')])
def test_demo_boundaries(client, q, expected):
    result, _ = ask(client, q)
    assert not result.get('sql') and expected in result['answer']


@pytest.mark.parametrize('mutation', [
    "DELETE FROM orders WHERE order_date='2026-08-31'",
    'INSERT INTO orders SELECT * FROM orders WHERE order_id=1',
    'UPDATE orders SET order_id=1 WHERE order_id=100',
    'UPDATE orders SET amount_cents=NULL WHERE order_id=1',
    "UPDATE orders SET status='unknown' WHERE order_id=1",
    'INSERT INTO refunds SELECT * FROM refunds WHERE refund_id=1',
    'UPDATE refunds SET order_id=12345 WHERE refund_id=1',
])
def test_quality_blocks_invalid_comparison(client, mutation):
    source = client.app.state.store.source('demo-commerce')
    with duckdb.connect(source['path']) as db:
        db.execute(mutation)
    result, _ = ask(client, QUESTION_EN)
    assert 'checks failed' in result['answer']
    assert len(result['investigation']) == 2 and not result.get('reconciliation')


def test_modified_context_is_not_silently_ignored(client):
    client.put('/api/sources/demo-commerce/context', json={'metrics': 'net sales = gross sales'})
    result, _ = ask(client, QUESTION_EN)
    assert 'definitions have changed' in result['answer'] and not result.get('sql')


@pytest.mark.parametrize('mutation,expected', [
    ("UPDATE orders SET status='cancelled' WHERE order_date<'2026-08-01'", 'no eligible orders'),
    ("UPDATE orders SET amount_cents=0 WHERE order_date<'2026-08-01'; UPDATE refunds SET amount_cents=0 WHERE order_id IN (SELECT order_id FROM orders WHERE order_date<'2026-08-01')", 'percentage undefined'),
])
def test_comparison_baseline_edge_cases(client, mutation, expected):
    with duckdb.connect(client.app.state.store.source('demo-commerce')['path']) as db:
        db.execute(mutation)
    result, _ = ask(client, QUESTION_EN)
    assert expected in result['answer']


def test_retrieval_version_no_hits_and_bilingual_match():
    context = {'version': 4, 'metrics': '净销售额 Net sales excludes completed refunds.', 'fields': 'cost field not available'}
    for q in ('净销售额', 'net sales'):
        hits = retrieve(context, q)
        assert hits[0]['id'] == 'metrics:0@v4'
    assert retrieve(context, 'astronomy') == []
    assert retrieve({'version': 0}, 'sales') == []


def test_profile_uses_rows_beyond_sample_without_claiming_population():
    result = {'columns': ['value'], 'rows': [[i] for i in range(100)], 'row_count': 100, 'truncated': True, 'sql': 'SELECT value FROM t'}
    view = evidence(result)
    assert len(view['rows']) == 30
    assert view['returned_rows_profile']['value']['sum'] == 4950
    assert view['truncated'] and 'ALL RETURNED' in view['scope']


def enable_ai(client, monkeypatch, replies):
    client.app.state.store.save_settings({'mode': 'llm', 'provider': 'custom', 'base_url': 'https://example.com', 'model': 'mock'})
    calls = []
    responses = iter(replies)
    def model(settings, messages, **kwargs):
        calls.append(json.loads(json.dumps(messages)))
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response
    monkeypatch.setattr('backend.agent.call_model', model)
    return calls


def plan(sql, explanation='Check totals'):
    return json.dumps({'sql': sql, 'explanation': explanation, 'chart_type': 'none'})


def test_ai_observe_then_adapt_and_preserve_context(client, monkeypatch):
    calls = enable_ai(client, monkeypatch, [plan('SELECT SUM(amount_cents) AS gross FROM orders'),
        plan("SELECT category, SUM(amount_cents) FROM orders GROUP BY category"),
        plan(None, 'No causal evidence is available.'), 'Observed totals [1] and categories [2]. Causality is unknown.'])
    result, _ = ask(client, 'Investigate sales', mode='investigate')
    assert len(result['investigation']) == 2
    assert result['stop_reason'] == 'planner_stopped'
    assert 'Observed result for step 1' in calls[1][-1]['content']
    assert result['quality']['tables_checked'] == 2
    assert result['usage']['model_calls'] == 4
    assert result['business_context']['version'] == 1


def test_ai_bounded_steps(client, monkeypatch):
    enable_ai(client, monkeypatch, [plan(f'SELECT COUNT(*)+{i} AS n FROM orders') for i in range(5)] + ['Evidence collected.'])
    result, _ = ask(client, 'Investigate sales')
    assert len(result['investigation']) == 5 and result['stop_reason'] == 'step_limit'
    assert result['usage']['model_calls'] == 6


def test_chart_change_does_not_trigger_investigation(client, monkeypatch):
    calls = enable_ai(client, monkeypatch, [plan('SELECT COUNT(*) FROM orders'), 'One result.'])
    result, _ = ask(client, 'Change to a line chart')
    assert 'investigation' not in result and len(calls) == 2


def test_repeat_and_summary_failure_keep_successful_evidence(client, monkeypatch):
    sql = 'SELECT COUNT(*) AS n FROM orders'
    enable_ai(client, monkeypatch, [plan(sql), plan(sql), ValueError('model unavailable')])
    result, _ = ask(client, 'Investigate sales')
    assert result['stop_reason'] == 'repeated_query' and len(result['investigation']) == 1
    assert result['rows'] == [[187]] and 'preserved' in result['notice']


def test_unsafe_queries_never_execute_and_repair_budget(client, monkeypatch):
    enable_ai(client, monkeypatch, [plan('DELETE FROM orders')] * 3)
    result, _ = ask(client, 'Investigate sales')
    assert result['stop_reason'] == 'query_error' and result['usage']['repair_attempts'] == 2
    assert result['investigation'] == []
    source = client.app.state.store.source('demo-commerce')
    assert client.app.state.engines.query(source, 'SELECT COUNT(*) FROM orders')['rows'] == [[187]]


def test_inspection_treats_duplicates_as_candidate_not_proven_key(client):
    quality = inspect_source(client.app.state.engines, client.app.state.store.source('demo-commerce'))
    assert quality['checks'][1]['candidate_key'] == 'refund_id'
    assert 'not constraints' in quality['scope']


def test_invalid_analysis_mode_rejected(client):
    cid = client.post('/api/conversations', json={'source_id': 'demo-commerce'}).json()['id']
    assert client.post(f'/api/conversations/{cid}/messages', json={'content': 'test', 'analysis_mode': 'execute'}).status_code == 422
