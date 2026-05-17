"""factors/quality/gross_profit_margin.py — 质量因子：毛利率（聚宽 gross_profit_margin_ttm）。"""
from __future__ import annotations

from factors._base import FactorEntry, FactorMeta, register


META = FactorMeta(
    name="gross_profit_margin",
    chinese_name="TTM 毛利率",
    category="quality",
    description=(
        "毛利率 TTM = (营业收入 - 营业成本) TTM / 营业收入 TTM。"
        "Novy-Marx (2013) 论文核心因子；强调毛利率比净利润率更难被操纵，"
        "是更纯净的质量信号。聚宽 gross_profit_margin_ttm 已做行业归类。"
    ),
    paper_refs=(
        "Novy-Marx (2013)",
        "Asness, Frazzini, Pedersen (2019) Quality Minus Junk",
    ),
    direction="ascending",
    jq_dependencies=("jqfactor.gross_profit_margin_ttm",),
    recommended_neutralization=("industry",),    # 必须做行业中性化
    known_issues=(
        "不同行业毛利率水平天然不同，**必须**做行业中性化",
        "毛利率突变需谨慎（可能是会计调整）",
    ),
)


def compute_jq(context, universe):
    from jqfactor import get_factor_values
    data = get_factor_values(
        securities=universe, factors=["gross_profit_margin_ttm"],
        end_date=context.previous_date, count=1,
    )
    return data["gross_profit_margin_ttm"].iloc[-1]


def compute_local(date, universe):
    from jqdatasdk import get_factor_values
    data = get_factor_values(
        securities=universe, factors=["gross_profit_margin_ttm"],
        end_date=str(date)[:10], count=1,
    )
    return data["gross_profit_margin_ttm"].iloc[-1]


register(FactorEntry(meta=META, compute_jq=compute_jq, compute_local=compute_local,
                     module=__name__))
