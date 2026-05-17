"""factors/momentum/ret_12m_skip_1m.py — 12 月动量剔近 1 月（直接调聚宽 MOMENTUM）。"""
from __future__ import annotations

from factors._base import FactorEntry, FactorMeta, register


META = FactorMeta(
    name="ret_12m_skip_1m",
    chinese_name="12 月动量（剔近 1 月）",
    category="momentum",
    description=(
        "经典 Jegadeesh-Titman 动量因子：过去第 -12 到 -2 个月的累计收益。"
        "剔最近 1 个月避开短期反转（Lehmann 1990）。"
        "本仓库调用聚宽 CNE5 风格因子 MOMENTUM（已是 12-1 累计的标准实现）。"
    ),
    paper_refs=(
        "Jegadeesh & Titman (1993) Returns to Buying Winners and Selling Losers",
        "Barra CNE5 model — MOMENTUM",
    ),
    direction="ascending",
    jq_dependencies=("jqfactor.MOMENTUM",),
    recommended_neutralization=("SIZE", "industry"),
    known_issues=(
        "A 股短期反转占主导，建议在中小盘上谨慎",
        "牛市末期 / 熊市初期动量崩塌（Daniel-Moskowitz 2016）",
    ),
)


def compute_jq(context, universe):
    from jqfactor import get_factor_values
    data = get_factor_values(
        securities=universe, factors=["MOMENTUM"],
        end_date=context.previous_date, count=1,
    )
    return data["MOMENTUM"].iloc[-1]


def compute_local(date, universe):
    from jqdatasdk import get_factor_values
    data = get_factor_values(
        securities=universe, factors=["MOMENTUM"],
        end_date=str(date)[:10], count=1,
    )
    return data["MOMENTUM"].iloc[-1]


register(FactorEntry(meta=META, compute_jq=compute_jq, compute_local=compute_local,
                     module=__name__))
