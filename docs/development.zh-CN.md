# 开发与构建

[English](development.en.md) · [首页](../README.md)

验证环境：Windows x64、Python 3.13、Node.js 22+、pnpm 11.19.0。

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.lock.txt
cd frontend
pnpm install --frozen-lockfile
pnpm build
cd ..
.\.venv\Scripts\python -m uvicorn backend.app:app --host 127.0.0.1 --port 8100
```

也可运行 `start.ps1 -Rebuild`。前端 `pnpm dev` 代理 API 到 8100。使用 `DATA_AGENT_STORAGE` 为测试服务指定独立存储目录。

## 结构

`backend/agent.py` 编排计划、只读执行、最多两次修正和总结；`engines.py` 管理数据连接；`store.py` 保存设置与历史；`app.py` 提供 API 与事件流；`frontend/src` 为 React / ECharts 界面；`launcher.py` 管理服务生命周期。

翻译集中于前后端 `locales`，通过 `i18n` 模块访问。`GET/PUT /api/preferences` 保存语言；消息请求可传 `language`，旧客户端使用已保存偏好。用户数据和历史正文不翻译。

## 验证与发布

```powershell
.\.venv\Scripts\python -m pytest -q
cd frontend
pnpm build
cd ..
.\build-windows.ps1
.\.venv\Scripts\python tests/smoke_windows.py release/Zhishu/Zhishu.exe
```

测试使用临时数据与模拟模型，不需要 Key。根目录 `VERSION` 为版本来源；前端包元数据保留同步版本，由测试检查。打包只包含应用资源、双语说明与依赖许可，不含用户存储。

推送和 Pull Request 自动测试与构建。`v*` 标签从指定版本构建并验证独立 EXE，创建 Release 草稿，维护者核验后发布。发布后不移动标签。
