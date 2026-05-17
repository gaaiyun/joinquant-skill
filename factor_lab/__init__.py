"""
factor_lab — 因子分析工具集。

不依赖聚宽云。在本地用 jqdatasdk / akshare 拉数据后跑分析。

子模块：
    single_factor.ic — IC / Rank-IC / IR / decay
    single_factor.grouping — 分组回测
"""
from __future__ import annotations

from factor_lab.single_factor.ic import compute_ic, ic_decay, ICReport  # noqa: F401
from factor_lab.single_factor.grouping import grouping_backtest, GroupingReport  # noqa: F401
