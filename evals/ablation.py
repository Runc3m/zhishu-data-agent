"""Small same-question comparison; no claim that retrieval must beat full context."""
import json
import sys
from pathlib import Path

import backend.agent as agent_module
from backend.retrieval import documents, retrieve_knowledge
from evals.warehouse import main as evaluate


def main():
    original = agent_module.retrieve_knowledge
    argv = sys.argv[:]
    reports=[]
    try:
        for strategy in ('lexical','hybrid','full_context'):
            def retrieval(context,source,question):
                if strategy != 'full_context':
                    return retrieve_knowledge(context,source,question,strategy=strategy)
                docs=[{**d,'score':0} for d in documents(context,source)]
                return {'mode':'full_context_baseline','model':None,'passages':docs,'constraints':[],
                        'notice':'Evaluation only: all available context, no selective retrieval.'}
            agent_module.retrieve_knowledge=retrieval
            output=Path(f'evaluation-results/ablation-{strategy}.json')
            sys.argv=['evals.warehouse','--live','--app-storage','storage','--skip-investigations',
                      '--case','gmv','--case','buyers','--case','profit','--output',str(output)]
            evaluate()
            report=json.loads(output.read_text(encoding='utf-8'))
            reports.append({'strategy':strategy,'passed':report['passed'],'total':report['total'],
                            'model_calls':sum(r['model_calls'] for r in report['results']),
                            'seconds':round(sum(r['seconds'] for r in report['results']),2)})
    finally:
        sys.argv=argv
        agent_module.retrieve_knowledge=original
    Path('evaluation-results/ablation-summary.json').write_text(json.dumps(reports,indent=2),encoding='utf-8')
    print(json.dumps(reports))


if __name__=='__main__': main()
