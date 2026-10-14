# 真实数据与调查

[English](warehouse.en.md) · [首页](../README.md)

## 导入 Olist

1. 从 [Olist 官方数据页](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) 下载 Brazilian E-Commerce ZIP。
2. 在知数选择“添加数据源 → ZIP 数据包”，上传包含九个 CSV 的原始 ZIP。
3. 选择新数据源，在模型设置启用 AI 后提问，例如“按月统计 2017 年已交付商品成交额和订单数”。

Windows 发布包和源码版都支持 ZIP 导入。数据包上限为压缩后 256 MB、解压后 512 MB、20 个 CSV。Olist 九文件会生成 13 张表，保留 2016–2018 年原始日期和 BRL 币种，不重写为当前日期。

Olist 是匿名历史数据，遵循 CC BY-NC-SA 4.0；不随仓库或发行包分发。缺少成本、库存和退款流水时，不能据此计算利润或完整净收入。

## 沿处理链路排查

在数据源页展开“数据处理链路”，查看原始层、清洗层、订单事实、日报表的依赖、实际 SQL 和加载记录。可以从原始仓库建立正常对照或四种故障的独立实验副本：关联金额放大、漏日期、状态过滤错误、陈旧报表。

选择副本，启用 AI 并使用“多步调查”。已注册管道最多执行 8 次工具行动和 2 次修复，可核对金额、订单覆盖、报表对账与刷新版本。实验标签不传入模型，原始数据库不会被实验修改。

表级血缘来自 SQLGlot 解析，不覆盖任意 ETL 语言；独立检查不保证源系统本身完整。引用审计只确认引用存在，解释与因果关系仍需人工复核。

## 可选：源码版混合检索

在项目根目录执行：

```powershell
.\.venv\Scripts\python -m pip install -r requirements-rag.txt
.\.venv\Scripts\python -m scripts.setup_warehouse --download --embeddings
```

已下载数据时，用 `--archive 文件路径` 代替 `--download`。FastEmbed / ONNX Runtime 加载预训练 multilingual-e5-small；BM25 与向量结果通过 RRF 合并。无需训练，首次设置需要联网。

检索覆盖字段、指标、表结构和 ETL，最多返回 8 个片段，另外保留指标排除条件与关联约束。请求期间不下载模型；缺失或不可用时明确显示关键词检索。Windows 发布包只提供关键词检索，不捆绑 FastEmbed、ONNX 或模型文件。

## 评测

`python -m evals.warehouse --live --app-storage storage` 使用所配置的模型运行公开数据评测，会消耗 API 额度。`python -m evals.retrieval` 检查离线检索。对话分析使用 `python -m evals.conversation --help` 查看运行参数。

结果写入忽略目录 `evaluation-results/`。评测范围和已公开的结果见[评测说明](evaluation.zh-CN.md)。
