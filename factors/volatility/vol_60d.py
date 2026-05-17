"""factors/volatility/vol_60d.py — 低波因子：60 日已实现波动率（反向：低波正向）。"""
from __future__ import annotations

import numpy as np

from factors._base import FactorEntry, FactorMeta, register


META = FactorMeta(
    name="vol_60d",
    chinese_name="60 日已实现波动率",
    category="volatility",
    description=(
        "过去 60 个交易日日收益率的标准差。"
        "低波动率股票长期跑赢高波动率（Ang-Hodrick-Xing-Zhang 2006），"
        "在 A 股 2014-2024 也得到验证，是经典 anomaly。direction=descending。"
    ),
    paper_refs=(
        "Ang, Hodrick, Xing, Zhang (2006) The Cross-Section of Volatility and Expected Returns",
        "Asness, Frazzini, Pedersen (2014) Low-Risk Investing without Industry Bets",
    ),
    direction="descending",
    jq_dependencies=("get_price",),
    recommended_neutralization=("log_mcap", "industry"),
    known_issues=(
        "次新股 / 停牌后复牌的波动率噪音大，需剔除",
        "波动率与 beta、市值都高相关，独立信号弱",
    ),
)


def compute_jq(context, universe):
    import pandas as pd
    prices = get_price(
        universe, end_date=context.previous_date, count=61,
        fields=["close"], panel=False, fq="pre",
    )
    close = prices.set_index(["time", "code"])["close"].unstack("code")
    if len(close) < 61:
        return pd.Series(dtype=float)
    log_ret = np.log(close / close.shift(1)).dropna()
    return log_ret.std(ddof=1) * np.sqrt(252)   # 年化


register(FactorEntry(meta=META, compute_jq=compute_jq, module=__name__))
