"""Exercise the distributed EXE in fresh storage, without any developer credentials."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import zipfile

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('exe', type=Path)
    args = parser.parse_args()
    exe = args.exe.resolve()
    version = (exe.parent / 'VERSION').read_text().strip()
    archive = exe.parent.parent / f'Zhishu-v{version}-windows-x64.zip'
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        forbidden = {'storage', 'local.key', 'app.sqlite3', '.env', 'launcher.log'}
        assert not any(forbidden.intersection(Path(n).parts) or n.endswith('.duckdb') for n in names)
        assert any(n.endswith('/Zhishu.exe') for n in names)
    print('Share archive: no private runtime files')
    with tempfile.TemporaryDirectory(prefix='zhishu-package-test-') as temp:
        root = Path(temp)
        blocker = socket.socket()
        blocker.bind(('127.0.0.1', 0))
        port = blocker.getsockname()[1]
        command = [str(exe), '--headless', '--no-browser', '--data-dir', str(root), '--port', str(port)]
        process = subprocess.Popen(command, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            with httpx.Client(trust_env=False, timeout=30) as client:
                url = ''
                for _ in range(160):
                    assert process.poll() is None, 'Packaged application exited during startup'
                    try:
                        actual = json.loads((root / 'launcher.json').read_text())['port']
                        url = f'http://127.0.0.1:{actual}'
                        if client.get(url + '/api/health', timeout=.5).status_code == 200:
                            break
                    except (OSError, ValueError, httpx.HTTPError):
                        pass
                    time.sleep(.25)
                else:
                    raise AssertionError('Application did not become ready')
                assert actual != port
                assert client.get(url).status_code == 200
                assert client.get(url + '/favicon.svg').status_code == 200
                assert client.get(url + '/api/health').json()['version'] == version
                settings = client.get(url + '/api/settings').json()
                assert settings['mode'] == 'demo' and settings['provider'] == 'deepseek'
                assert not settings['has_api_key']
                assert client.get(url + '/api/conversations').json() == []
                assert len(client.get(url + '/api/sources').json()) == 1
                cid = client.post(url + '/api/conversations', json={'source_id': 'demo-sales'}).json()['id']
                events = client.post(url + f'/api/conversations/{cid}/messages', json={'content': '各地区销售额对比'})
                parsed = [json.loads(line[6:]) for line in events.text.splitlines() if line.startswith('data: ')]
                result = next(e['result'] for e in parsed if e['type'] == 'result')
                assert result['row_count'] == 4 and result['chart']['type'] == 'bar'
                csv = client.post(url + '/api/sources/csv', files={'file': ('test.csv', b'city,revenue\nA,10\nB,20\n', 'text/csv')})
                assert csv.status_code == 200
                sid = csv.json()['id']
                assert client.get(url + f'/api/sources/{sid}/preview').json()['row_count'] == 2
                assert client.get(url + f'/api/conversations/{cid}/export').status_code == 200
                assert client.put(url + '/api/preferences', json={'language': 'en-US'}).status_code == 200
                events = client.post(url + f'/api/conversations/{cid}/messages', json={'content': 'Monthly sales trend'})
                parsed = [json.loads(line[6:]) for line in events.text.splitlines() if line.startswith('data: ')]
                english = next(e['result'] for e in parsed if e['type'] == 'result')
                assert english['language'] == 'en-US' and english['row_count'] == 8
                assert '## Question' in client.get(url + f'/api/conversations/{cid}/export').text
                second = subprocess.run(command, creationflags=subprocess.CREATE_NO_WINDOW, timeout=15)
                assert second.returncode == 0 and process.poll() is None
                print('Packaged EXE: startup, port conflict, frontend, clean defaults, SQL, chart, CSV, export, single-instance PASS')
        finally:
            blocker.close()
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=15)


if __name__ == '__main__':
    main()
