# Installation and usage

[简体中文](usage.zh-CN.md) · [Home](../README.en.md)

## Launch

Supports Windows 10/11 x64. Download the ZIP from [Releases](https://github.com/Runc3m/zhishu-data-agent/releases), extract it completely and double-click `Zhishu.exe`. Do not copy the EXE alone. Port 8100 is the default, with a nearby free port selected when occupied. Select Open workspace to reopen the interface. Keep the launch center open and select Quit Zhishu when finished.

The application is not code-signed yet. If Windows reports an unknown publisher, verify the source and supplied SHA-256 checksum before deciding to run it. Do not disable system protection.

## First analysis

Choose Sample sales data and a suggested question. Results offer charts, sortable tables and SQL, with follow-ups in the same conversation. Download CSV from the result toolbar or export Markdown beneath the question box. Switch 简体中文 / English at the top right; the preference survives restarts. Historical text and original data are not translated again.

## Add data

CSV headers are column names. UTF-8 / GB18030 are supported, up to 20 MB, 100,000 rows and 120 columns per file. Imported data uses the `data` table. Demo supports “Preview the first 20 rows” and “How many rows are there?”. Enable AI for other questions.

Connect to PostgreSQL / MySQL using a read-only account. The first 30 tables in the selected schema are inspected. Cross-source queries are unsupported. Queries return up to 500 rows, charts show up to 50 groups and each query has an 8-second timeout.

## Storage and updates

Packaged storage is `%LOCALAPPDATA%\ZhishuDataAgent\storage`; source runs use the project’s `storage` directory. `Zhishu.exe --data-dir <directory>` opens existing storage. Different directories are separate workspaces.

Quit Zhishu and back up the entire storage directory, including databases and `local.key`, before updating. Extract and launch the new version without overwriting or deleting storage. Share the original Release ZIP, not your personal data directory.


## Local development edition: InsightBridge / 知数

The English product name is **InsightBridge**; the Chinese name remains 知数. Existing repository URLs, storage paths, health-check IDs and historical release filenames remain compatible. These changes have not yet been published as a new Windows package.

- **Bilingual retrieval**: FastEmbed / ONNX Runtime runs pretrained multilingual-e5-small locally; RRF combines semantic and BM25 rankings. Retrieve fields, metrics, schemas and ETL, preserving mandatory metric exclusions and relationship constraints. Missing embeddings visibly fall back to keywords. No request-time downloads; complete business snapshots are retained for audit rather than injected wholesale.
- **Investigation**: choose Automatic, Single query or Investigation beside the input. AI investigations allow five successful analytical queries and two repairs in total, and stop repeated queries. Up to three additional read-only source diagnostics run first. A soft 180-second budget is checked before starting another step; in-flight calls may exceed it.
- **Inspectable evidence**: each step exposes executed SQL, rows and truncation. Retrieved passages, observations, reconciliation and stopping reasons persist in history and Markdown exports.
- **Summary scope**: numeric profiles cover all returned rows, with a sample of at most 30 rows. A capped result is not the full database; population claims require aggregate SQL. Mechanical column sums do not imply additive business metrics.

An imported Olist warehouse is selected first; otherwise Commerce investigation demo is used. Its first card compares August with July 2026 through five executed queries: order coverage and quality, refund quality and relationships, overall totals, category contributions, and a follow-up on the largest contributor. Synthetic net sales are CNY 5,890 → 4,960, a change of -930. Electronics contributes -1,240, Home +310, and Sports 0; the breakdown reconciles.

Two further cards demonstrate ambiguous refund-rate definitions and missing September data. This rule demo supports its card questions only. Edited demo definitions require AI mode; the original Sales demo remains available separately.

For your own CSV or database, enable AI. Automatic diagnostics inspect only selected typed columns, not every quality condition. Date bounds alone do not prove ingestion completeness. Verify model-generated reconciliation and causal claims against evidence. Mocked-planner tests do not measure real-model accuracy; live evaluation needs a configured provider.

## Olist warehouse and experiments

Install `requirements-rag.txt`, then run `python -m scripts.setup_warehouse --download --embeddings`, or upload the official Olist ZIP. The warehouse has 13 tables and 99,441 orders, denominated in BRL. The data page shows table lineage and actual ETL SQL and creates isolated control/fanout/missing-date/status-filter/stale-mart copies. Select a copy and choose Investigation. Registered pipelines allow 8 tool actions and 2 repairs with independent checks and citation audits.
