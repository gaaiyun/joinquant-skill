"""factors/size/log_market_cap.py — 规模因子：聚宽 CNE5 SIZE 因子。"""
from __future__ import annotations

from factors._base import FactorEntry, FactorMeta, register


META = FactorMeta(
    name="log_market_cap",
    chinese_name="对数总市值 (CNE5 SIZE)",
    category="size",
    description=(
        "log(总市值)。小盘股长周期超额收益（A 股尤其显著）。"
        "聚宽 CNE5 SIZE = ln(总市值)，已经做了标准化。"
        "本因子为「**小盘正向**」 — direction=descending（SIZE 越低 → 收益越高）。"
        "也常作为协变量做中性化（中性化时 direction 不影响）。"
    ),
    paper_refs=(
        "Banz (1981) The Relationship Between Return and Market Value of Common Stocks",
        "Barra CNE5 model — SIZE",
    ),
    direction="descending",
    jq_dependencies=("jqfactor.SIZE",),
    recommended_neutralization=(),
    known_issues=(
        "A 股 2017-2019 大盘股行情下小盘因子失效",
        "中证 1000 / 2000 之外的小票流动性差，需要剔除",
    ),
)


def compute_jq(context, universe):
    from jqfactor import get_factor_values
    data = get_factor_values(
        securities=universe, factors=["SIZE"],
        end_date=context.previous_date, count=1,
    )
    return data["SIZE"].iloc[-1]


def compute_local(date, universe):
    from jqdatasdk import get_factor_values
    data = get_factor_values(
        securities=universe, factors=["SIZE"],
        end_date=str(date)[:10], count=1,
    )
    return data["SIZE"].iloc[-1]


register(FactorEntry(meta=META, compute_jq=compute_jq, compute_local=compute_local,
                     module=__name__))
