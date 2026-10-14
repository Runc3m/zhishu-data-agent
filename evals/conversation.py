"""Opt-in real-model conversational BI smoke evaluation (not a general accuracy benchmark).
Run: python -m evals.conversation --live --app-storage storage
"""
import argparse
import json
import tempfile
import time
from pathlib import Path
from backend.store import Store
from backend.engines import Engines
from backend.agent import Agent


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live",action="store_true")
    parser.add_argument("--app-storage",type=Path,default=Path("storage"))
    parser.add_argument("--output",type=Path,default=Path("evaluation-results/bi-conversation.json"))
    args=parser.parse_args()
    if not args.live:
        parser.error("--live is required: this uses the configured provider and may incur API charges")
    original=Store(args.app_storage)
    source=next(s for s in original.sources() if s.get("dataset")=="olist" and not s.get("experiment"))
    with tempfile.TemporaryDirectory() as directory:
        store=Store(Path(directory)); store.save_source(source)
        store.save_business_context(source["id"],original.business_context(source["id"]))
        store.save_settings(original.settings(private=True))
        engines=Engines(store); agent=Agent(store,engines); records=[]
        # Independent reference at raw item grain; no reference answers enter model prompts.
        expected=engines.query(source,"SELECT t.product_category_name_english AS category, ROUND(SUM(CAST(i.price AS DECIMAL(18,2))),2) AS gmv FROM raw_order_items i JOIN raw_orders o ON o.order_id=i.order_id JOIN raw_products p ON p.product_id=i.product_id LEFT JOIN raw_category_translation t ON t.product_category_name=p.product_category_name WHERE o.order_status='delivered' GROUP BY 1 ORDER BY 2 DESC LIMIT 1")["rows"][0]
        for language,questions in [("zh-CN",["哪个卖的最好","看不懂，解释一下","所以我该优先经营什么品类？给我具体建议和需要验证的风险。"]),("en-US",["Which sells best?","Explain this simply","What should I prioritize, and what should I validate before deciding?"])]:
            cid=store.create_conversation(source["id"])["id"]
            for index,question in enumerate(questions):
                start=time.monotonic(); events=list(agent.run(cid,question,language=language))
                result=next((e["result"] for e in events if e["type"]=="result"),None)
                checks={"responded":bool(result),"no_stream_error":not any(e["type"]=="error" for e in events)}
                if result:
                    if index==0:
                        checks["multiple_panels"]=len(result.get("panels",[]))>=2
                        checks["gmv_leader_matches_independent_raw_query"]=any(r and r[0]==expected[0] and any(isinstance(v,(int,float)) and abs(v-expected[1])<.01 for v in r[1:]) for panel in result.get("panels",[]) for r in panel["rows"][:1])
                    if index==1:
                        report=result.get("report") or {}
                        checks["explains_saved_evidence"]=bool(result.get("based_on_message_id")) and not result.get("sql")
                        checks["short_sections"]=len(report.get("findings",[]))<=2 and not report.get("actions")
                    if index==2:
                        checks["actionable_report"]=bool((result.get("report") or {}).get("actions"))
                records.append({"question":question,"language":language,"seconds":round(time.monotonic()-start,1),"checks":checks,"result":result})
                args.output.parent.mkdir(parents=True,exist_ok=True)
                args.output.write_text(json.dumps({"model":store.settings()["model"],"scope":"Six conversational smoke cases, not overall model accuracy. Narrative claims still need review.","independent_reference":expected,"records":records},ensure_ascii=False,indent=2),encoding="utf-8")
                print(json.dumps({"language":language,"case":index,"checks":checks}),flush=True)
        if not all(all(r["checks"].values()) for r in records):
            raise SystemExit(1)


if __name__=="__main__":
    main()
