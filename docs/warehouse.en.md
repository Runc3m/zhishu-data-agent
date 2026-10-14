# Real data and investigations

[简体中文](warehouse.zh-CN.md) · [Home](../README.en.md)

## Import Olist

1. Download the Brazilian E-Commerce ZIP from the [official Olist dataset page](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce).
2. In InsightBridge, choose Add data source → ZIP data package and upload the original nine-CSV ZIP.
3. Select the source, enable AI in Model settings, and ask, for example, “Show monthly delivered goods value and order counts in 2017.”

Both the Windows package and source edition support ZIP imports. Limits: 256 MB compressed, 512 MB uncompressed, and 20 CSV files. The nine Olist files produce 13 tables, preserving the original 2016–2018 dates and BRL currency.

Olist is anonymized historical data under CC BY-NC-SA 4.0, downloaded separately. Missing cost, inventory, and refund records cannot establish profit or complete net revenue.

## Trace a reporting issue

Expand the data pipeline on the source page to inspect dependencies, actual SQL, and load records for raw tables, staging, order facts, and daily reports. Create a separate control or experiment copy with one of four faults: join fanout, missing dates, incorrect status filtering, or a stale report.

Select the copy, enable AI, and choose Investigation. Registered pipelines allow up to 8 tool actions and 2 repairs, with independent checks for amounts, order coverage, reconciliation, and freshness. Fault labels are not sent to the model; experiments do not modify the original warehouse.

SQLGlot derives table-level lineage, not arbitrary ETL-language lineage. Checks cannot prove the upstream source system is complete. Citation audits check reference existence, not whether causal explanations are correct.

## Optional hybrid retrieval in the source edition

From the project root:

```powershell
.\.venv\Scripts\python -m pip install -r requirements-rag.txt
.\.venv\Scripts\python -m scripts.setup_warehouse --download --embeddings
```

Use `--archive PATH` instead of `--download` for an existing archive. FastEmbed / ONNX Runtime loads pretrained multilingual-e5-small; RRF combines BM25 and vector rankings. No training is needed; initial setup requires network access.

Retrieval covers fields, metrics, schema, and ETL, returning up to 8 passages alongside required exclusions and relationship constraints. No request-time model downloads. Missing or unavailable embeddings produce a visible keyword fallback. The Windows package offers keyword retrieval and excludes FastEmbed, ONNX, and model files.

## Evaluation

`python -m evals.warehouse --live --app-storage storage` runs public-data evaluation with your configured provider and consumes API quota. `python -m evals.retrieval` evaluates retrieval offline. See `python -m evals.conversation --help` for conversational checks.

Results go to the ignored `evaluation-results/` directory. See [evaluation methods and records](evaluation.en.md).
