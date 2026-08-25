"""
基于盈利质量与动量的多因子选股模型
研报来源：示例证券《选股因子系列：质量动量》2024-09

【自动生成】由 joinquant-skill/research_importer 从研报抽取生成。
生成前请人工 review 因子定义、universe、调仓频率是否正确再投入回测。

Generated factors: roe_ttm, ret_12m_skip_1m, pe_ttm_inverse
Native jqfactor mapping: roe_ttm=ROE_TTM, ret_12m_skip_1m=MOMENTUM, pe_ttm_inverse=EP
"""
from jqdata import *
from jqfactor import get_factor_values
import pandas as pd
import numpy as np


def initialize(context):
    """初始化策略参数。"""
    set_benchmark('000906.XSHG')
    set_option('use_real_price', True)
    set_order_cost(OrderCost(
        open_tax=0, close_tax=0.001,
        open_commission=0.0003, close_commission=0.0003,
        close_today_commission=0, min_commission=5,
    ), type='stock')
    set_slippage(FixedSlippage(0.002), type='stock')

    g.hold_num = 30
    g.factor_weights = {'roe_ttm': 0.4, 'ret_12m_skip_1m': 0.3, 'pe_ttm_inverse': 0.3}
    g.factor_native_ids = {'roe_ttm': 'ROE_TTM', 'ret_12m_skip_1m': 'MOMENTUM', 'pe_ttm_inverse': 'EP'}    # 本仓库因子名 → 聚宽 factor id

    # 调仓调度
    run_monthly(rebalance, 1, time='09:31')


def _get_universe(context):
    """股票池：中证 800 剔除 ST 与停牌。"""
    stocks = get_index_stocks('000906.XSHG')
    current = get_current_data()
    # 过滤 ST、停牌
    stocks = [s for s in stocks if not current[s].is_st and not current[s].paused]
    return stocks


def _compute_factor_scores(context, stocks):
    """从聚宽官方因子库拉 native 因子；已支持的非 native 因子用手算实现。"""
    df = pd.DataFrame(index=stocks)

    # 一次性拉 native 因子（end_date=context.previous_date 避免未来函数）
    native_pairs = {k: v for k, v in g.factor_native_ids.items() if v is not None}
    if native_pairs:
        native_factors = list(set(native_pairs.values()))
        try:
            data = get_factor_values(
                securities=stocks,
                factors=native_factors,
                end_date=context.previous_date,
                count=1,
            )
            for fname, fid in native_pairs.items():
                if fid in data and not data[fid].empty:
                    df[fname] = data[fid].iloc[-1]
        except Exception as exc:
            log.warn('get_factor_values failed: %s' % exc)

    # 全部因子都是 jqfactor native，无需额外计算

    # 标准化每个因子（rank + zscore），按方向调正
    scores = pd.Series(0.0, index=stocks)
    valid_factor_count = 0
    for fname, direction in {'roe_ttm': 'ascending', 'ret_12m_skip_1m': 'ascending', 'pe_ttm_inverse': 'ascending'}.items():
        if fname not in df.columns:
            log.warn('factor %s missing, skip it' % fname)
            continue
        if not df[fname].notna().any():
            log.warn('factor %s has no valid values, skip it' % fname)
            continue
        col = df[fname].rank(method='average')
        sd = col.std(ddof=1)
        col = (col - col.mean()) / sd if sd > 0 else col * 0
        if direction == 'descending':
            col = -col
        scores = scores + g.factor_weights.get(fname, 0) * col.fillna(0)
        valid_factor_count += 1
    if valid_factor_count == 0:
        return pd.Series(dtype=float)
    return scores


def rebalance(context):
    """调仓主入口。"""
    stocks = _get_universe(context)
    scores = _compute_factor_scores(context, stocks)
    target = scores.sort_values(ascending=False).head(g.hold_num).index.tolist()

    # 平掉不在目标里的持仓
    for s in list(context.portfolio.positions):
        if s not in target:
            order_target(s, 0)

    # 等权再平衡
    if target:
        target_value = context.portfolio.total_value / len(target)
        for s in target:
            order_target_value(s, target_value)
