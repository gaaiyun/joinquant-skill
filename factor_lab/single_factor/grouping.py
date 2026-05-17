"""
factor_lab/single_factor/grouping.py — 分组回测（quintile / decile portfolios）。

每期按因子值排序分 N 组，构建等权组合，看每组的下期累计收益。理想情况下：
- 单调性：组别 → 收益 单调（line plot 像滑梯）
- 多空价差（top - bottom）显著且稳定
- top group 跑赢基准
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class GroupingReport:
    n_groups: int
    group_returns: pd.DataFrame      # index=date, columns=group_1..group_n
    group_cumulative: pd.DataFrame   # 累积收益
    long_short_returns: pd.Series    # group_n - group_1
    long_short_cumulative: pd.Series
    monotonicity_score: float        # spearman corr between group_idx and mean group return
    annualized_long_short: float
    annualized_long_short_vol: float
    long_short_sharpe: float


def grouping_backtest(
    factor_panel: pd.DataFrame,
    forward_returns: pd.DataFrame,
    n_groups: int = 5,
    periods_per_year: int = 252,
) -> GroupingReport:
    """
    Parameters
    ----------
    factor_panel : DataFrame[date × stock]，因子值。
    forward_returns : DataFrame[date × stock]，前向收益（已对齐）。
    n_groups : 分组数（5 = quintile, 10 = decile）。
    periods_per_year : 用于年化（日 = 252, 周 = 52, 月 = 12）。
    """
    common_idx = factor_panel.index.intersection(forward_returns.index)
    common_cols = factor_panel.columns.intersection(forward_returns.columns)
    factor_panel = factor_panel.loc[common_idx, common_cols]
    forward_returns = forward_returns.loc[common_idx, common_cols]

    group_ret_rows = []
    for date in factor_panel.index:
        f = factor_panel.loc[date]
        r = forward_returns.loc[date]
        aligned = pd.concat([f.rename("f"), r.rename("r")], axis=1).dropna()
        if len(aligned) < n_groups * 5:
            group_ret_rows.append({f"group_{g + 1}": np.nan for g in range(n_groups)})
            continue
        aligned["group"] = pd.qcut(
            aligned["f"].rank(method="first"), q=n_groups,
            labels=range(1, n_groups + 1), duplicates="drop",
        )
        means = aligned.groupby("group", observed=True)["r"].mean()
        group_ret_rows.append({f"group_{int(g)}": v for g, v in means.items()})

    group_returns = pd.DataFrame(group_ret_rows, index=factor_panel.index)
    group_returns = group_returns.reindex(
        columns=[f"group_{g + 1}" for g in range(n_groups)]
    )

    # 累积收益（连乘 (1+r)）
    group_cumulative = (1 + group_returns.fillna(0)).cumprod() - 1

    # 多空价差
    long_short = group_returns[f"group_{n_groups}"] - group_returns["group_1"]
    long_short_cum = (1 + long_short.fillna(0)).cumprod() - 1

    # 单调性：组号 vs 各组期间平均收益的 spearman
    mean_per_group = group_returns.mean()
    group_idx = np.arange(1, n_groups + 1, dtype=float)
    if mean_per_group.notna().sum() >= 2:
        monotonicity = float(pd.Series(group_idx).corr(
            mean_per_group.reset_index(drop=True), method="spearman"
        ))
    else:
        monotonicity = np.nan

    ls_clean = long_short.dropna()
    if len(ls_clean) > 1:
        ann = float(ls_clean.mean() * periods_per_year)
        ann_vol = float(ls_clean.std(ddof=1) * np.sqrt(periods_per_year))
        sharpe = ann / ann_vol if ann_vol > 0 else np.nan
    else:
        ann = ann_vol = sharpe = np.nan

    return GroupingReport(
        n_groups=n_groups,
        group_returns=group_returns,
        group_cumulative=group_cumulative,
        long_short_returns=long_short,
        long_short_cumulative=long_short_cum,
        monotonicity_score=monotonicity,
        annualized_long_short=ann,
        annualized_long_short_vol=ann_vol,
        long_short_sharpe=sharpe,
    )
