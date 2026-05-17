"""factors/quality/roe_ttm.py — 质量因子：TTM 净资产收益率。"""
from __future__ import annotations

from factors._base import FactorEntry, FactorMeta, register


META = FactorMeta(
    name="roe_ttm",
    chinese_name="TTM ROE",
    category="quality",
    description=(
        "ROE = TTM 归母净利润 / 平均净资产。"
        "Novy-Marx (2013) 把 gross profitability 作为 quality 代表；ROE 是中国 A 股"
        "更常用的 quality 代理。与价值因子合成（QV）通常显著优于单一因子。"
    ),
    paper_refs=(
        "Novy-Marx (2013) The Other Side of Value: The Gross Profitability Premium",
        "中信证券《选股因子系列：质量因子》",
    ),
    direction="ascending",
    jq_dependencies=("indicator.roe", "indicator.eps"),
    recommended_neutralization=("log_mcap", "industry"),
    known_issues=(
        "杠杆放大 ROE，建议与 leverage 协整看",
        "金融股 ROE 偏高且稳定，需行业内分位",
    ),
)


def compute_jq(context, universe):
    df = get_fundamentals(
        query(indicator.code, indicator.roe).filter(indicator.code.in_(universe)),
        date=context.current_dt.strftime("%Y-%m-%d"),
    )
    return df.set_index("code")["roe"]


register(FactorEntry(meta=META, compute_jq=compute_jq, module=__name__))
