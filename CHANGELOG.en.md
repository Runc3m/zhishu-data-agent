# Changelog

[简体中文](CHANGELOG.md) · [Home](README.en.md)

## Unreleased: real warehouse and bilingual investigations

- Reuse DuckDB for multi-CSV ZIP ingestion; Olist's nine files produce 13 raw/staging/fact/report/load-history tables.
- Reuse FastEmbed, ONNX Runtime and pretrained multilingual E5 with BM25, explicit fallback, context-version isolation and citation checks.
- SQLGlot table lineage, actual ETL, load history, independent reconciliation and read-only investigation tools.
- Four isolated faults plus healthy controls and bilingual pipeline UI; original data remains unchanged.
- Final 143 automated tests passed; real-model business checks 40/40 and investigation evidence gates 10/10. See evaluation docs for scope and limitations.
- Source launcher prefers the project virtual environment. No new Windows binary release.

## 1.1.0

- User-confirmed source notes, column descriptions, metric definitions and relationships.
- Versioned context snapshots; planning, repairs and summaries use the same version, preserved in history and exports.
- 20 paired Chinese/English golden cases and a separate opt-in live-model evaluation runner.
- Fixed AND / OR / NOT being misclassified as unsupported functions in compound filters.
- Clarified that charts are rendered by the interface, not repeated-character drawings in summaries.

Context assists queries, not a full semantic engine. Demo mode does not apply it. Existing storage needs no rebuild.

## 1.0.0

First public release.

- Chinese/English interface, persistent language preference, localized messages and demo examples.
- CSV, PostgreSQL / MySQL, SQL validation, bounded repairs, charts and tables.
- Key-only DeepSeek setup, compatible services and local models.
- History, CSV / Markdown export and existing-storage compatibility.
- Windows launch center, bilingual documentation, automated tests and versioned releases.

Known limitations: local single-user operation; limited demo questions; no Excel, multi-file or cross-source joins; model output requires verification; application not code-signed.

## Unreleased — InsightBridge

- English product name is InsightBridge; Chinese name and existing storage remain compatible.
- Adds BM25 retrieval, bounded AI investigation and source-quality observations.
- Adds a bilingual synthetic commerce investigation with inspectable/exportable evidence.
- Summaries receive profiles of all returned rows with explicit sample and truncation limits.
