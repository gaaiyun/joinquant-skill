"""factors/size/log_market_cap.py — 规模因子：聚宽 CNE5 SIZE 因子。"""
from __future__ import annotations

from factors._base import FactorEntry, FactorMeta, register


META = FactorMeta(
    name="log_market_cap",
    chinese_name="CNE5 标准化市值 SIZE",
    category="size",
    description=(
        "聚宽 CNE5 风格因子 SIZE。"
        "**重要：聚宽返回的 SIZE 是横截面 z-score 标准化后的 ln(总市值)**，"
        "不是原始 ln(market_cap)；该值横截面均值约为 0、std 约为 1。"
        "如果只想拿原始 ln(总市值)，请直接用 valuation.market_cap 自行计算。"
        "小盘股长周期超额收益（A 股尤其显著），direction=descending —— "
        "SIZE 越低（小盘）预期收益越高。常用作中性化协变量。"
    ),
    paper_refs=(
        "Banz (1981) The Relationship Between Return and Market Value of Common Stocks",
        "Barra CNE5 model — SIZE",
    ),
    direction="descending",
    jq_dependencies=("jqfactor.SIZE",),
    recommended_neutralization=(),   # SIZE 本身就是 z-score 后的值，无须二次标准化
    known_issues=(
        "聚宽 SIZE 是已标准化后的值，不是原始 ln(market_cap)——名字虽叫 log_market_cap，实际取值与一般定义有偏差",
        "A 股 2017-2019 大盘股行情下小盘因子失效",
        "中证 1000 / 2000 之外的小票流动性差，建议先剔除",
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
