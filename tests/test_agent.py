import json

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.agent import call_model, parse_plan
from backend.engines import csv_bytes
from backend.safety import validate_sql
from backend.store import Store


@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path / 'storage')


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def stream(client, cid, text):
    response = client.post(f'/api/conversations/{cid}/messages', json={'content': text})
    assert response.status_code == 200
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]


def new_chat(client, source='demo-sales'):
    r = client.post('/api/conversations', json={'source_id': source})
    assert r.status_code == 200
    return r.json()['id']


def result(events):
    assert events[-1] == {'type': 'done'}
    assert not any(e['type'] == 'error' for e in events), events
    return next(e['result'] for e in events if e['type'] == 'result')


@pytest.mark.parametrize('question,groups', [
    ('各地区销售额对比', 4), ('每月销售趋势', 8), ('各品类利润排名', 4), ('销售概览', 1),
])
def test_demo_executes_real_data(client, app, question, groups):
    cid = new_chat(client)
    r = result(stream(client, cid, question))
    assert r['row_count'] == groups
    assert r['mode'] == 'demo'
    assert r['rows']
    assert r['executed_sql'].endswith('LIMIT 501')
    persisted = client.get(f'/api/conversations/{cid}/messages').json()
    assert len(persisted) == 2
    assert persisted[-1]['result']['rows'] == r['rows']
    assert 'sales' in r['sql']


def test_follow_up_chart_and_profit(client):
    cid = new_chat(client)
    first = result(stream(client, cid, '各地区销售额对比'))
    second = result(stream(client, cid, '改成折线图'))
    assert first['sql'] == second['sql']
    assert second['chart']['type'] == 'line'
    third = result(stream(client, cid, '各地区利润对比'))
    assert 'profit' in third['sql']
    assert third['rows'] != first['rows']


def test_multiple_followups_replace_quarter_and_keep_monthly_grouping(client):
    cid = new_chat(client)
    result(stream(client, cid, '每月销售趋势'))
    q2 = result(stream(client, cid, '只看第二季度'))
    q3 = result(stream(client, cid, '那第三季度呢'))
    profit = result(stream(client, cid, '那利润呢'))
    assert [r[0] for r in q2['rows']] == ['2026-04', '2026-05', '2026-06']
    assert [r[0] for r in q3['rows']] == ['2026-07', '2026-08']
    assert [r[0] for r in profit['rows']] == ['2026-07', '2026-08']
    assert 'SUM(profit)' in profit['sql']


def test_csv_roundtrip_and_reopen(client, app):
    data = '城市,收入\n杭州,10\n上海,20\n'.encode('utf-8-sig')
    r = client.post('/api/sources/csv', files={'file': ('城市.csv', data, 'text/csv')})
    assert r.status_code == 200, r.text
    source = r.json()
    assert 'path' not in source
    assert source['tables'][0]['rows'] == 2
    preview = client.get(f"/api/sources/{source['id']}/preview").json()
    assert preview['rows'] == [['杭州', 10], ['上海', 20]]
    cid = new_chat(client, source['id'])
    answer = result(stream(client, cid, '共有多少行'))
    assert answer['rows'] == [[2]]
    store = Store(app.state.store.root)
    assert len(store.messages(cid)) == 2
    assert store.source(source['id'])['name'] == '城市.csv'


def test_row_cap(client, app):
    source = app.state.store.source('demo-sales')
    r = app.state.engines.query(source, 'SELECT * FROM sales')
    assert r['row_count'] == 500
    assert r['truncated'] is True
    assert len(r['rows']) == 500


@pytest.mark.parametrize('sql', [
    'DELETE FROM sales', 'SELECT 1; DROP TABLE sales', 'COPY sales TO \'x.csv\'',
    "SELECT * FROM read_csv('C:/secret.csv')", "SELECT read_text('secret')", 'SELECT * FROM information_schema.tables',
    'SELECT * FROM sales FOR UPDATE', 'SELECT * INTO backup FROM sales',
    "ATTACH 'secret.duckdb' AS s", 'SELECT * FROM other.main.sales',
    'SELECT pg_sleep(30)', 'SELECT set_config(\'x\',\'y\',false)',
    'WITH secret AS (SELECT * FROM forbidden) SELECT * FROM secret',
    'WITH sales AS (SELECT * FROM forbidden) SELECT * FROM sales',
    'WITH RECURSIVE n AS (SELECT 1 UNION ALL SELECT 1 FROM n) SELECT * FROM n',
    "SELECT * FROM 'secret.csv'", 'SELECT public.sum(sales) FROM sales',
    'WITH x AS (DELETE FROM sales RETURNING *) SELECT * FROM x',
])
def test_unsafe_queries_rejected(sql):
    with pytest.raises(ValueError):
        validate_sql(sql, 'duckdb', [{'name': 'sales', 'schema': ''}])


