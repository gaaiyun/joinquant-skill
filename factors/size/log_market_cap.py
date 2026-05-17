"""factors/size/log_market_cap.py — 规模因子：对数总市值（小盘正向）。"""
from __future__ import annotations

import numpy as np

from factors._base import FactorEntry, FactorMeta, register


META = FactorMeta(
    name="log_market_cap",
    chinese_name="对数总市值（小盘）",
    category="size",
    description=(
        "log(总市值)。小盘股长周期超额收益（A 股尤其显著），"
        "本因子为「**小盘正向**」 — direction=descending（log_mcap 越低 → 收益越高）。"
        "也常作为协变量做中性化。"
    ),
    paper_refs=(
        "Banz (1981) The Relationship Between Return and Market Value of Common Stocks",
        "Liu, Stambaugh, Yuan (2019) Size and value in China",
    ),
    direction="descending",
    jq_dependencies=("valuation.market_cap",),
    recommended_neutralization=(),   # 自己就是规模因子，不需再中性化
    known_issues=(
        "A 股 2017-2019 大盘股行情下小盘因子失效",
        "中证 1000 / 2000 之外的小票流动性差，需要剔除",
    ),
)


def compute_jq(context, universe):
    import pandas as pd
    df = get_fundamentals(
        query(valuation.code, valuation.market_cap).filter(valuation.code.in_(universe)),
        date=context.current_dt.strftime("%Y-%m-%d"),
    )
    df["log_mcap"] = np.log(df["market_cap"] * 1e8)
    return df.set_index("code")["log_mcap"]


register(FactorEntry(meta=META, compute_jq=compute_jq, module=__name__))
