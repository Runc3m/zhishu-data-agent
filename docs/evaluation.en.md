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
