"""Opt-in real-model evaluation on the local Olist snapshot. Never sends golden answers.

python -m evals.warehouse --live --app-storage storage
Numerical checks are automated; natural-language correctness still needs review.
"""
import argparse
import json
import math
import re
import tempfile
import time
from pathlib import Path

from backend.agent import Agent
from backend.engines import Engines
from backend.store import Store, now
from backend.warehouse import create_experiment

WHERE = " FROM fct_orders WHERE order_status='delivered' AND purchased_at>='2017-01-01' AND purchased_at<'2018-01-01'"
CASES = [
 ('gmv','2017 年已交付商品成交额是多少？','What is delivered GMV for 2017?', 'SELECT ROUND(SUM(item_amount),2)'+WHERE),
 ('count','2017 年已交付订单数是多少？','How many delivered orders were purchased in 2017?', 'SELECT COUNT(*)'+WHERE),
 ('aov','2017 年已交付订单客单价是多少？四舍五入到两位小数。','What is 2017 delivered order AOV, rounded to 2 decimals?', 'SELECT ROUND(AVG(item_amount),2)'+WHERE),
 ('months','按月统计 2017 年已交付商品成交额，按月份升序。','Show monthly 2017 delivered GMV ordered by month ascending.', "SELECT STRFTIME(purchased_at,'%Y-%m'),ROUND(SUM(item_amount),2)"+WHERE+' GROUP BY 1 ORDER BY 1'),
 ('freight','2017 年已交付订单运费合计是多少？','What is total freight for delivered orders purchased in 2017?', 'SELECT ROUND(SUM(freight_amount),2)'+WHERE),
 ('payments','2017 年已交付订单支付金额合计是多少？','What is the total payment amount for delivered orders purchased in 2017?', 'SELECT ROUND(SUM(payment_amount),2)'+WHERE),
 ('items','2017 年已交付订单包含多少商品明细行？','How many item lines belong to delivered orders purchased in 2017?', 'SELECT SUM(item_count)'+WHERE),
 ('delivery','2017 年已交付订单平均交付天数是多少？保留两位小数。','What is mean delivery days for delivered orders purchased in 2017, rounded to 2 decimals?', 'SELECT ROUND(AVG(delivery_days),2)'+WHERE+' AND delivery_days>=0'),
 ('ontime','2017 年已交付订单准时交付率是多少？返回0到1的小数，保留四位。','What is 2017 on-time delivery rate as a 0–1 fraction rounded to 4 decimals?', 'SELECT ROUND(AVG(CAST(on_time AS INTEGER)),4)'+WHERE+' AND on_time IS NOT NULL'),
 ('late','2017 年已交付订单中延期交付订单数是多少？','How many delivered orders purchased in 2017 were late?', 'SELECT COUNT(*)'+WHERE+' AND on_time=false'),
 ('max_amount','2017 年已交付订单中最大的单笔商品金额是多少？','What is the largest item amount of a delivered order purchased in 2017?', 'SELECT MAX(item_amount)'+WHERE),
 ('min_amount','2017 年已交付订单中最小的单笔商品金额是多少？','What is the smallest item amount of a delivered order purchased in 2017?', 'SELECT MIN(item_amount)'+WHERE),
 ('multi_item','2017 年已交付订单中有多少订单包含多条商品明细？','How many delivered orders purchased in 2017 have multiple item lines?', 'SELECT COUNT(*)'+WHERE+' AND item_count>1'),
 ('missing_delivery','2017 年已交付订单中有多少缺失实际送达时间？','How many delivered orders purchased in 2017 have a missing actual delivery timestamp?', 'SELECT COUNT(*)'+WHERE+' AND delivered_at IS NULL'),
 ('cancel_count','2017 年购买的订单中 canceled 状态的订单数是多少？','How many orders purchased in 2017 have canceled status?', "SELECT COUNT(*) FROM fct_orders WHERE order_status='canceled' AND purchased_at>='2017-01-01' AND purchased_at<'2018-01-01'"),
 ('cancel_rate','2017 年订单取消率是多少？返回0到1的小数，保留四位。','What is the 2017 cancellation rate as a 0–1 fraction rounded to 4 decimals?', "SELECT ROUND(SUM(CASE WHEN order_status='canceled' THEN 1 ELSE 0 END)*1.0/COUNT(*),4) FROM fct_orders WHERE purchased_at>='2017-01-01' AND purchased_at<'2018-01-01'"),
 ('states','2017 年已交付订单涉及多少个客户州？','How many customer states are represented in delivered orders purchased in 2017?', "SELECT COUNT(DISTINCT c.customer_state) FROM fct_orders f JOIN raw_customers c USING(customer_id) WHERE f.order_status='delivered' AND f.purchased_at>='2017-01-01' AND f.purchased_at<'2018-01-01'"),
 ('buyers','2017 年已交付订单对应多少不同的真实客户？用 customer_unique_id。','How many unique buyers had delivered orders purchased in 2017? Use customer_unique_id.', "SELECT COUNT(DISTINCT c.customer_unique_id) FROM fct_orders f JOIN raw_customers c USING(customer_id) WHERE f.order_status='delivered' AND f.purchased_at>='2017-01-01' AND f.purchased_at<'2018-01-01'"),
 ('profit','2017 年净利润是多少？','What is net profit for 2017?',None),
 ('roi','2017 年广告投放ROI是多少？','What is advertising ROI for 2017?',None),
]


