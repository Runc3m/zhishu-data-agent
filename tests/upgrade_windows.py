"""Verify actual packaged v1.0 storage can be reopened by a new executable."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import time

import httpx


def start(exe, root, client):
    version = (exe.parent / 'VERSION').read_text().strip()
    process = subprocess.Popen([str(exe), '--headless', '--no-browser', '--data-dir', str(root), '--port', '18200'], creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        for _ in range(200):
            assert process.poll() is None, 'Application exited during upgrade verification'
            try:
                port = json.loads((root / 'launcher.json').read_text())['port']
                url = f'http://127.0.0.1:{port}'
                if client.get(url + '/api/health', timeout=.5).json().get('version') == version:
                    return process, url
            except (OSError, ValueError, httpx.HTTPError):
                pass
            time.sleep(.2)
        raise AssertionError('Startup timed out')
    except BaseException:
        stop(process)
        raise


def stop(process):
    if process.poll() is None:
        process.terminate()
        process.wait(timeout=15)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('old_exe', type=Path)
    parser.add_argument('new_exe', type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='zhishu-upgrade-test-') as temp, httpx.Client(trust_env=False, timeout=30) as client:
        root = Path(temp)
        process, url = start(args.old_exe.resolve(), root, client)
        try:
            cid = client.post(url + '/api/conversations', json={'source_id':'demo-sales'}).json()['id']
            response = client.post(url + f'/api/conversations/{cid}/messages', json={'content':'销售概览'})
            assert '"type": "result"' in response.text
            history = client.get(url + f'/api/conversations/{cid}/messages').json()
            client.put(url + '/api/preferences', json={'language':'en-US'}).raise_for_status()
            client.put(url + '/api/settings', json={'mode':'demo','provider':'deepseek','api_key':'upgrade-test-secret'}).raise_for_status()
            source = client.post(url + '/api/sources/csv', files={'file':('upgrade.csv',b'city,value\nA,10\n','text/csv')}).json()
            encryption_key = (root / 'local.key').read_bytes()
        finally:
            stop(process)
        process, url = start(args.new_exe.resolve(), root, client)
        try:
            assert client.get(url + f'/api/conversations/{cid}/messages').json() == history
            assert client.get(url + '/api/preferences').json()['language'] == 'en-US'
            assert client.get(url + '/api/settings').json()['has_api_key']
            assert (root / 'local.key').read_bytes() == encryption_key
            assert client.get(url + f"/api/sources/{source['id']}/preview").json()['rows'] == [['A',10]]
            saved = client.put(url + '/api/sources/demo-sales/context', json={'metrics':'gross = sum(sales)'}).json()
            assert saved['version'] == 1
        finally:
            stop(process)
        process, url = start(args.new_exe.resolve(), root, client)
        try:
            assert client.get(url + '/api/sources/demo-sales/context').json() == saved
            assert client.get(url + f'/api/conversations/{cid}/messages').json() == history
        finally:
            stop(process)
    print('Upgrade PASS: v1.0 history, CSV, language, encrypted key retained; business context persisted across restart.')


if __name__ == '__main__':
    main()
