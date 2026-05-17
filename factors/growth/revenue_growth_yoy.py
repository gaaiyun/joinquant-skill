"""factors/growth/revenue_growth_yoy.py — 成长因子：营业收入同比（聚宽 inc_revenue_year_on_year）。"""
from __future__ import annotations

from factors._base import FactorEntry, FactorMeta, register


META = FactorMeta(
    name="revenue_growth_yoy",
    chinese_name="营业收入同比增速",
    category="growth",
    description=(
        "TTM 营业收入同比增长率。"
        "和 net profit growth 比，营收增长更难被操纵（毛利率调整影响 net "
        "但不影响 revenue），在 A 股周期 / 成长股切换的市场里更稳。"
        "聚宽 inc_revenue_year_on_year 已按季度更新。"
    ),
    paper_refs=(
        "Lakonishok, Shleifer, Vishny (1994) Contrarian Investment, Extrapolation, and Risk",
        "聚宽因子库 - 成长因子",
    ),
    direction="ascending",
    jq_dependencies=("jqfactor.inc_revenue_year_on_year",),
    recommended_neutralization=("SIZE", "industry"),
    known_issues=(
        "周期股的同比受基期影响（疫情后 / 疫情前对比不公平）",
        "并购重组导致的收入跳升应该剔除",
        "营收增长 ≠ 利润增长，组合使用更稳",
    ),
)


def compute_jq(context, universe):
    from jqfactor import get_factor_values
    data = get_factor_values(
        securities=universe, factors=["inc_revenue_year_on_year"],
        end_date=context.previous_date, count=1,
    )
    return data["inc_revenue_year_on_year"].iloc[-1]


def compute_local(date, universe):
    from jqdatasdk import get_factor_values
    data = get_factor_values(
        securities=universe, factors=["inc_revenue_year_on_year"],
        end_date=str(date)[:10], count=1,
    )
    return data["inc_revenue_year_on_year"].iloc[-1]


register(FactorEntry(meta=META, compute_jq=compute_jq, compute_local=compute_local,
                     module=__name__))
