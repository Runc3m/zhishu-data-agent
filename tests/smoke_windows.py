"""Exercise the distributed EXE in fresh storage, without any developer credentials."""
import argparse
import csv
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import zipfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx


def verify_release_features(client, url):
    """Exercise the frozen modules and HTTP integration without external AI credentials."""
    rows = {
        'orders': [['order_id','customer_id','order_status','order_purchase_timestamp','order_delivered_customer_date','order_estimated_delivery_date'],
                   ['a','c1','delivered','2017-01-01','2017-01-05','2017-01-06']],
        'order_items': [['order_id','order_item_id','price','freight_value','product_id','seller_id'],['a','1','100','10','p','s']],
        'order_payments': [['order_id','payment_value'],['a','110']],
        'customers': [['customer_id','customer_unique_id'],['c1','u1']],
    }
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as z:
        for name in ('orders','order_items','order_payments','order_reviews','customers','products','sellers','geolocation','category_translation'):
            out = io.StringIO()
            csv.writer(out).writerows(rows.get(name, [['id'], ['x']]))
            filename = 'product_category_name_translation.csv' if name == 'category_translation' else f'olist_{name}_dataset.csv'
            z.writestr(filename, out.getvalue())
    response = client.post(url + '/api/sources/package', files={'file': ('olist-test.zip', archive.getvalue(), 'application/zip')})
    response.raise_for_status()
    source = response.json()
    assert len(source['tables']) == 13
    assert client.get(url + f'/api/sources/{source["id"]}/checks').json()['passed']
    assert len(client.get(url + f'/api/sources/{source["id"]}/pipeline').json()['steps']) == 3

    plan = {'action': 'analysis', 'queries': [
        {'sql': 'SELECT category, SUM(sales) AS revenue FROM sales GROUP BY 1 ORDER BY 2 DESC', 'chart_type': 'horizontal_bar'},
        {'sql': "SELECT strftime(order_date, '%Y-%m') AS month, SUM(sales) AS revenue FROM sales GROUP BY 1 ORDER BY 1", 'chart_type': 'area'}]}
    report = {'conclusion': 'Results are available for review.', 'findings': ['Compare query results [1].'],
              'actions': [], 'limitations': ['Synthetic package test.'], 'followups': []}
    replies = iter([plan, report, report])
    class Model(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']))
            data = json.dumps({'choices': [{'message': {'content': json.dumps(next(replies))}}]}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Model)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client.put(url + '/api/sources/demo-sales/context', json={'metrics':'revenue = SUM(sales); group by category for category rankings.'}).raise_for_status()
        client.put(url + '/api/settings', json={'mode':'llm', 'provider':'custom', 'base_url':f'http://127.0.0.1:{server.server_port}/v1', 'model':'package-test', 'api_key':''}).raise_for_status()
        cid = client.post(url + '/api/conversations', json={'source_id':'demo-sales'}).json()['id']
        def ask(question):
            response = client.post(url + f'/api/conversations/{cid}/messages', json={'content':question})
            response.raise_for_status()
            events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
            assert not any(e['type'] == 'error' for e in events), events
            return next(e['result'] for e in events if e['type'] == 'result')
        analysis = ask('Which sells best?')
        assert len(analysis['panels']) == 2
        assert analysis['panels'][0]['chart']['type'] == 'horizontal_bar'
        assert len(analysis['panels'][0]['rows']) == 4
        assert len(analysis['panels'][1]['rows']) == 8
        assert analysis['report']['conclusion'] == report['conclusion']
        assert analysis['retrieval']['mode'] == 'lexical'
        explanation = ask('Explain this simply')
        assert explanation['response_kind'] == 'explain' and explanation['based_on_message_id']
        client.delete(url + f'/api/conversations/{cid}').raise_for_status()
        assert not any(c['id'] == cid for c in client.get(url + '/api/conversations').json())
        assert client.get(url + f'/api/sources/{source["id"]}/checks').json()['passed']
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    print('v1.2 package: Olist import/lineage/checks, simulated-model BI/explanation, lexical retrieval, deletion PASS')


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
                assert client.get(url + '/api/preferences').json()['language'] == 'zh-CN'
                assert {s['id'] for s in client.get(url + '/api/sources').json()} == {'demo-sales', 'demo-commerce'}
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
                if version != '1.0.0':
                    context = client.put(url + f'/api/sources/{sid}/context', json={'notes': 'Synthetic package verification', 'metrics': 'total = sum(revenue)'}).json()
                    assert context['version'] == 1
                    assert client.get(url + f'/api/sources/{sid}/context').json() == context
                verify_release_features(client, url)
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
