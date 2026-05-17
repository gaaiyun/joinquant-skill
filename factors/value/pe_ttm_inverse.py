"""
factors/value/pe_ttm_inverse.py — 价值因子：E/P (TTM 盈利收益率)。

经济直觉
--------
E/P = TTM 净利润 / 总市值。越高估值越便宜。Fama-French (1992) 在美股、
Liu-Stambaugh-Yuan (2019) 在 A 股都验证：低估值组合长期跑赢。

⚠️ 实现说明
-----------
聚宽官方因子库**已经有 `EP` 因子**（= 1 / PE_TTM），且做了 winsorize / 缺失
处理。我们**直接用官方**，不手算（减少踩坑）。

→ 在策略里如何使用：见本文件 `compute_jq` 或直接抄一行：
```python
from jqfactor import get_factor_values
ep = get_factor_values(stocks, ['EP'], end_date=context.previous_date, count=1)['EP'].iloc[-1]
```
"""
from __future__ import annotations

from factors._base import FactorEntry, FactorMeta, register


META = FactorMeta(
    name="pe_ttm_inverse",
    chinese_name="TTM PE 倒数 (E/P)",
    category="value",
    description=(
        "盈利收益率 E/P（净利润 TTM / 总市值）。"
        "经典价值因子，A 股长周期 IC 通常在 0.04-0.08。"
        "本仓库直接调用聚宽官方因子 EP（聚宽内置 1/PE_TTM，处理过亏损 / 单位 / 缺失）。"
    ),
    paper_refs=(
        "Fama & French (1992) The Cross-Section of Expected Stock Returns",
        "Liu, Stambaugh, Yuan (2019) Size and value in China",
    ),
    direction="ascending",
    jq_dependencies=("jqfactor.EP",),           # 聚宽官方 factor id
    recommended_neutralization=("SIZE", "industry"),
    universe_hint="中证 800 / 全 A（剔除 ST 与亏损）",
    known_issues=(
        "金融行业（银行 / 保险）的 PE 含义与制造业不同，行业内分位更可靠",
        "周期股的 PE 在景气拐点会误导",
    ),
)


def compute_jq(context, universe):
    """
    在聚宽策略里跑的实现 —— 直接调官方因子库。

    Parameters
    ----------
    context : 聚宽 Context 对象
    universe : list[str] 股票代码列表

    Returns
    -------
    pd.Series, index = 股票代码，value = E/P
    """
    # 注：聚宽云上 jqfactor 在 strategy runtime 里能直接 import；
    # 在 research / Jupyter 环境改用：from jqdatasdk import get_factor_values
    from jqfactor import get_factor_values
    data = get_factor_values(
        securities=universe,
        factors=["EP"],
        end_date=context.previous_date,    # 避免未来函数：用前一交易日
        count=1,
    )
    return data["EP"].iloc[-1]             # 横截面 Series


def compute_local(date, universe):
    """本地 jqdatasdk 离线分析用（适合 factor_lab）。"""
    from jqdatasdk import get_factor_values
    data = get_factor_values(
        securities=universe, factors=["EP"],
        end_date=str(date)[:10], count=1,
    )
    return data["EP"].iloc[-1]


register(FactorEntry(meta=META, compute_jq=compute_jq, compute_local=compute_local,
                     module=__name__))
