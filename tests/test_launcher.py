import json
import socket

from launcher import healthy, lock_storage, reserve_socket, storage_id


def test_health_identity(tmp_path):
    from fastapi.testclient import TestClient
    from backend.app import create_app
    app = create_app(tmp_path / 'storage')
    with TestClient(app) as client:
        data = client.get('/api/health').json()
        assert data['instance'] == storage_id(app.state.store.root)


def test_storage_lock(tmp_path):
    first = lock_storage(tmp_path)
    assert first is not None
    assert lock_storage(tmp_path) is None
    first.close()
    second = lock_storage(tmp_path)
    assert second is not None
    second.close()


def test_port_conflict_uses_next_port():
    busy = socket.socket()
    busy.bind(('127.0.0.1', 0))
    port = busy.getsockname()[1]
    reserved, actual = reserve_socket(port)
    try:
        assert actual > port
        assert reserved.getsockname()[0] == '127.0.0.1'
    finally:
        reserved.close()
        busy.close()


def test_health_does_not_follow_system_proxy(monkeypatch, tmp_path):
    import launcher
    from io import BytesIO
    class Opener:
        def open(self, url, timeout):
            return BytesIO(json.dumps({'app': 'zhishu-data-agent', 'version': '1.1.0', 'instance': storage_id(tmp_path)}).encode())
    def build(handler):
        assert handler.proxies == {}
        return Opener()
    monkeypatch.setattr(launcher, 'build_opener', build)
    assert healthy('http://127.0.0.1:8100', tmp_path)