def test_valid_cte_and_window(app, client):
    source = app.state.store.source('demo-sales')
    r = app.state.engines.query(source, '''WITH grouped AS (
        SELECT region, SUM(sales) AS revenue FROM sales GROUP BY region
    ) SELECT region, revenue, RANK() OVER (ORDER BY revenue DESC) AS ranking FROM grouped''')
    assert len(r['rows']) == 4
    assert sorted(row[2] for row in r['rows']) == [1, 2, 3, 4]


def test_settings_secret_never_returned(client, app):
    body = {'mode': 'llm', 'base_url': 'https://example.com/v1', 'model': 'test', 'api_key': 'private-test-secret'}
    r = client.put('/api/settings', json=body)
    assert r.status_code == 200
    assert r.json()['has_api_key']
    assert 'private-test-secret' not in r.text
    assert 'api_key' not in r.json()
    assert b'private-test-secret' not in app.state.store.db.read_bytes()
    body['api_key'] = None
    client.put('/api/settings', json=body)
    assert app.state.store.settings(private=True)['api_key'] == 'private-test-secret'
    body['api_key'] = ''
    client.put('/api/settings', json=body)
    assert not client.get('/api/settings').json()['has_api_key']


def test_llm_repair_is_revalidated(client, app, monkeypatch):
    client.put('/api/settings', json={'mode':'llm','base_url':'https://example.com/v1','model':'test','api_key':''})
    calls = []
    responses = iter([
        '{"sql":"SELECT SUM(missing) AS total FROM sales","explanation":"汇总","chart_type":"none"}',
        '{"sql":"SELECT ROUND(SUM(sales),2) AS total FROM sales","explanation":"修正字段","chart_type":"none"}',
        '汇总已完成，具体数值见结果表。',
    ])
    def mock_call(*args, **kwargs):
        calls.append(args)
        return next(responses)
    monkeypatch.setattr('backend.agent.call_model', mock_call)
    r = result(stream(client, new_chat(client), '总销售额是多少'))
    assert r['rows'][0][0] == pytest.approx(1190033.7)
    assert len(calls) == 3
    assert '修正' in r['explanation']


def test_llm_cannot_repair_into_write(client, app, monkeypatch):
    client.put('/api/settings', json={'mode':'llm','base_url':'https://example.com/v1','model':'test'})
    monkeypatch.setattr('backend.agent.call_model', lambda *a, **k: '{"sql":"DELETE FROM sales","explanation":"删除"}')
    events = stream(client, new_chat(client), '测试')
    assert any(e['type']=='error' for e in events)
    count = app.state.engines.query(app.state.store.source('demo-sales'), 'SELECT COUNT(*) AS n FROM sales')
    assert count['rows'] == [[720]]


def test_export_real_results(client):
    cid = new_chat(client)
    stream(client, cid, '各地区销售额对比')
    message = client.get(f'/api/conversations/{cid}/messages').json()[-1]
    exported = client.get(f"/api/conversations/{cid}/messages/{message['id']}/csv")
    assert exported.status_code == 200
    assert exported.content.startswith(b'\xef\xbb\xbf')
    assert '地区' in exported.text
    report = client.get(f'/api/conversations/{cid}/export')
    assert report.status_code == 200
    assert 'LIMIT 501' in report.text
    assert '规则演示' in report.text


def test_csv_formula_escape():
    exported = csv_bytes({'columns': ['=header'], 'rows': [['=HYPERLINK("x")'], [' +SUM(1)'], [-12]]}).decode('utf-8-sig')
    assert "'=header" in exported
    assert "'=HYPERLINK" in exported
    assert "' +SUM" in exported
    assert '-12' in exported


def test_local_only_api(client):
    assert client.get('/api/settings', headers={'Origin':'https://attacker.example'}).status_code == 403
    assert client.get('/api/health', headers={'Host':'attacker.example'}).status_code == 400
    assert client.get('/api/health').status_code == 200
    assert client.post('/api/conversations', json={'source_id':'nonexistent'}).status_code == 400


def test_bad_inputs(client):
    cid = new_chat(client)
    assert client.post(f'/api/conversations/{cid}/messages', json={'content':'  '}).status_code == 422
    assert client.post('/api/sources/csv', files={'file':('bad.csv',b'', 'text/csv')}).status_code == 400
    assert client.post('/api/sources/csv', files={'file':('bad.exe',b'a\n1', 'text/csv')}).status_code == 400
    r = client.put('/api/settings',json={'mode':'llm','base_url':'http://remote.example/v1','model':'x'})
    assert r.status_code == 422
    secret = 'sensitive-key-' * 400
    r = client.put('/api/settings', json={'mode':'llm','base_url':'https://example.com/v1','model':'x','api_key':secret})
    assert r.status_code == 422
    assert secret not in r.text


