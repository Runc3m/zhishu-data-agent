"""Offline bilingual retrieval probe. Synthetic glossary, not business answer accuracy."""
import json
from pathlib import Path
from backend.retrieval import retrieve_knowledge

TOPICS = [
 ('退款归属原订单购买月份，只有成功退款才计入。','退款应计入哪个月？','Which month should a successful refund belong to?'),
 ('客户复购统计必须按客户唯一标识去重，而不是订单客户编号。','复购客户如何去重？','Which identifier deduplicates returning customers?'),
 ('准时交付按实际送达日期不晚于预计送达日期判断。','怎样判定按时送达？','How is on-time delivery determined?'),
 ('取消率的分母是同一购买区间内的全部订单，分子是取消订单。','订单取消比例怎么计算？','What is the denominator of the cancellation rate?'),
 ('商品成交额不包含运费，统计已交付订单的商品金额。','成交额含运费吗？','Does delivered merchandise value include shipping fees?'),
 ('支付记录可能一单多条，须先按订单汇总后与商品明细关联。','支付表和明细表怎样避免重复计费？','How can joining payments and items avoid double counting?'),
 ('邮政编码对应多个地理坐标，关联前须先汇总成每邮编一行。','邮编连接地理表为什么会放大数据？','Why does joining the postcode geography table duplicate rows?'),
 ('成本数据缺失时无法计算利润，不允许用销售额代替利润。','没有成本能算利润吗？','Can profit be calculated without cost data?'),
 ('广告花费和归因收入均不存在，因此不能计算广告回报率。','能否计算投放回报？','Is advertising return on investment available?'),
 ('平均客单价以已交付商品成交额除以已交付订单数量计算。','客单价怎么计算？','How do you calculate average order value?'),
 ('加载水位记录最后成功处理的批次，日期最大值不能证明完整加载。','怎样判断数据完整加载？','Does the maximum date prove ingestion completeness?'),
 ('日报表版本应引用最新订单事实版本，否则报表可能未刷新。','如何判断日报表陈旧？','How can we detect a stale daily report?'),
 ('评分均值按评价记录计算，重复评价不能默认按订单唯一处理。','评价记录按什么粒度计算？','What is the grain of review scores?'),
 ('商品类别需要使用类别翻译表，原始类别名称采用葡萄牙语。','商品分类英文名从哪里来？','Where do English product category names come from?'),
 ('缺失送达日期的订单不能用零天代替交付时长。','送达时间为空如何计算时长？','How should missing delivery timestamps affect delivery duration?'),
 ('订单金额单位是巴西雷亚尔，不能自动按人民币标注。','金额是什么币种？','What currency are monetary amounts expressed in?'),
 ('成交趋势按购买日期归属，不能混用送达日期和支付日期。','成交趋势用哪种日期？','Which timestamp assigns transactions to a sales trend period?'),
 ('原始数据层保留文件字段，清洗层负责时间和金额类型转换。','类型转换发生在哪一层？','Which pipeline layer converts date and amount types?'),
 ('实验数据是原始数据库的独立副本，注入故障不会改写真实数据。','故障实验会修改原始库吗？','Do fault experiments modify the original database?'),
 ('品类贡献之和必须与独立计算的总体变化一致。','如何验证品类变化分解？','How do category contributions reconcile with overall change?'),
]


def main():
    context={'version':1,'notes':'','metrics':'','relationships':'','fields':'\n\n'.join(x[0] for x in TOPICS)}
    source={'id':'retrieval-probe','tables':[]}
    results=[]
    for strategy in ('lexical','hybrid'):
        for i,(text,zh,en) in enumerate(TOPICS):
            for language,question in [('zh-CN',zh),('en-US',en)]:
                found=retrieve_knowledge(context,source,question,limit=3,strategy=strategy)
                results.append({'strategy':strategy,'actual_mode':found['mode'],'case':i,'language':language,
                                'hit_at_3':any(p['text']==text for p in found['passages']),
                                'retrieved':[p['id'] for p in found['passages']]})
    summary=[{'strategy':s,'language':lang,'hits':sum(r['hit_at_3'] for r in results if r['strategy']==s and r['language']==lang),'total':len(TOPICS)} for s in ('lexical','hybrid') for lang in ('zh-CN','en-US')]
    path=Path('evaluation-results/retrieval.json');path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({'method':'Synthetic Chinese-only glossary; lexical vs hybrid top-3 retrieval, no mandatory constraints or answer leakage. Not an end-to-end business benchmark.','summary':summary,'results':results},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary))


if __name__=='__main__': main()
