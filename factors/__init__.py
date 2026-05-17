"""
factors — Barra 风格 A 股因子库。

自动 import 所有 category 子包下的 factor module，触发注册。
"""
from __future__ import annotations

# 暴露 registry API
from factors._base import (  # noqa: F401
    Category,
    Direction,
    FactorEntry,
    FactorMeta,
    all_factors,
    by_category,
    get,
    register,
    reset_registry,
    search,
)

# 自动 import 所有 factor 文件以触发 register() 调用
# v1：手动列；v2 可以改成 pkgutil.walk_packages 自动扫描
from factors.value import pe_ttm_inverse, book_to_market  # noqa: F401, E402
from factors.momentum import ret_12m_skip_1m  # noqa: F401, E402
from factors.quality import roe_ttm, gross_profit_margin  # noqa: F401, E402
from factors.growth import revenue_growth_yoy  # noqa: F401, E402
from factors.size import log_market_cap  # noqa: F401, E402
from factors.volatility import vol_60d  # noqa: F401, E402
from factors.reversal import ret_5d  # noqa: F401, E402
