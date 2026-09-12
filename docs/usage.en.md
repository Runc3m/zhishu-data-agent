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
