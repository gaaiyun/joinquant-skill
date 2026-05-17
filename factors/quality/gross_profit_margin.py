"""factors/quality/gross_profit_margin.py — 质量因子：毛利率。"""
from __future__ import annotations

from factors._base import FactorEntry, FactorMeta, register


META = FactorMeta(
    name="gross_profit_margin",
    chinese_name="毛利率",
    category="quality",
    description=(
        "毛利率 = (营业收入 - 营业成本) / 营业收入。"
        "Novy-Marx (2013) 论文核心因子；强调"
        "毛利率比净利润率更难被操纵，是更纯净的质量信号。"
    ),
    paper_refs=(
        "Novy-Marx (2013)",
        "Asness, Frazzini, Pedersen (2019) Quality Minus Junk",
    ),
    direction="ascending",
    jq_dependencies=("income.total_operating_revenue", "income.total_operating_cost"),
    recommended_neutralization=("industry",),
    known_issues=(
        "不同行业毛利率水平天然不同，**必须**做行业中性化",
        "毛利率突变需谨慎（可能是会计调整）",
    ),
)


def compute_jq(context, universe):
    df = get_fundamentals(
        query(
            income.code,
            income.total_operating_revenue,
            income.total_operating_cost,
        ).filter(income.code.in_(universe)),
        date=context.current_dt.strftime("%Y-%m-%d"),
    )
    df["gpm"] = (df["total_operating_revenue"] - df["total_operating_cost"]) / df["total_operating_revenue"]
    return df.set_index("code")["gpm"]


register(FactorEntry(meta=META, compute_jq=compute_jq, module=__name__))
