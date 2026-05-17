"""factors/value/book_to_market.py — 价值因子：账面市值比（直接调聚宽 BTOP）。"""
from __future__ import annotations

from factors._base import FactorEntry, FactorMeta, register


META = FactorMeta(
    name="book_to_market",
    chinese_name="账面市值比 (BTOP)",
    category="value",
    description=(
        "BM = 净资产 / 总市值 = 1 / PB。"
        "Fama-French HML 因子的基础，A 股长周期 IC 约 0.03-0.06。"
        "本仓库直接调用聚宽 CNE5 风格因子 BTOP（已做标准化与单位对齐）。"
    ),
    paper_refs=(
        "Fama & French (1992)",
        "Barra CNE5 model",
    ),
    direction="ascending",
    jq_dependencies=("jqfactor.BTOP",),
    recommended_neutralization=("SIZE", "industry"),
    known_issues=(
        "金融股 BM 通常很高但收益未必好（行业内分位更可靠）",
        "BM < 0 的股票（资不抵债）聚宽已处理为缺失",
    ),
)


def compute_jq(context, universe):
    from jqfactor import get_factor_values
    data = get_factor_values(
        securities=universe, factors=["BTOP"],
        end_date=context.previous_date, count=1,
    )
    return data["BTOP"].iloc[-1]


def compute_local(date, universe):
    from jqdatasdk import get_factor_values
    data = get_factor_values(
        securities=universe, factors=["BTOP"],
        end_date=str(date)[:10], count=1,
    )
    return data["BTOP"].iloc[-1]


register(FactorEntry(meta=META, compute_jq=compute_jq, compute_local=compute_local,
                     module=__name__))
