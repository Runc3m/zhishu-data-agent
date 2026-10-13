import csv
import io
import json
import zipfile

import pytest

from backend.engines import Engines
from backend.store import Store
from backend.warehouse import import_package, create_experiment, run_checks, lineage, FILES
from backend.retrieval import retrieve_knowledge, citation_audit


@pytest.fixture
def warehouse(tmp_path):
    rows = {
        'orders': [['order_id','customer_id','order_status','order_purchase_timestamp','order_delivered_customer_date','order_estimated_delivery_date'],
                   ['a','c1','delivered','2017-01-01','2017-01-05','2017-01-06'],
                   ['b','c2','delivered','2017-01-02','2017-01-08','2017-01-06'],
                   ['c','c3','canceled','2017-01-02','','2017-01-06']],
        'order_items': [['order_id','order_item_id','price','freight_value','product_id','seller_id'],['a','1','100','10','p','s'],['a','2','50','5','p','s'],['b','1','80','8','p','s'],['c','1','40','4','p','s']],
        'order_payments': [['order_id','payment_value'],['a','100'],['a','65'],['b','88'],['c','44']],
        'customers': [['customer_id','customer_unique_id'],['c1','u1'],['c2','u2'],['c3','u1']],
    }
    archive = tmp_path/'input.zip'
    with zipfile.ZipFile(archive,'w') as z:
        for file,key in FILES.items():
            out=io.StringIO(); csv.writer(out).writerows(rows.get(key,[['id'],['x']]))
            z.writestr(file,out.getvalue())
    store=Store(tmp_path/'storage')
    source=import_package(store,archive)
    return store,Engines(store),store.source(source['id'])


def test_import_grain_and_lineage(warehouse):
    store, engines, source = warehouse
    assert engines.query(source,'SELECT SUM(item_amount) FROM fct_orders')['rows']==[[270.0]]
    assert engines.query(source,'SELECT SUM(delivered_gmv) FROM mart_daily_sales')['rows']==[[230.0]]
    assert run_checks(engines,source)['passed']
    assert lineage('WITH x AS (SELECT * FROM a) SELECT * FROM x JOIN b ON x.id=b.id')==['a','b']
    assert len(source['tables'])==13


@pytest.mark.parametrize('fault,expected', [('control',[]),('fanout',['fact_amount']),('missing_partition',['raw_coverage']),('status_filter',['mart_reconcile']),('stale_mart',['mart_reconcile','freshness'])])
def test_faults_independently_detected_and_original_preserved(warehouse,fault,expected):
    store,engines,source=warehouse
    replica=create_experiment(store,source['id'],fault)
    result=run_checks(engines,store.source(replica['id']))
    assert [c['id'] for c in result['checks'] if c['status']=='fail']==expected
    assert all(c['status']!='unavailable' for c in result['checks'])
    assert run_checks(engines,source)['passed']
    assert 'fault' not in replica
    assert 'fault' not in engines.schema_context(store.source(replica['id']))


def test_zip_does_not_extract_paths_or_accept_non_csv(tmp_path):
    archive=tmp_path/'input.zip'
    with zipfile.ZipFile(archive,'w') as z: z.writestr('../../outside.csv','a\n1\n')
    store=Store(tmp_path/'storage')
    source=import_package(store,archive)
    assert source['tables'][0]['name']=='outside'
    assert not (tmp_path/'outside.csv').exists()
    with zipfile.ZipFile(archive,'w') as z: z.writestr('run.py','bad')
    with pytest.raises(ValueError, match='Only CSV'): import_package(store,archive)


def test_retrieval_no_network_fallback_and_source_isolation(warehouse,monkeypatch):
    store,_,source=warehouse
    monkeypatch.setenv('INSIGHTBRIDGE_LEXICAL_ONLY','1')
    found=retrieve_knowledge(store.business_context(source['id']),source,'delivered GMV')
    assert found['mode']=='lexical' and found['passages']
    assert all(p['source_id']==source['id'] for p in found['passages'])
    assert citation_audit('unsupported [999]',found['passages'])['unknown']==['999']


def test_pipeline_tool_loop_keeps_evidence(warehouse,monkeypatch):
    from backend.agent import Agent
    store,engines,source=warehouse
    store.save_settings({'mode':'llm','provider':'custom','base_url':'https://example.com','model':'mock'})
    responses=iter([json.dumps({'tool':'etl','argument':'fct_orders'}),json.dumps({'tool':'query','argument':'SELECT SUM(item_amount) FROM fct_orders'}),json.dumps({'tool':'finish','explanation':'done'}),'Verified [1][2][3]'])
    monkeypatch.setattr('backend.agent.call_model',lambda *args,**kwargs:next(responses))
    monkeypatch.setenv('INSIGHTBRIDGE_LEXICAL_ONLY','1')
    cid=store.create_conversation(source['id'])['id']
    events=list(Agent(store,engines).run(cid,'Investigate report','en-US','investigate'))
    result=next(e['result'] for e in events if e['type']=='result')
    assert result['rows']==[[270.0]]
    assert result['pipeline_checks']['passed']
    assert not result['citation_audit']['unknown']
    assert [s['tool'] for s in result['investigation']]==['checks','etl','query']


def test_month_equivalence_does_not_accept_other_dates():
    from evals.warehouse import compare
    assert compare([['2017-01-01 00:00:00',12.3]],[['2017-01',12.3]])
    assert not compare([['2017-01-02',12.3]],[['2017-01',12.3]])
    assert not compare([['2017-01-01',99]],[['2017-01',12.3]])


def test_updated_context_does_not_retrieve_stale_registry(warehouse,monkeypatch):
    store,_,source=warehouse
    monkeypatch.setenv('INSIGHTBRIDGE_LEXICAL_ONLY','1')
    context=store.save_business_context(source['id'],{'metrics':'New confirmed metric: GMV includes freight.'})
    found=retrieve_knowledge(context,source,'GMV')
    assert all(p['section']!='metric' for p in found['passages']+found['constraints'])
    assert any('includes freight' in p['text'] for p in found['constraints'])
