"""factors/growth/revenue_growth_yoy.py — 成长因子：营业收入同比。"""
from __future__ import annotations

from factors._base import FactorEntry, FactorMeta, register


META = FactorMeta(
    name="revenue_growth_yoy",
    chinese_name="营业收入同比增速",
    category="growth",
    description=(
        "TTM 营业收入同比增长率。"
        "和 net profit growth 比，营收增长更难被操纵（毛利率调整影响 net 但不影响 revenue），"
        "在 A 股周期/成长股切换的市场里更稳。"
    ),
    paper_refs=(
        "Lakonishok, Shleifer, Vishny (1994) Contrarian Investment, Extrapolation, and Risk",
        "中信证券《选股因子系列：成长因子》",
    ),
    direction="ascending",
    jq_dependencies=("indicator.inc_revenue_year_on_year",),
    recommended_neutralization=("log_mcap", "industry"),
    known_issues=(
        "周期股的同比受基期影响（疫情后/疫情前对比不公平）",
        "并购重组导致的收入跳升应该剔除",
        "营收增长 ≠ 利润增长，组合使用更稳",
    ),
)


def compute_jq(context, universe):
    df = get_fundamentals(
        query(indicator.code, indicator.inc_revenue_year_on_year)
        .filter(indicator.code.in_(universe)),
        date=context.current_dt.strftime("%Y-%m-%d"),
    )
    return df.set_index("code")["inc_revenue_year_on_year"]


register(FactorEntry(meta=META, compute_jq=compute_jq, module=__name__))
