"""factors/volatility/vol_60d.py — 低波因子：60 日年化波动率（聚宽 Variance60 → sqrt + 年化）。"""
from __future__ import annotations

import numpy as np
import pandas as pd

from factors._base import FactorEntry, FactorMeta, register


META = FactorMeta(
    name="vol_60d",
    chinese_name="60 日年化波动率",
    category="volatility",
    description=(
        "过去 60 个交易日日收益率的年化标准差。低波动率股票长期跑赢"
        "（Ang-Hodrick-Xing-Zhang 2006），在 A 股 2014-2024 也验证过。"
        "本仓库基于聚宽 Variance60（60 日方差），开方 + 年化 ×sqrt(252)。"
        "direction=descending（波动率越低 → 预期收益越高）。"
    ),
    paper_refs=(
        "Ang, Hodrick, Xing, Zhang (2006) The Cross-Section of Volatility and Expected Returns",
        "Asness, Frazzini, Pedersen (2014) Low-Risk Investing without Industry Bets",
    ),
    direction="descending",
    jq_dependencies=("jqfactor.Variance60",),
    recommended_neutralization=("SIZE", "industry"),
    known_issues=(
        "次新股 / 停牌后复牌的波动率噪音大，聚宽因子库通常已剔除",
        "Variance60 是方差不是波动率，必须 sqrt 才有正确量纲",
        "波动率与 beta、市值都高相关，独立信号弱",
    ),
)


def compute_jq(context, universe):
    from jqfactor import get_factor_values
    data = get_factor_values(
        securities=universe, factors=["Variance60"],
        end_date=context.previous_date, count=1,
    )
    variance = data["Variance60"].iloc[-1]
    # 方差 → 标准差 → 年化（×sqrt(252)）
    return np.sqrt(variance.clip(lower=0)) * np.sqrt(252)


def compute_local(date, universe):
    from jqdatasdk import get_factor_values
    data = get_factor_values(
        securities=universe, factors=["Variance60"],
        end_date=str(date)[:10], count=1,
    )
    variance = data["Variance60"].iloc[-1]
    return np.sqrt(variance.clip(lower=0)) * np.sqrt(252)


register(FactorEntry(meta=META, compute_jq=compute_jq, compute_local=compute_local,
                     module=__name__))