def test_model_http_protocol(monkeypatch):
    captured = []
    def handle(request):
        captured.append(request)
        return httpx.Response(200, json={'choices':[{'message':{'content':'{"sql":null,"explanation":"需要更多信息"}'}}]})
    real_client = httpx.Client
    monkeypatch.setattr('backend.agent.httpx.Client', lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs))
    config = {'base_url':'https://example.com/v1','model':'custom','api_key':'test-secret'}
    plan = parse_plan(call_model(config, [{'role':'user','content':'hi'}]))
    assert plan.sql is None
    assert captured[0].url.path == '/v1/chat/completions'
    assert captured[0].headers['authorization'] == 'Bearer test-secret'


def test_conversation_conflict(client, app, monkeypatch):
    # Sequential requests are permitted; completed streams must release the busy lock.
    cid = new_chat(client)
    stream(client, cid, '销售概览')
    stream(client, cid, '各地区销售额对比')
    assert len(client.get(f'/api/conversations/{cid}/messages').json()) == 4


def test_deepseek_only_requires_key(client, app, monkeypatch):
    from backend.providers import DEEPSEEK_URL, DEEPSEEK_MODEL
    assert client.get('/api/settings').json()['provider'] == 'deepseek'
    calls = []
    monkeypatch.setattr('backend.app.call_model', lambda config, messages, **kw: calls.append((config, kw)) or 'OK')
    body = {'mode': 'llm', 'provider': 'deepseek', 'api_key': '  test-secret  '}
    assert client.post('/api/settings/test', json=body).status_code == 200
    assert calls[0][0]['base_url'] == DEEPSEEK_URL
    assert calls[0][0]['model'] == DEEPSEEK_MODEL
    assert calls[0][0]['api_key'] == 'test-secret'
    assert calls[0][1]['max_tokens'] >= 128
    saved = client.put('/api/settings', json=body)
    assert saved.status_code == 200
    assert 'test-secret' not in saved.text
    assert client.post('/api/settings/test', json={'mode': 'llm', 'provider': 'deepseek'}).status_code == 200
    assert calls[-1][0]['api_key'] == 'test-secret'


def test_deepseek_overrides_stale_fields(client):
    body = {'mode': 'llm', 'provider': 'deepseek', 'base_url': 'http://localhost:11434/v1', 'model': 'deepseek-chat'}
    r = client.put('/api/settings', json=body)
    assert r.status_code == 200
    assert r.json()['base_url'] == 'https://api.deepseek.com'
    assert r.json()['model'] == 'deepseek-v4-flash'


def test_legacy_custom_settings_remain_custom(client):
    body = {'mode': 'demo', 'base_url': 'http://localhost:11434/v1', 'model': 'local-model'}
    assert client.put('/api/settings', json=body).json()['provider'] == 'custom'
    assert client.get('/api/settings').json()['model'] == 'local-model'


@pytest.mark.parametrize('url,thinking', [('https://api.deepseek.com', True), ('https://example.com/v1', False)])
def test_thinking_disabled_only_for_deepseek(monkeypatch, url, thinking):
    captured = []
    def handle(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={'choices': [{'message': {'content': 'OK'}}]})
    real_client = httpx.Client
    monkeypatch.setattr('backend.agent.httpx.Client', lambda **kw: real_client(transport=httpx.MockTransport(handle), **kw))
    assert call_model({'base_url': url, 'model': 'model', 'api_key': 'test-secret'}, []) == 'OK'
    assert ('thinking' in captured[0]) == thinking
    if thinking:
        assert captured[0]['thinking'] == {'type': 'disabled'}


def test_missing_deepseek_key_friendly(client):
    r = client.post('/api/settings/test', json={'mode': 'llm', 'provider': 'deepseek', 'api_key': ''})
    assert r.status_code == 400
    assert '填写 DeepSeek API Key' in r.json()['detail']


def test_proxy_dependency_error_is_friendly(monkeypatch):
    def missing(**kwargs):
        raise ImportError('socksio')
    monkeypatch.setattr('backend.agent.httpx.Client', missing)
    with pytest.raises(ValueError, match='网络代理组件'):
        call_model({'base_url': 'https://example.com', 'model': 'model'}, [])


@pytest.mark.parametrize('status,reason', [(401, 'API Key 无效'), (402, '余额不足'), (404, '接口地址或模型不存在'), (429, '请求过于频繁')])
def test_safe_model_errors(monkeypatch, status, reason):
    real_client = httpx.Client
    monkeypatch.setattr('backend.agent.httpx.Client', lambda **kw: real_client(
        transport=httpx.MockTransport(lambda req: httpx.Response(status, text='test-secret')), **kw))
    with pytest.raises(ValueError) as exc:
        call_model({'base_url': 'https://example.com', 'model': 'test', 'api_key': 'test-secret'}, [])
    assert reason in str(exc.value)
    assert 'test-secret' not in str(exc.value)
