# -*- coding: utf-8 -*-
"""
05 — 均值回归策略（布林带 + RSI）
适用场景：单股票或小池子，价格偏离均值时反向操作。
使用方法：修改 STOCKS, BB_PERIOD, RSI_PERIOD 后粘贴到聚宽运行。
"""


STOCKS = ('000001.XSHE', '600036.XSHG')   # ← 交易池
BB_PERIOD = 20        # ← 布林带周期
BB_WIDTH = 2.0        # ← 布林带宽度（标准差倍数）
RSI_PERIOD = 14       # ← RSI 周期
RSI_OVERSOLD = 30     # ← RSI 超卖阈值（买入信号）
RSI_OVERBOUGHT = 70   # ← RSI 超买阈值（卖出信号）
MAX_POS_PER_STOCK = 0.4  # ← 单只股票最大仓位比例


def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)

    set_order_cost(OrderCost(
        open_tax=0, close_tax=0.001,
        open_commission=0.0003, close_commission=0.0003,
        close_today_commission=0, min_commission=5,
    ), type='stock')
    set_slippage(PriceRelatedSlippage(0.00246))

    run_daily(trade, time='09:31')


def trade(context):
    for security in STOCKS:
        close = attribute_history(
            security, max(BB_PERIOD, RSI_PERIOD) + 5, '1d', ['close']
        )['close']

        if len(close) < BB_PERIOD:
            continue

        price = close.iloc[-1]
        bb_mid, bb_upper, bb_lower = calc_bollinger(close, BB_PERIOD, BB_WIDTH)
        rsi = calc_rsi(close, RSI_PERIOD)

        pos = context.portfolio.positions.get(security)
        has_pos = pos is not None and pos.total_amount > 0

        if price < bb_lower and rsi < RSI_OVERSOLD and not has_pos:
            max_value = context.portfolio.total_value * MAX_POS_PER_STOCK
            available = min(context.portfolio.available_cash * 0.95, max_value)
            if available > price * 100:
                order_value(security, available)
                log.info('均值回归买入 %s | 价格 %.2f < 下轨 %.2f, RSI=%.1f' %
                         (security, price, bb_lower, rsi))

        elif has_pos and (price > bb_upper or rsi > RSI_OVERBOUGHT):
            order_target(security, 0)
            log.info('均值回归卖出 %s | 价格 %.2f > 上轨 %.2f, RSI=%.1f' %
                     (security, price, bb_upper, rsi))


def calc_bollinger(close, period, width):
    """计算布林带"""
    ma = close[-period:].mean()
    std = close[-period:].std()
    return ma, ma + width * std, ma - width * std


def calc_rsi(close, period):
    """计算 RSI"""
    import numpy as np
    delta = close.diff().dropna()
    gain = delta.where(delta > 0, 0)
    loss = (-delta).where(delta < 0, 0)
    avg_gain = gain[-period:].mean()
    avg_loss = loss[-period:].mean()
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)
