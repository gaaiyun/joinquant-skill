"""factors/value/book_to_market.py — 价值因子：账面市值比 B/M (= 1/PB)。"""
from __future__ import annotations

from factors._base import FactorEntry, FactorMeta, register


META = FactorMeta(
    name="book_to_market",
    chinese_name="账面市值比",
    category="value",
    description=(
        "BM = 净资产 / 总市值 = 1 / PB。"
        "Fama-French HML 因子的基础，A 股长周期 IC 约 0.03-0.06。"
        "与 E/P 中度相关，建议二者择一或合成。"
    ),
    paper_refs=(
        "Fama & French (1992)",
        "中信证券《选股因子系列：BP 在 A 股的实证》",
    ),
    direction="ascending",
    jq_dependencies=("valuation.market_cap", "balance.total_owner_equities"),
    recommended_neutralization=("log_mcap", "industry"),
    known_issues=(
        "金融股 BM 通常很高但收益未必好（行业内分位更可靠）",
        "BM < 0 的股票（资不抵债）应剔除",
    ),
)


def compute_jq(context, universe):
    """聚宽实现：BM = total_owner_equities / market_cap（注意单位对齐）。"""
    df = get_fundamentals(
        query(
            valuation.code,
            valuation.market_cap,        # 亿元
            balance.total_owner_equities,  # 元
        ).filter(valuation.code.in_(universe)),
        date=context.current_dt.strftime("%Y-%m-%d"),
    )
    df["bm"] = (df["total_owner_equities"] / 1e8) / df["market_cap"]
    df.loc[df["bm"] <= 0, "bm"] = float("nan")
    return df.set_index("code")["bm"]


register(FactorEntry(meta=META, compute_jq=compute_jq, module=__name__))
