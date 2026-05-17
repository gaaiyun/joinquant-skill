"""factors/reversal/ret_5d.py — 短期反转：5 日收益率（手算，聚宽无现成对应）。"""
from __future__ import annotations

import pandas as pd

from factors._base import FactorEntry, FactorMeta, register


META = FactorMeta(
    name="ret_5d",
    chinese_name="5 日收益率（短期反转）",
    category="reversal",
    description=(
        "过去 5 个交易日累计收益率。Lehmann (1990) 与 Jegadeesh (1990) "
        "发现短期（1 日 - 1 月）有强反转效应——近期涨多了未来跌、跌多了未来涨。"
        "A 股短期反转效应显著强于美股。"
        "聚宽因子库未提供 5 日反转的现成因子，本仓库通过 `get_price` 手算。"
        "direction=descending（收益越高 → 未来越可能反转下跌）。"
    ),
    paper_refs=(
        "Lehmann (1990) Fads, Martingales, and Market Efficiency",
        "Jegadeesh (1990) Evidence of Predictable Behavior of Security Returns",
    ),
    direction="descending",
    jq_dependencies=("get_price (close, count=6)",),    # 没有聚宽 factor id
    recommended_neutralization=("SIZE", "industry"),
    known_issues=(
        "高频反转——换手率高，交易成本可能吃掉收益",
        "停牌 / 涨跌停后的反转包含噪声",
        "与流动性因子高度相关",
    ),
)


def compute_jq(context, universe):
    """
    手算实现（聚宽云）：用 get_price 拿 6 个交易日 close → 5 日累计收益。
    用 context.previous_date 避免未来函数。
    """
    prices = get_price(
        universe, end_date=context.previous_date, count=6,
        fields=["close"], panel=False, fq="pre", skip_paused=False,
    )
    # panel=False 返回 long-format DataFrame，列 [time, code, close]
    close_panel = prices.set_index(["time", "code"])["close"].unstack("code")
    if len(close_panel) < 6:
        return pd.Series(dtype=float)
    return close_panel.iloc[-1] / close_panel.iloc[0] - 1.0


def compute_local(date, universe):
    """本地用 jqdatasdk.get_price。"""
    from jqdatasdk import get_price
    prices = get_price(
        security=universe, end_date=str(date)[:10], count=6,
        fields=["close"], panel=False, fq="pre", skip_paused=False,
    )
    close_panel = prices.set_index(["time", "code"])["close"].unstack("code")
    if len(close_panel) < 6:
        return pd.Series(dtype=float)
    return close_panel.iloc[-1] / close_panel.iloc[0] - 1.0


register(FactorEntry(meta=META, compute_jq=compute_jq, compute_local=compute_local,
                     module=__name__))
