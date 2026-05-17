"""factors/momentum/ret_12m_skip_1m.py — 12 月动量（剔除最近 1 个月）。"""
from __future__ import annotations

from factors._base import FactorEntry, FactorMeta, register


META = FactorMeta(
    name="ret_12m_skip_1m",
    chinese_name="12 月动量（剔近 1 月）",
    category="momentum",
    description=(
        "经典 Jegadeesh-Titman 动量因子：用过去第 -12 到 -2 个月的累计收益排序。"
        "剔最近 1 个月是为了避开短期反转效应（Lehmann 1990）。"
        "美股长周期有效，A 股部分时段失效（短期反转更强），常需配合质量因子使用。"
    ),
    paper_refs=(
        "Jegadeesh & Titman (1993) Returns to Buying Winners and Selling Losers",
        "Asness, Moskowitz, Pedersen (2013) Value and Momentum Everywhere",
    ),
    direction="ascending",
    jq_dependencies=("get_price",),
    recommended_neutralization=("log_mcap", "industry"),
    known_issues=(
        "A 股短期反转占主导，建议在中小盘上谨慎",
        "牛市末期/熊市初期动量崩塌（Daniel-Moskowitz 2016）",
        "需中性化市值否则被小盘信号污染",
    ),
)


def compute_jq(context, universe):
    """聚宽实现：取 252 个交易日前到 21 个交易日前的累计收益。"""
    end_date = context.previous_date     # 防未来函数
    prices = get_price(
        universe, end_date=end_date, count=252,
        fields=["close"], panel=False, fq="pre",
    )
    # MultiIndex (time, code)
    close = prices.set_index(["time", "code"])["close"].unstack("code")
    if len(close) < 252:
        import pandas as pd
        return pd.Series(dtype=float)
    ret = close.iloc[-21] / close.iloc[0] - 1.0   # 第 252 日 → 第 21 日的累计
    return ret


register(FactorEntry(meta=META, compute_jq=compute_jq, module=__name__))
