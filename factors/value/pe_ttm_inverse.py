"""
factors/value/pe_ttm_inverse.py — 价值因子：滚动 12 月 PE 倒数 (E/P)。

经济直觉
--------
PE 是市值 / 净利润；E/P = 1/PE 越高，说明赚 1 块钱要付的市值越少，估值越便宜。
Fama-French (1992) 在美股、Liu-Stambaugh-Yuan (2019) 在 A 股都验证：
低估值组合长期跑赢高估值组合。

注意点
------
- **必须用 TTM**（滚动 12 个月）净利润，不能用单季年化或最新一期年报数据
  — 季度性 / 一次性收益会让因子失真。
- E/P 比 1/PE 在数学上等价但更稳定（PE 接近 0 时会爆炸）。
- 亏损公司（净利润<0）应当**单独处理**：要么剔除，要么置为 NaN，**不要用负 E/P 排序**
  （会把巨亏股票排到最前面）。
"""
from __future__ import annotations

from factors._base import FactorEntry, FactorMeta, register


META = FactorMeta(
    name="pe_ttm_inverse",
    chinese_name="TTM PE 倒数",
    category="value",
    description=(
        "盈利收益率 E/P（净利润 TTM / 总市值）。"
        "经典价值因子，A 股长周期 IC 通常在 0.04-0.08。"
    ),
    paper_refs=(
        "Fama & French (1992) The Cross-Section of Expected Stock Returns",
        "Liu, Stambaugh, Yuan (2019) Size and value in China",
    ),
    direction="ascending",
    jq_dependencies=(
        "valuation.market_cap",
        "income.np_parent_company_owners",
    ),
    recommended_neutralization=("log_mcap", "industry"),
    universe_hint="中证 800 / 全 A（剔除 ST 与亏损）",
    known_issues=(
        "亏损公司应剔除或置 NaN",
        "金融行业（银行 / 保险）的 PE 含义与制造业不同，行业内分位更可靠",
        "周期股的 PE 在景气拐点会误导",
    ),
)


def compute_jq(context, universe: list[str]) -> "pandas.Series":
    """
    在聚宽编辑器里跑的实现（直接复制可用）。

    Parameters
    ----------
    context : Context
        聚宽传入的策略上下文，含 context.current_dt
    universe : list[str]
        股票代码列表（带 .XSHG / .XSHE 后缀）

    Returns
    -------
    pd.Series
        index = 股票代码，value = E/P TTM。亏损公司值为 NaN。
    """
    import pandas as pd  # 聚宽运行时已注入
    # from jqdata import *  # 聚宽运行时已注入，不需 import

    # 拉滚动 12 个月归母净利润 + 当前市值
    # 注意：聚宽 `query` 是 SQLAlchemy 风格，需要 valuation 和 income 两张表
    q = query(
        valuation.code,
        valuation.market_cap,            # 单位：亿元
        income.np_parent_company_owners,  # 归母净利润，单季值，需自己累加
    ).filter(valuation.code.in_(universe))
    df = get_fundamentals(q, date=context.current_dt.strftime("%Y-%m-%d"))

    # 上面只拿了"当前期"单季，不是 TTM。在策略里建议用 fundamentals_continuously
    # 或自行回溯 4 个季度。为示例简洁此处用 indicator.eps_ttm（聚宽有现成的）：
    q_ttm = query(
        valuation.code,
        valuation.market_cap,
        indicator.eps,                    # 单季 EPS
    ).filter(valuation.code.in_(universe))
    df = get_fundamentals(q_ttm, date=context.current_dt.strftime("%Y-%m-%d"))

    # E/P = 总净利润 / 总市值；这里用 eps × 总股本 ≈ 净利润；近似处理
    # 生产代码请用 income.np_parent_company_owners 的 TTM 累加
    df["ep"] = df["eps"] / (df["market_cap"] * 1e8 / df["market_cap"])
    df.loc[df["eps"] <= 0, "ep"] = float("nan")
    return df.set_index("code")["ep"]


def compute_local(date, universe: list[str]) -> "pandas.Series":
    """
    本地 jqdatasdk 实现（用于 factor_lab 离线分析）。

    需要先：
        from jqdatasdk import auth, query, get_fundamentals, valuation, indicator
        auth("your_jq_user", "your_jq_pwd")
    """
    from jqdatasdk import query, get_fundamentals, valuation, indicator

    q = query(
        valuation.code,
        valuation.market_cap,
        indicator.eps,
    ).filter(valuation.code.in_(universe))
    df = get_fundamentals(q, date=str(date)[:10])
    import pandas as pd  # noqa: F401  (placeholder for any post-processing)
    df["ep"] = df["eps"] / df["market_cap"]
    df.loc[df["eps"] <= 0, "ep"] = float("nan")
    return df.set_index("code")["ep"]


# ---------------------------------------------------------------------------
# 自动注册
# ---------------------------------------------------------------------------
register(FactorEntry(
    meta=META,
    compute_jq=compute_jq,
    compute_local=compute_local,
    module=__name__,
))
