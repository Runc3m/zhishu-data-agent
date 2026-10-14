# Business evaluation

[简体中文](evaluation.zh-CN.md) · [Business context](business-context.en.md)

`evals/business.py` contains independent, public synthetic retail data and golden answers across orders, refunds and items. Each of 20 cases has Chinese and English questions: 40 questions total.

Coverage includes net/gross revenue, completed refunds, eligible orders, average order value, quarterly/monthly boundaries, regional aggregates, distinct refunded orders, duplicate item joins, quantities, cancellations, test exclusions, cents/CNY conversion, missing costs and conflicting definitions.

Manually checkable totals: 6 eligible orders, CNY 2,500 gross revenue, CNY 280 completed refunds and CNY 2,220 net revenue. Two clarification cases should not generate SQL.

## Regression versus live models

`pytest` supplies mocked model plans but runs actual read-only SQL, compares each row against golden answers and checks context versions and repair prompts. It verifies the application pipeline, not a real model’s accuracy, and requires no key.

Run a live evaluation explicitly:

```powershell
.\.venv\Scripts\python -m evals.run --live --app-storage storage --output evaluation-results/live.json
```

The command reads the selected workspace’s model configuration and uses independent temporary data, not existing business records. Provider API fees apply. Alternatively set `ZHISHU_EVAL_BASE_URL`, `ZHISHU_EVAL_MODEL` and `ZHISHU_EVAL_API_KEY` instead of `--app-storage`. Do not put keys in command history or commit them.

Reports contain dates, model, code/data digests, generated SQL, actual values and outcomes, never keys. Checks compare results, not just SQL executability. Clarification cases require no SQL and a nonempty answer, with wording reviewed manually. A single passing run does not guarantee accuracy on real business data.

## v1.1.0 validation record

On 2026-09-12, `deepseek-v4-flash` passed **40/40** questions in this set. The missing-cost and conflicting-definition answers were reviewed individually in both languages: each explained the issue without inventing SQL. See the [public evaluation record](evaluations/v1.1.0-deepseek.json) for questions, SQL, results and code digests. This is one run on a small public benchmark, not a production accuracy claim.

## Investigation regression tests (development edition)

tests/test_investigation.py executes synthetic SQL and checks independently calculated month/category totals. Missing dates, duplicate orders/refunds, null amounts, unknown status and orphan refunds must block comparisons. Mock planners test observation-driven continuation, the five-step cap, repeated-query stopping, read-only repair budgets, evidence preservation after summary failure, bilingual behavior and exports. The original 20 business cases and their English counterparts remain. Mock success rates are not live-model accuracy.

## Olist and bilingual RAG (2026-10-14)

See [recorded evidence](evaluations/insightbridge-olist.json). DeepSeek V4 Flash passed 40/40 numeric/refusal checks across 20 bilingual business questions. The first exact-format comparison was 39/40 because one month column used first-day timestamps instead of YYYY-MM; the numeric results matched, and the comparator now accepts equivalent month labels.

Four faults and a healthy control, each in both languages, passed 10/10 automated evidence gates after an invalid-citation fix. These gates require checks, a query, ETL inspection for faults, and resolvable references; they do not certify every narrative claim. Read explanations against the retained evidence.

On a separate synthetic Chinese-only glossary, Top-3 retrieval was 20/20 for Chinese in both modes, and 0/20 lexical versus 20/20 hybrid for English. In the small end-to-end ablation (3 questions × 2 languages), lexical, hybrid and full-context variants each passed 6/6. This demonstrates cross-language retrieval improvement, not a business-answer accuracy advantage.

Reproduce with `python -m evals.warehouse --live --app-storage storage`, `python -m evals.retrieval`, and `python -m evals.ablation`. Warehouse and ablation use paid provider calls; retrieval is local. The source snapshot has no reliable cost/refund data. Results are single runs, not production guarantees; unsupported generalizations can still appear in model explanations.

## Conversational BI regression

The full backend suite passed 161 tests; targeted post-fix regression passed 78 tests and chart mapping passed six tests. Six live conversational smoke cases (broad ranking, explanation, decision support in each language) passed the specified checks. The GMV leader is independently verified from raw_orders + raw_order_items to detect order/item fan-out errors. See [conversational-bi.json](evaluations/conversational-bi.json).

These six cases are not a general accuracy benchmark. Initial runs exposed duplicated order amounts after item joins and an invalid model object silently accepted as an empty plan; both were repaired before the final rerun. Narrative claims still need human review, and the grain guard covers known direct-join patterns only.

Reproduce with `python -m evals.conversation --live --app-storage storage` (uses saved provider settings and incurs API usage). Run chart tests from frontend with `npm run test:charts`.

Browser validation additionally caught a malformed report with trailing fields. First-object parsing and complete-conclusion recovery were added; 20 related tests passed to prevent raw JSON from appearing in chat.
