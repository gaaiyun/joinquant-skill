"""
factor_lab/single_factor/ic.py — IC（信息系数）与 Rank-IC 时间序列分析。

定义
----
- **IC(t)**: 横截面上 t 期因子值与 t→t+N 期收益率的 Pearson 相关系数
- **Rank-IC(t)**: 用秩相关（Spearman），对异常值更鲁棒，工业界更常用
- **IC_IR = mean(IC) / std(IC)**: 信号稳定性指标，>0.5 视为好因子

输入约定
--------
factor_panel : DataFrame[date × stock]，单元 = 因子值（已 winsorize/standardize）
returns_panel : DataFrame[date × stock]，单元 = N 日前向收益率
两个 panel 的 index/columns 必须对齐。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd


Method = Literal["pearson", "spearman"]


@dataclass
class ICReport:
    method: Method
    forward_periods: int
    ic_series: pd.Series         # index = date, value = IC
    ic_mean: float
    ic_std: float
    ic_ir: float                 # 日频 IC 序列的 IR = mean / std（**未年化**）
    ic_t_stat: float             # t = mean * sqrt(n) / std
    ic_win_rate: float           # P(IC > 0)
    ic_positive_n: int
    ic_total_n: int

    def annualized_ir(self, periods_per_year: int = 252) -> float:
        """把日频 IR 换算成年化 IR：IR × sqrt(periods_per_year / forward_periods)。

        例：日频持有 IR=0.05 → 年化 IR = 0.05 × sqrt(252/1) ≈ 0.79。
        """
        if not (self.ic_ir == self.ic_ir):   # NaN check
            return float("nan")
        if self.forward_periods <= 0:
            return float("nan")
        import math
        return self.ic_ir * math.sqrt(periods_per_year / self.forward_periods)

    def to_dict(self) -> dict:
        return {
            "method": self.method,
            "forward_periods": self.forward_periods,
            "ic_mean": self.ic_mean,
            "ic_std": self.ic_std,
            "ic_ir": self.ic_ir,             # daily/per-period, NOT annualized
            "ic_ir_annualized": self.annualized_ir(),
            "ic_t_stat": self.ic_t_stat,
            "ic_win_rate": self.ic_win_rate,
            "ic_positive_n": self.ic_positive_n,
            "ic_total_n": self.ic_total_n,
        }


def compute_ic(
    factor_panel: pd.DataFrame,
    returns_panel: pd.DataFrame,
    method: Method = "spearman",
    forward_periods: int = 1,
) -> ICReport:
    """
    计算单因子的 IC 时间序列与汇总统计。

    Parameters
    ----------
    factor_panel : DataFrame[date × stock]
    returns_panel : DataFrame[date × stock]
        必须是「前向收益」—— 第 t 行已经表示 t→t+N 的收益。
        调用方需自己 shift 好（避免在本函数里做有歧义的 shift）。
    method : 'spearman' | 'pearson'
    forward_periods : 仅作为 metadata 写到 report 中，不影响计算（计算依赖
        returns_panel 已经按 forward_periods shift 好的事实）。
    """
    if factor_panel.shape != returns_panel.shape:
        # 对齐 index/columns 的交集
        common_idx = factor_panel.index.intersection(returns_panel.index)
        common_cols = factor_panel.columns.intersection(returns_panel.columns)
        factor_panel = factor_panel.loc[common_idx, common_cols]
        returns_panel = returns_panel.loc[common_idx, common_cols]

    if method not in {"pearson", "spearman"}:
        raise ValueError("method 必须是 'pearson' 或 'spearman'")

    ic_values = []
    for date in factor_panel.index:
        f = factor_panel.loc[date]
        r = returns_panel.loc[date]
        aligned = pd.concat([f.rename("f"), r.rename("r")], axis=1).dropna()
        if len(aligned) < 10:
            ic_values.append(np.nan)
            continue
        ic_values.append(aligned["f"].corr(aligned["r"], method=method))

    ic_series = pd.Series(ic_values, index=factor_panel.index, name="ic").dropna()
    n = len(ic_series)
    if n == 0:
        return ICReport(
            method=method, forward_periods=forward_periods,
            ic_series=ic_series, ic_mean=np.nan, ic_std=np.nan,
            ic_ir=np.nan, ic_t_stat=np.nan, ic_win_rate=np.nan,
            ic_positive_n=0, ic_total_n=0,
        )

    mean = float(ic_series.mean())
    std = float(ic_series.std(ddof=1)) if n > 1 else 0.0
    ir = mean / std if std > 0 else np.nan
    t_stat = mean * np.sqrt(n) / std if std > 0 else np.nan
    positive = int((ic_series > 0).sum())
    return ICReport(
        method=method, forward_periods=forward_periods, ic_series=ic_series,
        ic_mean=mean, ic_std=std, ic_ir=ir, ic_t_stat=t_stat,
        ic_win_rate=positive / n, ic_positive_n=positive, ic_total_n=n,
    )


def ic_decay(
    factor_panel: pd.DataFrame,
    returns_by_horizon: dict[int, pd.DataFrame],
    method: Method = "spearman",
) -> pd.DataFrame:
    """
    因子衰减分析：不同 forward horizon 下的 IC。

    Returns
    -------
    DataFrame[horizon, [ic_mean, ic_ir, ic_t_stat]]
    """
    rows = []
    for h, ret_panel in sorted(returns_by_horizon.items()):
        r = compute_ic(factor_panel, ret_panel, method=method, forward_periods=h)
        rows.append({"horizon": h, "ic_mean": r.ic_mean, "ic_ir": r.ic_ir,
                     "ic_t_stat": r.ic_t_stat, "n": r.ic_total_n})
    return pd.DataFrame(rows).set_index("horizon")
