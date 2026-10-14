import threading
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from backend.app import create_app


def test_delete_only_selected_conversation_and_messages(tmp_path):
    with TestClient(create_app(tmp_path / 'storage')) as client:
        store = client.app.state.store
        first = store.create_conversation('demo-sales')['id']
        other = store.create_conversation('demo-sales')['id']
        store.add_message(first, 'user', 'delete this test conversation')
        store.add_message(first, 'assistant', 'answer', {'rows': [[1]], 'columns': ['n']})
        store.add_message(other, 'user', 'keep this test conversation')
        store.save_settings({'api_key': 'test-secret'})
        before_sources, before_settings = store.sources(), store.settings(private=True)
        before_context = store.business_context('demo-sales')
        assert client.delete(f'/api/conversations/{first}').json() == {'deleted': first}
        assert client.get(f'/api/conversations/{first}/messages').status_code == 400
        assert client.get(f'/api/conversations/{first}/export').status_code == 400
        assert client.delete(f'/api/conversations/{first}').status_code == 400
        assert store.messages(other)[0]['content'] == 'keep this test conversation'
        assert store.sources() == before_sources
        assert store.settings(private=True) == before_settings
        assert store.business_context('demo-sales') == before_context
        with store.connect() as db:
            assert db.execute('SELECT COUNT(*) FROM messages WHERE conversation_id=?', (first,)).fetchone()[0] == 0


def test_active_conversation_cannot_be_deleted(tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    with TestClient(create_app(tmp_path / 'storage')) as client:
        cid = client.app.state.store.create_conversation('demo-sales')['id']
        def slow_answer(*args, **kwargs):
            entered.set()
            assert release.wait(10)
            yield {'type': 'done'}
        monkeypatch.setattr(client.app.state.agent, 'run', slow_answer)
        with ThreadPoolExecutor(max_workers=1) as executor:
            request = executor.submit(client.post, f'/api/conversations/{cid}/messages', json={'content': 'test'})
            try:
                assert entered.wait(10)
                blocked = client.delete(f'/api/conversations/{cid}', headers={'Accept-Language': 'en-US'})
                assert blocked.status_code == 409 and 'Wait for it to finish' in blocked.text
                assert client.app.state.store.conversation(cid)
            finally:
                release.set()
            assert request.result(timeout=10).status_code == 200
        assert client.delete(f'/api/conversations/{cid}').status_code == 200


def test_cross_site_delete_is_blocked(tmp_path):
    with TestClient(create_app(tmp_path / 'storage')) as client:
        cid = client.app.state.store.create_conversation('demo-sales')['id']
        assert client.delete(f'/api/conversations/{cid}', headers={'Origin': 'https://example.com'}).status_code == 403
        assert client.app.state.store.conversation(cid)
