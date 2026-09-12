import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.i18n import translate
from backend.store import Store
from backend.version import VERSION


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'storage')) as client:
        yield client


def ask(client, text, language=None, cid=None):
    cid = cid or client.post('/api/conversations', json={'source_id': 'demo-sales'}).json()['id']
    body = {'content': text}
    if language:
        body['language'] = language
    response = client.post(f'/api/conversations/{cid}/messages', json=body)
    assert response.status_code == 200
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    assert not any(e['type'] == 'error' for e in events), events
    return cid, next(e['result'] for e in events if e['type'] == 'result'), events


def test_preference_migration_preserves_settings_and_history(client):
    store = client.app.state.store
    store.save_settings({'mode': 'demo', 'api_key': 'migration-test-secret'})
    cid, first, _ = ask(client, '销售概览')
    key_file = (store.root / 'local.key').read_bytes()
    before = store.messages(cid)
    with store.connect() as db:
        db.execute('DROP TABLE preferences')
    reopened = Store(store.root)
    assert reopened.preferences() == {'language': 'zh-CN'}
    assert reopened.messages(cid) == before
    assert reopened.settings(private=True)['api_key'] == 'migration-test-secret'
    assert client.put('/api/preferences', json={'language': 'en-US'}).status_code == 200
    assert Store(store.root).preferences()['language'] == 'en-US'
    assert (store.root / 'local.key').read_bytes() == key_file
    assert client.put('/api/preferences', json={'language': 'invalid'}).status_code == 422
    assert 'Select a valid option' in client.put('/api/preferences', json={'language': 'invalid'}).text


@pytest.mark.parametrize('question,count', [
    ('Compare sales by region', 4), ('Monthly sales trend', 8),
    ('Rank categories by profit', 4), ('Sales overview', 1), ('Preview the first 20 rows', 20),
])
def test_english_demo(client, question, count):
    _, result, events = ask(client, question, 'en-US')
    assert result['language'] == 'en-US'
    assert result['row_count'] == count
    for e in events:
        if e['type'] == 'step':
            assert not re.search('[\u4e00-\u9fff]', e['label'] + e['detail'])
    assert not re.search('[\u4e00-\u9fff]', result['explanation'] + result['answer'] + result['notice'])


def test_english_followups_and_request_snapshot(client):
    client.put('/api/preferences', json={'language': 'en-US'})
    cid, result, _ = ask(client, 'Monthly sales trend')
    _, result, _ = ask(client, 'Only show the second quarter', cid=cid)
    assert [r[0] for r in result['rows']] == ['2026-04', '2026-05', '2026-06']
    _, result, _ = ask(client, 'What about the third quarter?', cid=cid)
    assert [r[0] for r in result['rows']] == ['2026-07', '2026-08']
    _, result, _ = ask(client, 'What about profit?', cid=cid)
    assert 'SUM(profit)' in result['sql']
    generator = client.app.state.agent.run(cid, 'Sales overview', language='en-US')
    next(generator)
    client.put('/api/preferences', json={'language': 'zh-CN'})
    events = list(generator)
    assert next(e['result'] for e in events if e['type'] == 'result')['language'] == 'en-US'


def test_errors_templates_and_exports(client):
    assert translate('返回 4 行 · 8 ms', 'en-US') == '4 rows returned · 8 ms'
    assert translate('API Key 无效（HTTP 401），请检查模型设置。', 'en-US') == 'Invalid API key (HTTP 401). Check Model settings.'
    assert translate('自定义数据', 'en-US') == '自定义数据'
    client.put('/api/preferences', json={'language': 'en-US'})
    error = client.post('/api/settings/test', json={'mode': 'llm', 'api_key': ''})
    assert 'Enter your DeepSeek API key' in error.json()['detail']
    cid, result, _ = ask(client, '各地区销售额对比', 'zh-CN')
    before = client.get(f'/api/conversations/{cid}/messages').json()
    exported = client.get(f'/api/conversations/{cid}/export?language=en-US').text
    assert '## Question' in exported and '## Analysis' in exported
    assert result['answer'] in exported
    assert client.get(f'/api/conversations/{cid}/messages').json() == before


def test_ai_language_rule_and_override(client, monkeypatch):
    client.put('/api/settings', json={'mode': 'llm', 'provider': 'custom', 'base_url': 'https://example.com', 'model': 'test'})
    calls = []
    def mock(settings, messages, **kwargs):
        calls.append(messages)
        return '{"sql":null,"explanation":"Please clarify the metric."}'
    monkeypatch.setattr('backend.agent.call_model', mock)
    ask(client, 'Which metric? Please answer in French.', 'en-US')
    assert 'Default response language: English' in calls[0][0]['content']
    assert 'unless the user explicitly requests another language' in calls[0][0]['content']
    assert calls[0][-1]['content'].endswith('Please answer in French.')


def test_frontend_catalog_and_version():
    root = Path(__file__).resolve().parents[1]
    catalog = json.loads((root / 'frontend/src/locales/en.json').read_text(encoding='utf-8'))
    source = '\n'.join(path.read_text(encoding='utf-8') for path in (root / 'frontend/src').glob('*.tsx'))
    for literal in re.findall(r'\bt\(("(?:[^"\\]|\\.)*")', source):
        key = json.loads(literal)
        assert key in catalog, key
    business = (root / 'frontend/src/BusinessContext.tsx').read_text(encoding='utf-8')
    for key in re.findall(r"(?:label|hint): '([^']+)'", business):
        assert key in catalog
    for key, value in catalog.items():
        assert sorted(re.findall(r'\{\d+\}', key)) == sorted(re.findall(r'\{\d+\}', value)), key
    assert json.loads((root / 'frontend/package.json').read_text())['version'] == VERSION
