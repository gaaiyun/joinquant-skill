# -*- coding: utf-8 -*-
"""
案例：6 ETF 动量轮动，TOP 2，周度调仓
基于 templates/03-etf-rotation.py 修改
"""


ETF_POOL = (
    '510300.XSHG',  # 沪深300ETF
    '510500.XSHG',  # 中证500ETF
    '159915.XSHE',  # 创业板ETF
    '518880.XSHG',  # 黄金ETF
    '511010.XSHG',  # 国债ETF
    '513100.XSHG',  # 纳指ETF
)
TOP_K = 2
LOOKBACK = 20


def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)

    set_order_cost(OrderCost(
        open_tax=0, close_tax=0,
        open_commission=0.0003, close_commission=0.0003,
        close_today_commission=0, min_commission=5,
    ), type='fund')
    set_slippage(PriceRelatedSlippage(0.00246))

    run_weekly(rebalance, weekday=1, time='09:31')


def rebalance(context):
    scores = {}
    for etf in ETF_POOL:
        close = attribute_history(etf, LOOKBACK + 1, '1d', ['close'])['close']
        if len(close) < 2:
            continue
        momentum = close.iloc[-1] / close.iloc[0] - 1
        scores[etf] = momentum

    if not scores:
        return

    import pandas as pd
    ranked = pd.Series(scores).sort_values(ascending=False)
    target = ranked.head(TOP_K).index.tolist()

    for etf in list(context.portfolio.positions.keys()):
        if etf not in target:
            order_target(etf, 0)
            log.info('轮出 %s (动量 %.2f%%)' % (etf, scores.get(etf, 0) * 100))

    weight = 1.0 / TOP_K
    for etf in target:
        order_target_value(etf, context.portfolio.total_value * weight)
        log.info('轮入 %s (动量 %.2f%%)' % (etf, ranked[etf] * 100))
