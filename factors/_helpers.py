"""
factors/_helpers.py — winsorize / standardize / industry-neutralize 通用函数。

这些函数在因子分析中几乎每次都要用。集中放这里避免每个 factor 文件重复写。

设计原则：纯 numpy / pandas，无聚宽特定依赖；在聚宽云和本地都能 import。
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


def winsorize(s: pd.Series, lower: float = 0.025, upper: float = 0.975) -> pd.Series:
    """分位数去极值。默认 2.5% / 97.5%。"""
    if s.empty:
        return s
    lo = s.quantile(lower)
    hi = s.quantile(upper)
    return s.clip(lower=lo, upper=hi)


def winsorize_mad(s: pd.Series, n: float = 5.0) -> pd.Series:
    """中位数绝对偏差（MAD）去极值。
    比分位数更鲁棒：上下限 = median ± n * MAD。"""
    if s.empty:
        return s
    median = s.median()
    mad = (s - median).abs().median()
    if mad == 0:
        return s
    return s.clip(lower=median - n * 1.4826 * mad, upper=median + n * 1.4826 * mad)


def standardize(s: pd.Series) -> pd.Series:
    """z-score 标准化。"""
    if s.empty:
        return s
    std = s.std(ddof=1)
    if std == 0 or pd.isna(std):
        return s - s.mean()
    return (s - s.mean()) / std


def neutralize(factor: pd.Series, by: pd.DataFrame) -> pd.Series:
    """
    对协变量做线性回归中性化。

    Parameters
    ----------
    factor : pd.Series
        index = 股票代码，value = 因子值。
    by : pd.DataFrame
        index = 股票代码，columns = 协变量（如 log_market_cap、industry dummies）。

    Returns
    -------
    pd.Series
        回归残差，index 同 factor。
    """
    aligned = pd.concat([factor.rename("y"), by], axis=1).dropna()
    if len(aligned) < len(aligned.columns) + 1:
        return factor

    y = aligned["y"].to_numpy()
    X = aligned.drop(columns=["y"]).to_numpy()
    # 加截距
    X = np.column_stack([np.ones(len(X)), X])
    # OLS 闭式解
    try:
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    except np.linalg.LinAlgError:
        return factor
    y_hat = X @ beta
    residual = pd.Series(y - y_hat, index=aligned.index, name=factor.name)
    # 把 dropped 的部分加回去（值为 NaN）
    return residual.reindex(factor.index)


def industry_dummies(industries: pd.Series) -> pd.DataFrame:
    """把行业代码 Series 转成 one-hot DataFrame（drop 第一类避免共线性）。"""
    return pd.get_dummies(industries, drop_first=True, dtype=float)


def pipeline(s: pd.Series, by: Optional[pd.DataFrame] = None) -> pd.Series:
    """
    一站式 winsorize → standardize → (optional) neutralize → standardize。

    Parameters
    ----------
    s : pd.Series
        原始因子值。
    by : pd.DataFrame, optional
        中性化要回归的协变量（log_mcap + industry dummies 是典型）。
    """
    s = winsorize_mad(s)
    s = standardize(s)
    if by is not None:
        s = neutralize(s, by)
        s = standardize(s)
    return s


def rank_normalize(s: pd.Series) -> pd.Series:
    """秩归一化：把因子值映射到 [-1, 1]，对异常值更鲁棒。"""
    if s.empty:
        return s
    n = s.notna().sum()
    if n == 0:
        return s
    ranks = s.rank(method="average")
    return (ranks - (n + 1) / 2) / (n / 2)
