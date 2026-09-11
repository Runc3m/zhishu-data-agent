# 知数 · Data Agent

一个可以在本机运行的中文数据分析网页。产品方向参考 [DataHub Analytics Agent](https://github.com/datahub-project/analytics-agent)，本项目独立实现代码与界面，适合继续开发自己的 Data Agent。

## 日常使用：双击即可，不用 CMD

在这台开发电脑上，双击项目文件夹中的 **`Zhishu.lnk`** 或 **`打开知数.vbs`**。

启动中心会自动打开浏览器，保留原来 `storage/` 中的 Key、数据和对话。启动中心可以最小化，使用完点“退出知数”。关闭网页不会停止程序，重复双击入口会重新打开网页而不会重复启动同一份数据。

默认地址是 http://127.0.0.1:8100；端口被占用时免安装程序会自动选用附近的可用端口。网页本身不能启动已经关闭的本地服务，因此请双击应用入口，不要只收藏本地网址。

## 发给别人使用

发送 **`release/Zhishu-Windows-x64.zip`**，不要发送整个项目目录。

对方将 ZIP **完整解压**，双击里面的 `Zhishu.exe` 即可，不需要安装 Python、Node.js 或运行命令。`_internal/` 必须与 exe 一起保留。包内附带使用说明；未签名的自制程序可能出现来源提醒，请核实来源，不要关闭安全软件。

分享包不含制作者的 Key、导入数据和分析历史。对方第一次启动是规则演示模式，需要 AI 时填写自己的 DeepSeek Key。数据默认保存在 `%LOCALAPPDATA%\ZhishuDataAgent\storage`，每个 Windows 用户独立保存。此目录不会随安装包分享；不要主动把此目录发给别人。

`127.0.0.1` 是每个人自己的电脑，不是公网网址。当前方案适合个人或小范围分发；需要所有人只打开一个网址时，应另外部署服务器、HTTPS、登录、权限、用户数据隔离与用量控制，不能直接把当前单用户接口暴露到公网。

## 开发者启动与打包

`start.cmd` / `start.ps1` 保留为开发入口，需要保持终端开启。自定义端口：

```powershell
.\start.ps1 -Port 8101
```

首次在其他机器运行建议 Python 3.13（本次验证版本）。脚本会创建 `.venv` 并按 `requirements.lock.txt` 安装已验证的依赖。若未带构建产物，还需要 Node.js 22+ 与 pnpm。修改前端后运行：

```powershell
.\start.ps1 -Rebuild
```

## 使用方式

1. 默认使用规则演示模式：内置 720 条明确标注的模拟订单（2026 年 1–8 月）。点击“各地区销售额对比”“每月销售趋势”“各品类利润排名”“销售概览”，查看真实执行的 SQL、表格和图表。
2. “添加数据”支持 CSV（UTF-8 / GB18030，首行为字段名，单文件最多 20 MB、100,000 行、120 列）。CSV 导入后表名为 `data`；字段中的标点归一为下划线，重复名称自动加后缀。
3. 数据库连接支持 PostgreSQL、MySQL，读取指定 Schema 中的前 30 张数据表。使用只读账号。PostgreSQL 默认 Schema 为 `public`，MySQL 留空时使用数据库名。
4. 打开“模型设置”，切换为“AI 分析”，保留默认 DeepSeek，粘贴自己的 API Key，点击“验证并启用”。无需填写网址和模型名；已保存的 Key 留空即可继续使用。只有选择“其他兼容服务 / 本地模型”才需要地址和模型名，本地 Ollama 可以不填密钥。
5. 继续在同一对话里追问，如“那利润呢”“只看第二季度”“改成折线图”。点击“新建分析”开始独立对话。切换数据源也会开启新的分析上下文。
6. 分析结果支持图表类型切换、表格排序和分页、实际执行 SQL 展示与复制、CSV 下载；底部可导出 Markdown 分析记录。历史对话和导入数据会保留到下次启动。

模型预设与其他服务（DeepSeek 预设按 2026-09-08 的官方文档与真实调用验证）：

| 服务 | API 根地址 | 模型名称示例 |
| --- | --- | --- |
| DeepSeek（自动配置） | `https://api.deepseek.com` | `deepseek-v4-flash` |
| Ollama | `http://localhost:11434/v1` | 你已下载且支持指令的模型名称 |
| 其他兼容服务 | 服务商提供的 HTTPS API 根地址 | 服务商提供的模型名称 |

请不要把密钥写进源码或发到聊天中。密钥及数据库密码在本机加密保存，前端仅收到“是否已配置”的标志。AI 模式将问题、表结构、最近最多 10 条对话内容及 SQL、最多 30 行查询结果发送至你指定的模型服务。规则演示模式不调用模型。

DeepSeek 使用官方 [Chat API](https://api-docs.deepseek.com/)；该有界文本工作流关闭默认[思考模式](https://api-docs.deepseek.com/guides/thinking_mode/)，避免短测试只消耗推理 token 而没有最终内容。已加入 SOCKS 代理依赖，支持现有 HTTP/SOCKS 环境代理。Key 无效、余额不足、超时和网络错误会显示对应提示。

## 已实现的 Agent 流程

```text
问题 + 最近对话
  → 读取当前数据源的真实表结构
  → LLM 返回结构化查询计划 / 必要的澄清问题
  → SQLGlot 解析、只读检查、表与函数白名单
  → 数据引擎执行（单条限时 8 秒）
  → 错误反馈给模型，最多修正 2 次，每次重新校验
  → 根据真实查询结果生成中文总结
  → 返回 ECharts 图表配置、表格、SQL
  → 保存对话、结果与导出记录
```

前端用 SSE 接收步骤、查询计划、SQL 和最终结果。模型请求本身为完整响应，网页展示的是步骤流，不是逐 token 文本流。这里使用显式 Python 工作流实现 Agent，便于理解和修改，未引入 LangGraph。

## 工程结构

```text
backend/
  app.py         FastAPI 接口、SSE、导入、导出、本机访问校验
  agent.py       查询计划、模型调用、有限重试、演示规则、结果总结
  engines.py     DuckDB / PostgreSQL / MySQL 数据接入与执行
  safety.py      SQL AST 校验、表/函数白名单与行数限制
  store.py       SQLite 持久化、凭据加密
frontend/src/
  main.tsx       React 工作台、设置、对话、表格与 ECharts
  style.css      桌面和窄屏样式
tests/
  test_agent.py  数据查询、模型协议、修复与拒绝路径测试
storage/         本机生成的数据库、CSV 导入数据与 local.key（不入版本控制）
launcher.py      无命令行窗口的启动中心、端口选择、重复启动处理
Zhishu.lnk       本机双击入口，使用项目 storage
打开知数.vbs     本机备用双击入口
release/         Windows 免安装应用与干净的分享 ZIP
start.ps1        开发安装、构建和启动脚本
build-windows.ps1  打包脚本，只收集代码、网页和依赖
```

技术栈：React / TypeScript / Vite / ECharts；Python / FastAPI / SQLAlchemy / DuckDB / SQLGlot / SQLite。

## 开发与验证

后端开发：

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8100 --reload
```

前端开发（另开终端）：

```powershell
cd frontend
pnpm install --frozen-lockfile
pnpm dev
```

访问 http://127.0.0.1:5173 。前端将 `/api` 请求代理到 8100。生产运行由 FastAPI 直接托管构建好的前端，只需要一个服务。

```powershell
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
pnpm build
```

更新前端构建后，在项目目录执行以下命令可重新打包（先退出运行中的免安装程序）：

```powershell
.\build-windows.ps1
.\create-shortcut.ps1
.\.venv\Scripts\python.exe tests\smoke_windows.py release\Zhishu\Zhishu.exe
```

验收包括 51 项自动测试、真实 DeepSeek 连接和模拟销售数据分析、独立 EXE 的干净启动/端口冲突/重复启动/SQL/图表/CSV/导出以及分享包隐私检查。EXE 在当前 Windows x64 电脑运行验收，尚未覆盖其他系统版本。

## 当前边界

- 这是本机单用户 MVP：默认只监听 `127.0.0.1`，没有登录、多租户、角色管理或公网部署配置。数据库只读事务与 SQL 校验不能替代正式数据库账号的最小权限。
- 实现了原项目的核心问数链路，没有复制 DataHub 元数据平台、SSO、上下文质量评分、知识回写等企业功能。
- 演示模式只有有限的中文规则；不支持的问题会提示启用 AI，绝不会将演示模式伪装成模型分析。
- 数据查询最多返回 500 行，图表最多展示其中 50 组，总结最多发送前 30 行；超限会明确标记。不要把截断后的明细当作全量统计，统计应在 SQL 中完成。
- 数据库连接时保存表结构快照；结构变化后需重新添加数据源。暂不支持跨数据源 JOIN、Excel 文件和任意 Python 执行。
- 已使用用户自己的 DeepSeek Key 对连接和模拟销售数据分析进行真实验收；PostgreSQL / MySQL 尚未用真实服务器凭据验收。
- 本地密钥文件和密文放在同一工作目录，提供静态加密，不抵御能够读取整个本机目录的攻击者。备份 `storage/` 时应完整保存并保护其中的 `local.key`。

SQL 校验参考：[SQLGlot 官方文档](https://sqlglot.com/)。DuckDB 执行连接禁止外部文件访问与扩展自动安装，参照 [DuckDB 官方安全说明](https://duckdb.org/docs/current/operations_manual/securing_duckdb/overview)。
