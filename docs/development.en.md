# Development and builds

[简体中文](development.zh-CN.md) · [Home](../README.en.md)

Verified environment: Windows x64, Python 3.13, Node.js 22+ and pnpm 11.19.0.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.lock.txt
cd frontend
pnpm install --frozen-lockfile
pnpm build
cd ..
.\.venv\Scripts\python -m uvicorn backend.app:app --host 127.0.0.1 --port 8100
```

Alternatively run `start.ps1 -Rebuild`. Frontend `pnpm dev` proxies APIs to 8100. Set `DATA_AGENT_STORAGE` to isolate test storage.

## Architecture

`backend/agent.py` orchestrates planning, read-only execution, up to two repairs and summarization; `engines.py` manages data connections; `store.py` persists settings and history; `app.py` provides APIs and event streams; `frontend/src` contains React / ECharts; `launcher.py` manages the service lifecycle.

Translations are centralized in frontend/backend `locales` and accessed via `i18n`. `GET/PUT /api/preferences` stores language; message requests may specify `language`, while older clients use the saved preference. Never translate user data or historical content.

## Verification and releases

```powershell
.\.venv\Scripts\python -m pytest -q
cd frontend
pnpm build
cd ..
.\build-windows.ps1
.\.venv\Scripts\python tests/smoke_windows.py release/Zhishu/Zhishu.exe
```

Tests use temporary data and mocked models, with no key required. Root `VERSION` is authoritative; frontend package metadata retains a matching version checked by tests. Packages include application assets, bilingual instructions and dependency licenses, not user storage.

Pushes and pull requests trigger tests and builds. A `v*` tag builds that version, verifies its standalone EXE and creates a Release draft for maintainer review. Do not move published tags.
