"""Opt-in live evaluation. Never used by the normal CI test suite."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

from backend.agent import Agent
from backend.engines import Engines
from backend.store import Store
from backend.version import VERSION
from .business import CASES, CONTEXT, seed_business


def matches(result, case):
    if not result or result.get('error'):
        return False
    if case['rows'] is None:
        return not result.get('sql') and bool(result.get('answer'))
    rows = result.get('rows', [])
    if len(rows) != len(case['rows']):
        return False
    for actual, expected in zip(rows, case['rows']):
        if len(actual) != len(expected):
            return False
        for a, e in zip(actual, expected):
            if isinstance(e, (int, float)):
                if not isinstance(a, (int, float)) or not math.isclose(a, e, rel_tol=1e-9, abs_tol=.005):
                    return False
            elif a != e:
                return False
    return True


def evaluate(config, case, language):
    with tempfile.TemporaryDirectory(prefix='zhishu-live-eval-') as temp:
        store = Store(Path(temp))
        source = seed_business(store)
        if case['context_override']:
            store.save_business_context(source['id'], {**CONTEXT, **case['context_override']})
        store.save_settings({**config, 'mode': 'llm'})
        cid = store.create_conversation(source['id'])['id']
        events = list(Agent(store, Engines(store)).run(cid, case[language], language))
        result = next((e['result'] for e in events if e['type'] == 'result'), None)
        record = {'case': case['id'], 'language': language, 'question': case[language],
                  'passed': matches(result, case), 'expected_rows': case['rows'],
                  'actual_rows': result.get('rows') if result else None,
                  'sql': result.get('sql') if result else None,
                  'answer': result.get('answer') if result else None,
                  'context_version': result.get('context_version') if result else None,
                  'errors': [e['message'] for e in events if e['type'] == 'error']}
        print(f"{language} {case['id']}: {'PASS' if record['passed'] else 'FAIL'}", flush=True)
        return record


def main():
    parser = argparse.ArgumentParser(description='Run synthetic business questions against a real model (provider fees apply).')
    parser.add_argument('--live', action='store_true', required=True)
    parser.add_argument('--app-storage', type=Path, help='Explicitly use model settings from an existing local workspace, read-only.')
    parser.add_argument('--output', type=Path, default=Path('evaluation-results/live.json'))
    parser.add_argument('--workers', type=int, choices=range(1,5), default=1)
    parser.add_argument('--case', action='append', dest='cases')
    args = parser.parse_args()
    if args.app_storage:
        if not (args.app_storage / 'app.sqlite3').exists() or not (args.app_storage / 'local.key').exists():
            parser.error('Existing application storage not found.')
        config = Store(args.app_storage).settings(private=True)
    else:
        config = {'provider': 'custom', 'base_url': os.environ.get('ZHISHU_EVAL_BASE_URL', 'https://api.deepseek.com'),
                  'model': os.environ.get('ZHISHU_EVAL_MODEL', ''), 'api_key': os.environ.get('ZHISHU_EVAL_API_KEY', '')}
        if not config['model']:
            parser.error('Set ZHISHU_EVAL_MODEL and provider credentials, or use --app-storage.')
    selected = [case for case in CASES if not args.cases or case['id'] in args.cases]
    if not selected:
        parser.error('No matching evaluation cases.')
    jobs = [(case, language) for language in ('zh-CN','en-US') for case in selected]
    started = datetime.now(timezone.utc).isoformat()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        records = list(pool.map(lambda pair: evaluate(config, *pair), jobs))
    report = {'version': VERSION, 'started_at': started, 'completed_at': datetime.now(timezone.utc).isoformat(),
              'model': config['model'], 'provider': config.get('provider'),
              'agent_sha256': hashlib.sha256(Path('backend/agent.py').read_bytes()).hexdigest(),
              'fixture_sha256': hashlib.sha256(Path('evals/business.py').read_bytes()).hexdigest(),
              'passed': sum(record['passed'] for record in records), 'total': len(records),
              'method': 'Live model planning and summarization; real read-only queries; golden result comparison. Clarification cases require no SQL and a nonempty answer; inspect their wording manually.',
              'results': records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"Result: {report['passed']}/{report['total']} | {args.output}")
    return 0 if report['passed'] == report['total'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
