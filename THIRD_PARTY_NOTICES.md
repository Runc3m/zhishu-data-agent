# Third-party notices / 第三方许可与致谢

Original Zhishu code is MIT licensed. Dependencies retain their own terms; the project license does not replace them. Release archives include collected dependency license texts in `licenses/`.

知数自有代码使用 MIT。依赖保留各自条款，项目许可不取代依赖许可。发布包 `licenses/` 收录依赖许可文本。

| Component / 组件 | License / 许可 |
| --- | --- |
| React, Vite, Lucide | MIT |
| TypeScript, Apache ECharts | Apache-2.0 |
| zrender, pandas, NumPy | BSD-3-Clause and bundled notices |
| FastAPI, SQLAlchemy, SQLGlot, DuckDB, PyMySQL | MIT |
| Starlette, HTTPX, Uvicorn | BSD-3-Clause |
| cryptography | Apache-2.0 OR BSD-3-Clause and bundled notices |
| psycopg / psycopg-binary | LGPL-3.0-or-later and bundled notices |
| Python, Tcl/Tk | PSF and bundled Tcl/Tk notices |
| FastEmbed, ONNX Runtime, multilingual-e5-small model | Apache-2.0, MIT, MIT respectively; optional local retrieval |
| Olist Brazilian E-Commerce public dataset | CC BY-NC-SA 4.0; separate user download, not bundled in Git |
| PyInstaller | GPL-2.0-or-later with distribution exception |

Versions: `requirements.lock.txt`, `requirements-build.txt`, `frontend/pnpm-lock.yaml`. Original distributed texts govern exact terms and bundled-library details. / 确切版本见锁定文件，具体条款和捆绑库信息以原始许可为准。

## Product inspiration / 产品思路借鉴

The schema → SQL → execution → explanation workflow was informed by [DataHub Analytics Agent](https://github.com/datahub-project/analytics-agent). Zhishu is independently implemented, not an official DataHub product, affiliated release or fork distribution. / 工作流思路借鉴 DataHub Analytics Agent；知数是独立实现，不是其官方产品、关联版本或分叉发行版。

The investigation design also draws on [WrenAI](https://github.com/Canner/WrenAI) for explicit business semantics and [Microsoft Data Formulator](https://github.com/microsoft/data-formulator) for inspectable exploration history. These are architectural references; no source code from these projects was copied or vendored. / 业务语义与探索记录参考上述项目的设计；未复制或捆绑其源码。

Runtime reuse: [DuckDB](https://duckdb.org/) handles CSV ingestion and SQL execution; [SQLGlot](https://github.com/tobymao/sqlglot) handles SQL parsing and table dependencies; [FastEmbed](https://github.com/qdrant/fastembed) handles ONNX tokenization, pooling and normalization using the publisher's [multilingual-e5-small](https://huggingface.co/intfloat/multilingual-e5-small) model. Model revision is recorded in local `provenance.json`. No model is trained by this application.

Conversational BI enhancements continue to use [Apache ECharts](https://echarts.apache.org/en/feature.html) for chart rendering and interactions, and SQLGlot for AST-based checks of known order/item grain contracts. Follow-up UX references [Wren AI answer components](https://docs.getwren.ai/oss/guide/home/answer). No Wren AI source code is copied.
