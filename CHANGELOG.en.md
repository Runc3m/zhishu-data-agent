# Changelog

[简体中文](CHANGELOG.md) · [Home](README.en.md)

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