def compare(actual, expected):
    if len(actual)!=len(expected): return False
    for row, ref in zip(actual,expected):
        if len(row)!=len(ref): return False
        for a,b in zip(row,ref):
            if isinstance(b,(float,int)):
                if not isinstance(a,(float,int)) or not math.isclose(a,b,abs_tol=.005,rel_tol=1e-9): return False
            elif a!=b:
                # Monthly SQL may return YYYY-MM or the first-day timestamp. Both
                # are valid for a request that does not prescribe display format.
                if not (isinstance(a,str) and isinstance(b,str) and re.fullmatch(r'\d{4}-\d{2}',b)
                        and re.fullmatch(re.escape(b)+r'-01(?:[ T]00:00:00)?',a)):
                    return False
    return True


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--live',action='store_true',required=True)
    parser.add_argument('--app-storage',type=Path,default=Path('storage'))
    parser.add_argument('--output',type=Path,default=Path('evaluation-results/warehouse-live.json'))
    parser.add_argument('--case',action='append')
    parser.add_argument('--skip-investigations',action='store_true')
    parser.add_argument('--fault',action='append',choices=['control','fanout','missing_partition','status_filter','stale_mart'])
    args=parser.parse_args()
    original=Store(args.app_storage)
    source=next(s for s in original.sources() if s.get('dataset')=='olist' and not s.get('experiment'))
    config=original.settings(private=True)
    records=[]
    report={'started_at':now(),'model':config['model'],'dataset_sha256':source['archive_sha256'],'results':records,
            'method':'Live API, read-only SQL; numeric golden comparison; refusal and causal wording require manual review. Fault labels are withheld from the agent.'}
    def save():
        args.output.parent.mkdir(parents=True,exist_ok=True)
        report['completed_at']=now()
        report['passed']=sum(r['passed'] for r in records);report['total']=len(records)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    with tempfile.TemporaryDirectory(prefix='insightbridge-eval-',dir=args.app_storage) as temp:
        store=Store(Path(temp));store.save_source(source)
        store.save_business_context(source['id'],original.business_context(source['id']))
        store.save_settings({**config,'mode':'llm'})
        engines=Engines(store);agent=Agent(store,engines)
        import backend.agent as module
        actual_model=module.call_model
        count=0
        def counted(*a,**k):
            nonlocal count
            count+=1
            return actual_model(*a,**k)
        module.call_model=counted
        try:
            for case,zh,en,sql in CASES:
                if args.case and case not in args.case: continue
                expected=engines.query(source,sql)['rows'] if sql else None
                for language,question in [('zh-CN',zh),('en-US',en)]:
                    count=0;started=time.monotonic();cid=store.create_conversation(source['id'])['id']
                    events=list(agent.run(cid,question,language,'query'))
                    result=next((e['result'] for e in events if e['type']=='result'),{})
                    passed=bool(result) and (compare(result.get('rows',[]),expected) if expected is not None else not result.get('sql') and bool(result.get('answer')))
                    records.append({'case':case,'language':language,'passed':passed,'expected':expected,'result':result,
                                    'errors':[e for e in events if e['type']=='error'],'model_calls':count,'seconds':round(time.monotonic()-started,2)})
                    print(case,language,'PASS' if passed else 'FAIL',flush=True);save()
            if not args.skip_investigations:
                for fault in ('control','fanout','missing_partition','status_filter','stale_mart'):
                    if args.fault and fault not in args.fault: continue
                    replica=create_experiment(store,source['id'],fault)
                    for language,question in [('zh-CN','调查日报表是否存在数据问题，沿处理链路定位并验证原因。'),('en-US','Investigate whether the daily report has data issues. Trace the pipeline and verify the cause.')]:
                        count=0;started=time.monotonic();cid=store.create_conversation(replica['id'])['id']
                        events=list(agent.run(cid,question,language,'investigate'))
                        result=next((e['result'] for e in events if e['type']=='result'),{})
                        # Automated evidence gate, NOT a semantic judge of the narrative.
                        checked=result.get('pipeline_checks',{})
                        traced=any(s.get('tool')=='etl' for s in result.get('investigation',[]))
                        queried=any(s.get('tool')=='query' for s in result.get('investigation',[]))
                        passed=bool(result) and checked.get('passed')==(fault=='control') and queried and (fault=='control' or traced) and not result.get('citation_audit',{}).get('unknown')
                        records.append({'case':'investigation_'+fault,'language':language,'passed':passed,'manual_review_required':True,
                                        'result':result,'model_calls':count,'seconds':round(time.monotonic()-started,2)})
                        print(fault,language,'EVIDENCE PASS' if passed else 'EVIDENCE FAIL',flush=True);save()
        finally:
            module.call_model=actual_model
    print('Result',report['passed'],'/',report['total'])


if __name__=='__main__': main()
