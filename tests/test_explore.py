import json

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.explore import classify, mentioned, rule_plan

CSV = '\n'.join(['order_id,order_date,region,channel,amount,quantity,customer_name'] + [
    f'{i},2026-0{1 + i % 6}-1{i % 9},R{i % 4},{"online" if i % 2 else "store"},{100 + i},{i % 7 + 1},P{i}' for i in range(60)])


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'storage')) as client:
        yield client


@pytest.fixture
def source(client):
    return client.post('/api/sources/csv', files={'file': ('shop.csv', CSV.encode(), 'text/csv')}).json()


def ask(client, source, text, language='zh-CN'):
    cid = client.post('/api/conversations', json={'source_id': source['id']}).json()['id']
    response = client.post(f'/api/conversations/{cid}/messages', json={'content': text, 'language': language})
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    assert not any(e['type'] == 'error' for e in events), events
    return next(e['result'] for e in events if e['type'] == 'result')


def test_classify_skips_ids_and_personal_columns(source):
    metrics, dims, dates = classify(source['tables'][0])
    assert metrics == ['amount', 'quantity']
    assert dims == ['region', 'channel']
    assert dates == ['order_date']


def test_mentions_prefer_longer_names():
    assert mentioned('Total amount_cents by region', ['amount', 'amount_cents', 'region']) == ['amount_cents', 'region']
    assert mentioned('按 地区 汇总 金额', ['金额', '地区']) == ['地区', '金额']


def test_suggestions_follow_schema_and_language(client, source):
    zh = client.get(f"/api/sources/{source['id']}/suggestions").json()
    assert [s['kind'] for s in zh] == ['compare', 'trend', 'summary', 'count', 'preview']
    # channel has fewer distinct values than region, so it groups first.
    assert zh[0]['question'] == '按 channel 汇总 amount'
    en = client.get(f"/api/sources/{source['id']}/suggestions", headers={'Accept-Language': 'en-US'}).json()
    assert en[1]['question'] == 'Monthly amount trend'


def test_every_suggestion_runs_in_rule_mode(client, source):
    for language in ('zh-CN', 'en-US'):
        for item in client.get(f"/api/sources/{source['id']}/suggestions", headers={'Accept-Language': language}).json():
            result = ask(client, source, item['question'], language)
            assert result['row_count'] > 0, item


def test_rule_results_are_correct(client, source):
    grouped = ask(client, source, '按 channel 汇总 amount')
    totals = {'online': sum(100 + i for i in range(60) if i % 2), 'store': sum(100 + i for i in range(60) if not i % 2)}
    assert {r[0]: r[1] for r in grouped['rows']} == totals
    assert grouped['chart']['type'] == 'bar'
    trend = ask(client, source, 'Monthly amount trend', 'en-US')
    assert [r[0] for r in trend['rows']] == [f'2026-0{m}' for m in range(1, 7)]
    assert trend['chart']['type'] == 'line'
    assert trend['explanation'] == 'amount by month of order_date (total).'
    average = ask(client, source, '各 region 的平均 quantity')
    assert len(average['rows']) == 4 and 'AVG' in average['sql']
    summary = ask(client, source, 'amount 的整体概况')
    assert summary['rows'][0][:2] == [60, sum(100 + i for i in range(60))]
    # Fixed phrases still work when no column is named.
    assert ask(client, source, '共有多少行')['rows'] == [[60]]


def test_unknown_question_lists_examples_from_columns(client, source):
    result = ask(client, source, '随便看看')
    assert not result.get('sql') and 'amount' in result['answer']
    english = ask(client, source, 'anything interesting?', 'en-US')
    assert english['answer'].startswith('Demo mode recognizes column names') and 'amount' in english['answer']


def test_rates_are_averaged_and_suggested_last():
    table = {'name': 't', 'schema': '', 'columns': [{'name': 'region', 'type': 'VARCHAR'},
        {'name': 'margin_rate', 'type': 'DOUBLE'}, {'name': 'revenue', 'type': 'DOUBLE'}]}
    assert classify(table)[0] == ['revenue', 'margin_rate']
    sql, explanation, _ = rule_plan('按 region 汇总 margin_rate', {'dialect': 'duckdb', 'tables': [table]})
    assert 'AVG("margin_rate")' in sql and '平均' in explanation


def test_rule_plans_use_dialect_month_functions():
    table = {'name': 'orders', 'schema': 'public', 'columns': [
        {'name': 'created_at', 'type': 'TIMESTAMP'}, {'name': 'total', 'type': 'NUMERIC'}]}
    sql, _, chart = rule_plan('monthly total trend', {'dialect': 'postgres', 'tables': [table]})
    assert "TO_CHAR(CAST(\"created_at\" AS DATE), 'YYYY-MM')" in sql and '"public"."orders"' in sql and chart == 'line'
    sql, _, _ = rule_plan('monthly total trend', {'dialect': 'mysql', 'tables': [{**table, 'schema': ''}]})
    assert "DATE_FORMAT(`created_at`, '%Y-%m')" in sql
    assert rule_plan('hello', {'dialect': 'mysql', 'tables': [table]}) is None
