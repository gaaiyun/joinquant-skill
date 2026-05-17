"""factors/quality/roe_ttm.py — 质量因子：TTM 净资产收益率（聚宽 ROE_TTM）。"""
from __future__ import annotations

from factors._base import FactorEntry, FactorMeta, register


META = FactorMeta(
    name="roe_ttm",
    chinese_name="TTM ROE",
    category="quality",
    description=(
        "ROE TTM = 滚动 12 月归母净利润 / 平均净资产。"
        "Novy-Marx (2013) 把 gross profitability 作为 quality 代表；"
        "聚宽因子库提供 ROE_TTM（TTM 累加，按报告期推近期）。"
        "与价值因子合成（QV 双因子）通常显著优于单一因子。"
    ),
    paper_refs=(
        "Novy-Marx (2013) The Other Side of Value: The Gross Profitability Premium",
        "聚宽因子库 - 质量因子 ROE_TTM",
    ),
    direction="ascending",
    jq_dependencies=("jqfactor.ROE_TTM",),
    recommended_neutralization=("SIZE", "industry"),
    known_issues=(
        "杠杆放大 ROE，建议与 LEVERAGE 协整看",
        "金融股 ROE 偏高且稳定，需行业内分位",
    ),
)


def compute_jq(context, universe):
    from jqfactor import get_factor_values
    data = get_factor_values(
        securities=universe, factors=["ROE_TTM"],
        end_date=context.previous_date, count=1,
    )
    return data["ROE_TTM"].iloc[-1]


def compute_local(date, universe):
    from jqdatasdk import get_factor_values
    data = get_factor_values(
        securities=universe, factors=["ROE_TTM"],
        end_date=str(date)[:10], count=1,
    )
    return data["ROE_TTM"].iloc[-1]


register(FactorEntry(meta=META, compute_jq=compute_jq, compute_local=compute_local,
                     module=__name__))
