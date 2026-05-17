"""factors/reversal/ret_5d.py — 短期反转：5 日收益率（反向）。"""
from __future__ import annotations

from factors._base import FactorEntry, FactorMeta, register


META = FactorMeta(
    name="ret_5d",
    chinese_name="5 日收益率（短期反转）",
    category="reversal",
    description=(
        "过去 5 个交易日累计收益率。"
        "Lehmann (1990) 和 Jegadeesh (1990) 发现短期（1 日-1 月）有强反转效应——"
        "近期涨多了未来跌、跌多了未来涨。在 A 股短期反转效应显著强于美股。"
        "direction=descending。"
    ),
    paper_refs=(
        "Lehmann (1990) Fads, Martingales, and Market Efficiency",
        "Jegadeesh (1990) Evidence of Predictable Behavior of Security Returns",
    ),
    direction="descending",
    jq_dependencies=("get_price",),
    recommended_neutralization=("log_mcap", "industry"),
    known_issues=(
        "高频反转——换手率高，交易成本可能吃掉收益",
        "停牌 / 涨跌停后的反转包含噪声",
        "与流动性因子高度相关",
    ),
)


def compute_jq(context, universe):
    import pandas as pd
    prices = get_price(
        universe, end_date=context.previous_date, count=6,
        fields=["close"], panel=False, fq="pre",
    )
    close = prices.set_index(["time", "code"])["close"].unstack("code")
    if len(close) < 6:
        return pd.Series(dtype=float)
    return close.iloc[-1] / close.iloc[0] - 1.0


register(FactorEntry(meta=META, compute_jq=compute_jq, module=__name__))
